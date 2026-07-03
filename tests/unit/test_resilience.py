"""Tests for resilience/stay_alive module.

# BOT-001 through BOT-010
"""
import asyncio
import time

import pytest

from fire_suppression.resilience.stay_alive import (
    ClockMonitor,
    ConfigResilience,
    DegradationMode,
    DetectionTimeoutGuard,
    DiskGuard,
    MemoryGuard,
    NetworkPartitionQueue,
    RelayHealthMonitor,
    SensorResilienceMonitor,
    SQLiteResilience,
    StayAliveManager,
)


class TestSensorResilienceMonitor:
    def test_initially_full_mode(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40", "mlx90614"])
        state = mon.get_state()
        assert state.mode == DegradationMode.FULL
        assert len(state.active_sensors) == 3

    def test_single_sensor_degradation(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40"])
        mon.record_failure("mq2")
        mon.record_failure("mq2")
        mon.record_failure("mq2")
        state = mon.get_state()
        assert state.mode == DegradationMode.DEGRADED
        assert "mq2" in state.failed_sensors
        assert "sht40" in state.active_sensors

    def test_emergency_mode(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40", "mlx90614"])
        mon.record_failure("mq2")
        mon.record_failure("mq2")
        mon.record_failure("mq2")
        mon.record_failure("sht40")
        mon.record_failure("sht40")
        mon.record_failure("sht40")
        state = mon.get_state()
        assert state.mode == DegradationMode.EMERGENCY
        assert state.detection_fallback == "camera_only"

    def test_success_resets(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40"])
        mon.record_failure("mq2")
        mon.record_failure("mq2")
        mon.record_success("mq2")
        state = mon.get_state()
        assert state.mode == DegradationMode.FULL

    def test_weight_redistribution(self) -> None:
        mon = SensorResilienceMonitor(["mq2", "sht40"])
        mon.record_failure("mq2")
        mon.record_failure("mq2")
        mon.record_failure("mq2")
        assert mon.get_weight("mq2") == 0.0
        assert mon.get_weight("sht40") == 1.0

    def test_unknown_sensor(self) -> None:
        mon = SensorResilienceMonitor(["mq2"])
        mon.record_failure("nonexistent")
        mon.record_success("nonexistent")
        assert mon.get_weight("nonexistent") == 0.0


class TestDetectionTimeoutGuard:
    @pytest.mark.asyncio
    async def test_success_no_fallback(self) -> None:
        guard = DetectionTimeoutGuard(timeout_seconds=1.0)

        async def fast_task():
            return "primary"

        async def fallback():
            return "fallback"

        result = await guard.run_with_timeout(fast_task, fallback)
        assert result == "primary"

    @pytest.mark.asyncio
    async def test_timeout_uses_fallback(self) -> None:
        guard = DetectionTimeoutGuard(timeout_seconds=0.1)

        async def slow_task():
            await asyncio.sleep(1.0)
            return "primary"

        async def fallback():
            return "fallback"

        result = await guard.run_with_timeout(slow_task, fallback)
        assert result == "fallback"


class TestSQLiteResilience:
    def test_recover_new_db(self, tmp_path) -> None:
        db = SQLiteResilience(str(tmp_path / "test.db"))
        assert db.recover() is False

    def test_is_corrupt_nonexistent(self, tmp_path) -> None:
        db = SQLiteResilience(str(tmp_path / "test.db"))
        assert db._is_corrupt() is False


class TestMemoryGuard:
    def test_check(self) -> None:
        guard = MemoryGuard(check_interval=60.0, growth_threshold_mb=50.0)
        result = guard.check()
        assert "current_mb" in result
        assert "status" in result


class TestNetworkPartitionQueue:
    def test_enqueue_and_dequeue(self, tmp_path) -> None:
        q = NetworkPartitionQueue(tmp_path / "queue.json")
        q.enqueue({"type": "alert", "msg": "fire"})
        q.enqueue({"type": "status", "msg": "ok"})
        assert len(q._queue) == 2
        items = q.dequeue_all()
        assert len(items) == 2
        assert items[0]["type"] == "alert"
        assert len(q._queue) == 0


class TestRelayHealthMonitor:
    def test_relay_toggle_tracking(self) -> None:
        mon = RelayHealthMonitor({"zone_a": 1, "zone_b": 2})
        mon.record_toggle("zone_a", True)
        assert mon.is_healthy("zone_a")
        mon.record_toggle("zone_b", False)
        assert not mon.is_healthy("zone_b")


class TestConfigResilience:
    def test_atomic_write(self, tmp_path) -> None:
        cr = ConfigResilience(tmp_path / "config.yaml")
        cr.atomic_write("test: value")
        assert (tmp_path / "config.yaml").exists()

    def test_recover(self, tmp_path) -> None:
        cr = ConfigResilience(tmp_path / "config.yaml")
        cr.atomic_write("original")
        cr.atomic_write("updated")
        recovered = cr.recover()
        assert recovered == "original"


class TestClockMonitor:
    def test_initial_confidence(self) -> None:
        mon = ClockMonitor(has_rtc=True)
        result = mon.check()
        assert result["status"] == "OK"
        assert result["has_rtc"] is True

    def test_mark_sync(self) -> None:
        mon = ClockMonitor()
        mon.mark_sync()
        result = mon.check()
        assert result["ntp_confidence"] == 1.0


class TestDiskGuard:
    def test_check(self) -> None:
        guard = DiskGuard(min_free_gb=0.01)
        result = guard.check()
        assert "free_gb" in result
        assert "status" in result


class TestStayAliveManager:
    def test_init(self) -> None:
        mgr = StayAliveManager({
            "sensor_names": ["mq2", "sht40"],
            "relay_pins": {"zone_a": 1},
            "db_path": "/tmp/test.db",
            "config_path": "/tmp/config.yaml",
        })
        health = mgr.health_snapshot()
        assert "mode" in health
        assert health["active_sensor_count"] == 2
        assert "memory" in health
        assert "disk" in health
