"""Tests for I2C bus scanning.

# S001 — I2C Bus Discovery
"""
from fire_suppression.sensors.i2c import scan_i2c_bus, i2c_device_present


class TestI2CScan:
    """# S001 — I2C Bus Discovery"""

    def test_mock_scan_returns_devices(self) -> None:
        result = scan_i2c_bus(1, mock=True)
        assert len(result) >= 5
        assert 0x48 in result  # ADS1115
        assert 0x44 in result  # SHT40
        assert 0x5A in result  # MLX90614

    def test_mock_scan_descriptions(self) -> None:
        result = scan_i2c_bus(1, mock=True)
        assert "ADS1115" in result[0x48]
        assert "SHT40" in result[0x44]

    def test_i2c_device_present_mock(self) -> None:
        assert i2c_device_present(1, 0x48, mock=True) is True
        assert i2c_device_present(1, 0x99, mock=True) is False  # Not in KNOWN_ADDRESSES

    def test_i2c_device_present_no_smbus(self) -> None:
        # Without smbus2 and not mocking, returns empty dict
        result = scan_i2c_bus(1, mock=False)
        assert isinstance(result, dict)
