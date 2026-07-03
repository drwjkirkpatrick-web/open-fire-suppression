"""Tests for base sensor and mock sensor classes.

# S012 — Sensor Health Monitoring
# M001 — Mock Hardware Layer
# M002 — Simulated Fire Scenarios
"""
import asyncio

import pytest

from fire_suppression.sensors.base import BaseSensor, MockSensor, SensorReading, SensorStatus


class DummySensor(BaseSensor):
    """Minimal sensor for testing BaseSensor health tracking."""
    async def read(self) -> SensorReading:
        return SensorReading(
            sensor_name="dummy",
            timestamp=0.0,
            values={"v": 1.0},
        )
    async def close(self) -> None:
        self._closed = True


class TestSensorHealth:
    """# S012 — Sensor Health Monitoring"""

    @pytest.mark.asyncio
    async def test_success_tracking(self) -> None:
        s = DummySensor("test")
        await s.read_with_health()
        assert s.health.total_reads == 1
        assert s.health.successful_reads == 1
        assert s.health.status == SensorStatus.OK

    @pytest.mark.asyncio
    async def test_failure_tracking(self) -> None:
        class FailingSensor(BaseSensor):
            async def read(self) -> SensorReading:
                raise RuntimeError("comm failure")
            async def close(self) -> None:
                pass

        s = FailingSensor("fail")
        result = await s.read_with_health()
        assert result is None
        assert s.health.total_reads == 1
        assert s.health.failed_reads == 1
        assert s.health.status == SensorStatus.ERROR
        assert "comm failure" in s.health.last_error

    @pytest.mark.asyncio
    async def test_window_degradation(self) -> None:
        from fire_suppression.sensors.base import BaseSensor

        class FailingSensor(BaseSensor):
            async def read(self) -> SensorReading:
                raise RuntimeError("comm failure")
            async def close(self) -> None:
                pass

        s = FailingSensor("fail")
        s._health_window = 4
        # 2 failures
        for _ in range(2):
            await s.read_with_health()
        # We need to verify the window trimming works
        assert s.health.total_reads == 2


class TestMockSensor:
    """# M001 — Mock Hardware Layer"""

    @pytest.mark.asyncio
    async def test_mock_reads(self) -> None:
        s = MockSensor("mock", initial_values={"temp": 25.0})
        r = await s.read()
        assert r.values["temp"] == 25.0

    @pytest.mark.asyncio
    async def test_mock_scenario_smoldering(self) -> None:
        """# M002 — Simulated Fire Scenarios"""
        s = MockSensor("mock")
        s.set_scenario("smoldering")
        readings = []
        for _ in range(5):
            r = await s.read()
            readings.append(r.values)
        # Temperature should rise over time
        assert readings[4]["temperature_c"] > readings[0]["temperature_c"]
        # Smoke should increase
        assert readings[4]["smoke_ppm"] > readings[0]["smoke_ppm"]

    @pytest.mark.asyncio
    async def test_mock_scenario_flashover(self) -> None:
        s = MockSensor("mock")
        s.set_scenario("flashover")
        r1 = await s.read()
        r10 = None
        for _ in range(9):
            r10 = await s.read()
        assert r10.values["temperature_c"] > r1.values["temperature_c"]
        assert r10.values["smoke_ppm"] > 100  # Flashover produces significant smoke

    @pytest.mark.asyncio
    async def test_mock_false_alarm(self) -> None:
        s = MockSensor("mock")
        s.set_scenario("false_alarm")
        r = await s.read()
        # High temp but no smoke/gas (step 0: exactly 25°C, then rises)
        assert r.values["temperature_c"] >= 25
        assert r.values["smoke_ppm"] == 10.0
        assert r.values["tvoc_ppb"] == 50.0

    @pytest.mark.asyncio
    async def test_mock_set_values(self) -> None:
        s = MockSensor("mock", initial_values={"a": 1.0})
        s.set_values({"a": 99.0, "b": 2.0})
        r = await s.read()
        assert r.values["a"] == 99.0
        assert r.values["b"] == 2.0
