"""SHT40 temperature and humidity sensor driver.

# S004 — SHT40 Temperature & Humidity
"""
from __future__ import annotations

import logging
import struct
import time
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SHT40_I2C_ADDRESS = 0x44
SHT40_ALT_ADDRESS = 0x45

# Commands (MSB)
SHT40_CMD_MEASURE_HIGH_PRECISION = 0xFD  # High precision, ~8.3ms
SHT40_CMD_MEASURE_MEDIUM_PRECISION = 0xF6  # Medium precision, ~4.8ms
SHT40_CMD_MEASURE_LOW_PRECISION = 0xE0   # Low precision, ~1.7ms
SHT40_CMD_SOFT_RESET = 0x94
SHT40_CMD_READ_SERIAL = 0x89

# CRC-8 parameters (x^8 + x^5 + x^4 + 1 = 0x31)
_CRC8_POLYNOMIAL = 0x31
_CRC8_INIT = 0xFF


def _crc8(data: bytes) -> int:
    """Calculate CRC-8 for SHT40 data validation."""
    crc = _CRC8_INIT
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ _CRC8_POLYNOMIAL
            else:
                crc <<= 1
            crc &= 0xFF
    return crc


class SHT40Sensor(BaseSensor):
    """Sensirion SHT40 temperature and humidity sensor.

    Highly reliable I2C sensor with CRC-checked data. Recommended over DHT22.
    """

    def __init__(
        self,
        name: str = "sht40",
        *,
        bus_number: int = 1,
        address: int = SHT40_I2C_ADDRESS,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.address = address
        self._bus = None

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
                self._soft_reset()
            except Exception as exc:
                logger.error("SHT40 init failed: %s", exc)
                self._bus = None

    def _soft_reset(self) -> None:
        if self._bus is None:
            return
        try:
            self._bus.write_byte(self.address, SHT40_CMD_SOFT_RESET)
            time.sleep(0.001)
        except Exception:
            pass

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "temperature_c": 25.0,
                    "humidity_percent": 50.0,
                },
                raw=b"\x66\x93\x7C\x27\x40\x2E",
                unit="°C / %RH",
            )

        if self._bus is None:
            raise RuntimeError("SHT40 SMBus not initialized")

        try:
            # Trigger measurement
            self._bus.write_byte(self.address, SHT40_CMD_MEASURE_HIGH_PRECISION)
            time.sleep(0.009)  # Wait for measurement (high precision)

            # Read 6 bytes: [temp MSB, temp LSB, temp CRC, hum MSB, hum LSB, hum CRC]
            data = self._bus.read_i2c_block_data(self.address, 0x00, 6)
            raw = bytes(data)

            # Validate CRCs
            if _crc8(raw[:2]) != raw[2]:
                raise ValueError("SHT40 temperature CRC mismatch")
            if _crc8(raw[3:5]) != raw[5]:
                raise ValueError("SHT40 humidity CRC mismatch")

            temp_raw = struct.unpack(">H", raw[:2])[0]
            hum_raw = struct.unpack(">H", raw[3:5])[0]

            # Sensirion conversion formulas
            temperature_c = -45.0 + 175.0 * (temp_raw / 65535.0)
            humidity_percent = -6.0 + 125.0 * (hum_raw / 65535.0)
            humidity_percent = max(0.0, min(100.0, humidity_percent))

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "temperature_c": round(temperature_c, 2),
                    "humidity_percent": round(humidity_percent, 2),
                },
                raw=raw,
                unit="°C / %RH",
            )

        except Exception as exc:
            logger.error("SHT40 read error: %s", exc)
            raise

    async def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
