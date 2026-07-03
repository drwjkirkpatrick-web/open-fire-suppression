"""I2C bus manager with device discovery for open-fire-suppression.

# S001 — I2C Bus Discovery
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from smbus2 import SMBus

logger = logging.getLogger(__name__)

# Common I2C device addresses for fire-suppression sensors
KNOWN_ADDRESSES: dict[int, str] = {
    0x48: "ADS1115 (ADC)",
    0x49: "ADS1115 alt",
    0x4A: "ADS1115 alt2",
    0x4B: "ADS1115 alt3",
    0x44: "SHT40 / SHT30",
    0x45: "SHT40 alt / SHT30 alt",
    0x5A: "MLX90614 (IR thermometer)",
    0x5B: "MLX90614 alt",
    0x76: "BME680 / BMP280",
    0x77: "BME680 alt / BMP280 alt",
    0x53: "ENS160",
    0x68: "AMG8833 / MPU6050 / DS3231",
    0x69: "AMG8833 alt / MPU6050 alt",
    0x33: "MLX90640 / MLX90641",
}


def scan_i2c_bus(bus_number: int = 1, *, mock: bool = False) -> dict[int, str]:
    """Scan the I2C bus and return a mapping of detected addresses to descriptions.

    Args:
        bus_number: Raspberry Pi I2C bus (default 1 on Pi 5).
        mock: If True, return synthetic results for development.

    Returns:
        Mapping of ``address → description`` for each device that ACKed.
    """
    found: dict[int, str] = {}

    if mock:
        # Simulate a fully-populated system for development
        logger.info("[MOCK] I2C scan returning synthetic devices")
        return {
            0x48: "ADS1115 (ADC)",
            0x44: "SHT40 (temp/humidity)",
            0x5A: "MLX90614 (IR thermometer)",
            0x77: "BME680 (temp/humidity/pressure/gas)",
            0x53: "ENS160 (VOC/eCO2)",
            0x69: "AMG8833 (thermal 8x8)",
        }

    try:
        from smbus2 import SMBus
    except ImportError:
        logger.warning("smbus2 not installed; I2C scan unavailable")
        return found

    try:
        with SMBus(bus_number) as bus:
            for addr in range(0x03, 0x78):  # Valid 7-bit I2C address range
                try:
                    bus.write_quick(addr)
                    desc = KNOWN_ADDRESSES.get(addr, f"Unknown device 0x{addr:02X}")
                    found[addr] = desc
                    logger.debug("I2C device found at 0x%02X: %s", addr, desc)
                except OSError:
                    pass  # No device at this address
    except Exception as exc:
        logger.error("I2C scan failed on bus %d: %s", bus_number, exc)

    if found:
        logger.info("I2C bus %d scan complete: %d device(s) found", bus_number, len(found))
    else:
        logger.warning("I2C bus %d scan: no devices found", bus_number)

    return found


def i2c_device_present(bus_number: int, address: int, *, mock: bool = False) -> bool:
    """Check if a specific I2C device is present.

    Args:
        bus_number: I2C bus number.
        address: 7-bit I2C address.
        mock: Return True in mock mode.

    Returns:
        True if the device ACKed a probe.
    """
    if mock:
        return address in KNOWN_ADDRESSES

    try:
        from smbus2 import SMBus
    except ImportError:
        return False

    try:
        with SMBus(bus_number) as bus:
            bus.write_quick(address)
            return True
    except OSError:
        return False
    except Exception:
        return False
