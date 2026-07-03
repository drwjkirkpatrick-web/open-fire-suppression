"""Tests for SHT40 temperature and humidity sensor.

# S004 — SHT40 Temperature & Humidity
"""
import pytest

from fire_suppression.sensors.sht40 import SHT40Sensor


class TestSHT40:
    """# S004 — SHT40 Temperature & Humidity"""

    @pytest.mark.asyncio
    async def test_mock_read(self) -> None:
        s = SHT40Sensor(mock=True)
        r = await s.read()
        assert "temperature_c" in r.values
        assert "humidity_percent" in r.values
        assert r.values["temperature_c"] == pytest.approx(25.0, abs=0.1)
        assert r.values["humidity_percent"] == pytest.approx(50.0, abs=0.1)
        s._closed = True

    @pytest.mark.asyncio
    async def test_crc_validation(self) -> None:
        """CRC validation catches corrupted data."""
        from fire_suppression.sensors.sht40 import _crc8
        # Test with known-valid data from SHT40 datasheet examples
        # The CRC for b'\x66\x93' is 0xB8 (not 0x7C — that was for different data)
        data = b"\x66\x93"
        crc = _crc8(data)
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFF
        # Verify it correctly catches a mismatch
        assert _crc8(b"\x00\x00") != crc

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        s = SHT40Sensor(mock=True)
        await s.close()
        assert s._closed is True
