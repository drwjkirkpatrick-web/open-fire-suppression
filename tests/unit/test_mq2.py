"""Tests for MQ-2 smoke sensor.

# S003 — MQ-2 Smoke Sensor Calibration
"""
import pytest

from fire_suppression.sensors.mq2 import MQ2Sensor


class TestMQ2:
    """# S003 — MQ-2 Smoke Sensor Calibration"""

    @pytest.mark.asyncio
    async def test_mock_read(self) -> None:
        s = MQ2Sensor(mock=True)
        r = await s.read()
        assert "smoke_ppm" in r.values
        assert "lpg_ppm" in r.values
        assert "rs" in r.values
        assert r.values["warmed_up"] is True
        s._closed = True

    @pytest.mark.asyncio
    async def test_warmup_state(self) -> None:
        s = MQ2Sensor(mock=True, warmup_seconds=60)
        # In mock mode, warmup is immediate for testing
        # But _start_time is set at init; after a small sleep it should pass
        import time as _time
        s._start_time = _time.time() - 61  # Pretend we started 61 seconds ago
        assert s.is_warmed_up is True
        s._closed = True

    @pytest.mark.asyncio
    async def test_calibrate_r0(self) -> None:
        s = MQ2Sensor(mock=True)
        r0 = await s.calibrate_r0(samples=10)
        assert r0 == pytest.approx(10000.0, abs=0.1)
        s._closed = True

    def test_rs_calculation(self) -> None:
        from fire_suppression.sensors.mq2 import MQ2Sensor
        rs = MQ2Sensor._calculate_rs(2.5, vcc=5.0, rl=10000.0)
        assert rs == pytest.approx(10000.0, abs=0.1)

    def test_ppm_calculation(self) -> None:
        from fire_suppression.sensors.mq2 import MQ2Sensor
        # Rs/R0 = 1.5, a=322, b=-2.47
        ppm = MQ2Sensor._ratio_to_ppm(1.5, 322.0, -2.47)
        assert ppm > 0
        assert ppm < 1000

    def test_zero_voltage(self) -> None:
        from fire_suppression.sensors.mq2 import MQ2Sensor
        rs = MQ2Sensor._calculate_rs(0.0)
        assert rs == float("inf")
