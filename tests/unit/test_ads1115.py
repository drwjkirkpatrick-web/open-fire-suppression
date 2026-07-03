"""Tests for ADS1115 ADC sensor.

# S002 — ADS1115 ADC Reading
"""
import pytest

from fire_suppression.sensors.ads1115 import ADS1115Sensor


class TestADS1115:
    """# S002 — ADS1115 ADC Reading"""

    @pytest.mark.asyncio
    async def test_mock_read_all_channels(self) -> None:
        s = ADS1115Sensor(mock=True)
        r = await s.read()
        assert "channel_0" in r.values
        assert "channel_1" in r.values
        assert "channel_2" in r.values
        assert "channel_3" in r.values
        assert r.unit == "V"
        s._closed = True

    @pytest.mark.asyncio
    async def test_mock_channel_values(self) -> None:
        s = ADS1115Sensor(mock=True)
        r = await s.read()
        # Mock values are 1.65, 1.85, 2.05, 2.25
        assert r.values["channel_0"] == pytest.approx(1.65, abs=0.01)
        assert r.values["channel_3"] == pytest.approx(2.25, abs=0.01)
        s._closed = True

    @pytest.mark.asyncio
    async def test_read_single_channel(self) -> None:
        s = ADS1115Sensor(mock=True)
        voltage = await s.read_channel(0)
        assert voltage == pytest.approx(1.65, abs=0.01)
        s._closed = True

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        s = ADS1115Sensor(mock=True)
        await s.close()
        assert s._closed is True
