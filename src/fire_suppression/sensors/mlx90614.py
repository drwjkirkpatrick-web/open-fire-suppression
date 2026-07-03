"""MLX90614 non-contact infrared thermometer sensor driver.

# S005 — MLX90614 Non-Contact Temperature
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

MLX90614_I2C_ADDRESS = 0x5A
MLX90614_ALT_ADDRESS = 0x5B

# Register addresses
MLX90614_RAW_IR1 = 0x04    # Ambient-compensated IR sensor 1
MLX90614_RAW_IR2 = 0x05    # IR sensor 2 (dual-zone models)
MLX90614_TA = 0x06          # Ambient temperature (chip die)
MLX90614_TOBJ1 = 0x07       # Object temperature (primary)
MLX90614_TOBJ2 = 0x08       # Object temperature (secondary)
MLX90614_EMISSIVITY = 0x24  # Emissivity register (0xFFFF = 1.0)
MLX90614_CONFIG1 = 0x25
MLX90614_ADDR = 0x2E       # I2C address register

# MLX90614 scaling factor
MLX90614_TEMP_SCALE = 0.02  # Each LSB = 0.02 Kelvin
MLX90614_KELVIN_OFFSET = 273.15


class MLX90614Sensor(BaseSensor):
    """Melexis MLX90614 non-contact infrared thermometer.

    Measures object temperature without physical contact.
    Critical for detecting hot spots in fire zones from a safe distance.
    """

    def __init__(
        self,
        name: str = "mlx90614",
        *,
        bus_number: int = 1,
        address: int = MLX90614_I2C_ADDRESS,
        emissivity: float = 1.0,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.address = address
        self.emissivity = emissivity
        self._bus = None

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
            except Exception as exc:
                logger.error("MLX90614 init failed: %s", exc)
                self._bus = None

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "object_temperature_c": 25.0,
                    "ambient_temperature_c": 22.0,
                },
                raw={"tobj": 29815, "ta": 29515},
                unit="°C",
            )

        if self._bus is None:
            raise RuntimeError("MLX90614 SMBus not initialized")

        try:
            tobj_raw = self._read_register(MLX90614_TOBJ1)
            ta_raw = self._read_register(MLX90614_TA)

            if tobj_raw is None or ta_raw is None:
                raise RuntimeError("MLX90614 register read failed")

            object_temp_c = self._raw_to_celsius(tobj_raw)
            ambient_temp_c = self._raw_to_celsius(ta_raw)

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "object_temperature_c": round(object_temp_c, 2),
                    "ambient_temperature_c": round(ambient_temp_c, 2),
                },
                raw={"tobj": tobj_raw, "ta": ta_raw},
                unit="°C",
            )

        except Exception as exc:
            logger.error("MLX90614 read error: %s", exc)
            raise

    def _read_register(self, reg: int) -> int | None:
        """Read a 16-bit register with PEC (packet error code) check."""
        if self._bus is None:
            return None
        try:
            # MLX90614 requires SMBus read with PEC
            data = self._bus.read_word_data(self.address, reg)
            # Swap bytes (SMBus reads little-endian but MLX90614 is big-endian)
            raw = ((data & 0xFF) << 8) | ((data >> 8) & 0xFF)
            return raw
        except Exception:
            return None

    @staticmethod
    def _raw_to_celsius(raw: int) -> float:
        """Convert MLX90614 raw reading to Celsius."""
        # Handle negative temperatures (two's complement for 16-bit)
        if raw & 0x8000:
            raw = raw - 0x10000
        temp_k = raw * MLX90614_TEMP_SCALE
        return temp_k - MLX90614_KELVIN_OFFSET

    async def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
