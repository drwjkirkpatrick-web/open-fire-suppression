"""Tests for resilience/stay_alive module.

# BOT-001 through BOT-010
"""
import asyncio

import pytest

from fire_suppression.resilience.stay_alive import (
    ClockMonitor,
    ConfigResilience,
    DegradationMode,
    DetectionTimeoutGuard,
    MemoryMonitor,
    RelayHealthMonitor,
    SensorResilienceMonitor,
    SQLiteResilience,
    StayAliveOrchestrator,
    StoreAndForwardQueue,
)


class TestSensorResilienceMonitor:
    def test_initially_full_mode(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40", "mlx90614"])
        state = mon.get_state()
        assert state.mode == DegradationMode.FULL
        assert len(state.active_sensors) == 3

    def test_single_sensor_degradation(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40", "mlx90614"])
        for _ in range(4):
            mon.record_failure("mq2")
        state = mon.get_state()
        assert state.mode == DegradationMode.DEGRADED
        assert "mq2" in state.failed_sensors
        assert "mq2" not in state.active_sensors

    def test_weight_redistribution(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40"])
        mon._max_failures = 1
        mon.record_failure("mq2")
        assert mon.get_weight("mq2") == 0.0
        assert mon.get_weight("sht40") == 1.0

    def test_sensor_recovery(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40"])
        mon.record_failure("mq2")
        mon.record_success("mq2")
        state = mon.get_state()
        assert "mq2" in state.active_sensors


class TestDetectionTimeoutGuard:
    @pytest.mark.asyncio
    async def test_normal_completion(self) -> None:
        guard = DetectionTimeoutGuard(timeout_seconds=1.0)
        async def fast():
            return "ok"
        async def fallback():
            return "fallback"
        result = await guard.run_with_timeout(fast, fallback)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_timeout_falls_back(self) -> None:
        guard = DetectionTimeoutGuard(timeout_seconds=0.1)
        async def slow():
            await asyncio.sleep(1.0)
            return "ok"
        async def fallback():
            return "fallback"
        result = await guard.run_with_timeout(slow, fallback)
        assert result == "fallback"


class TestStoreAndForwardQueue:
    def test_enqueue_and_dequeue(self, tmp_path) -> None:
        q = StoreAndForwardQueue(tmp_path / "queue.json")
        q.enqueue({"type": "alert", "msg": "fire"})
        q.enqueue({"type": "status", "msg": "ok"})
        assert q.size == 2
        items = q.dequeue_all()
        assert len(items) == 2
        assert items[0]["type"] == "alert"
        assert q.size == 0


class TestRelayHealthMonitor:
    def test_relay_toggle_tracking(self) -> None:
        mon = RelayHealthMonitor({1: "zone_a", 2: "zone_b"})
        mon.record_toggle("zone_a", True)
        assert mon.is_healthy("zone_a")
        mon.record_toggle("zone_b", False)
        assert not mon.is_healthy("zone_b")


class TestConfigResilience:
    def test_atomic_write(self, tmp_path) -> None:
        cr = ConfigResilience(tmp_path / "config.yaml")
        cr.atomic_write("test: value")
        assert (tmp_path / "config.yaml").exists()
        assert "test: value" in (tmp_path / "config.yaml").read_text()

    def test_recover(self, tmp_path) -> None:
        cr = ConfigResilience(tmp_path / "config.yaml")
        # Write initial config
        cr.atomic_write("original")
        # Write new config (which backs up original to LKG)
        cr.atomic_write("updated")
        recovered = cr.recover()
        assert recovered == "original"


class TestClockMonitor:
    def test_initial_confidence(self) -> None:
        mon = ClockMonitor(mock=True)
        assert mon.get_confidence() in ("high", "medium", "low", "unknown")

    def test_ntp_status_update(self) -> None:
        mon = ClockMonitor(mock=True)
        mon.update_ntp_status(synced=True)
        assert mon._ntp_confidence == "high"
        assert mon.get_status()["ntp_confidence"] == "high"


class TestStayAliveOrchestrator:
    def test_configure(self) -> None:
        orch = StayAliveOrchestrator()
        orch.configure(
            sensor_names=["mq2", "sht40"],
            relay_pins={1: "zone_a"},
            queue_path="/tmp/test_queue.json",
        )
        assert orch.sensor_monitor is not None
        assert orch.relay_monitor is not None

    def test_health_snapshot(self) -> None:
        orch = StayAliveOrchestrator()
        orch.configure(
            sensor_names=["mq2", "sht40"],
            relay_pins={1: "zone_a"},
            queue_path="/tmp/test_queue.json",
        )
        health = orch.get_health_snapshot()
        assert "mode" in health
        assert "timestamp" in health
