"""AMG8833 8×8 thermal camera sensor driver.

# S008 — AMG8833 Thermal Grid
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

AMG8833_I2C_ADDRESS = 0x69
AMG8833_ALT_ADDRESS = 0x68

# AMG8833 registers
AMG8833_PCTL = 0x00
AMG8833_RST = 0x01
AMG8833_FPSC = 0x02
AMG8833_INTC = 0x03
AMG8833_STAT = 0x04
AMG8833_SCLR = 0x05
AMG8833_AVE = 0x07
AMG8833_INTHL = 0x08
AMG8833_INTHH = 0x09
AMG8833_INTLL = 0x0A
AMG8833_INTLH = 0x0B
AMG8833_IHYSL = 0x0C
AMG8833_IHYSH = 0x0D
AMG8833_TTHL = 0x0E
AMG8833_TTHH = 0x0F
AMG8833_PIXEL_OFFSET = 0x80  # 64 pixels × 2 bytes

# Power control modes
AMG8833_NORMAL_MODE = 0x00
AMG8833_SLEEP_MODE = 0x10
AMG8833_STAND_BY_60S = 0x20
AMG8833_STAND_BY_10S = 0x21

# Frame rates
AMG8833_FPS_1 = 0x01
AMG8833_FPS_10 = 0x00

# Interrupt modes
AMG8833_INTEN = 0x01  # Enable interrupts
AMG8833_INTMOD = 0x02  # Absolute value mode (vs. difference mode)


class AMG8833Sensor(BaseSensor):
    """Panasonic AMG8833 8×8 thermal infrared array sensor.

    Returns a grid of 64 temperature readings (0.25°C resolution).
    Good for monitoring zones and detecting hotspots.
    """

    def __init__(
        self,
        name: str = "amg8833",
        *,
        bus_number: int = 1,
        address: int = AMG8833_I2C_ADDRESS,
        fps: int = 10,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.address = address
        self.fps = fps
        self._bus = None

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
                self._configure()
            except Exception as exc:
                logger.error("AMG8833 init failed: %s", exc)
                self._bus = None

    def _configure(self) -> None:
        if self._bus is None:
            return
        try:
            # Normal mode
            self._bus.write_byte_data(self.address, AMG8833_PCTL, AMG8833_NORMAL_MODE)
            time.sleep(0.01)
            # Set frame rate
            fps_reg = AMG8833_FPS_10 if self.fps == 10 else AMG8833_FPS_1
            self._bus.write_byte_data(self.address, AMG8833_FPSC, fps_reg)
            time.sleep(0.01)
            # Reset interrupt flags
            self._bus.write_byte_data(self.address, AMG8833_INTC, 0x00)
            time.sleep(0.01)
        except Exception:
            pass

    async def read(self) -> SensorReading:
        if self.mock:
            # Generate a grid with a hotspot in the center
            grid = [25.0] * 64
            # Hotspot at center pixels (row 3-4, col 3-4)
            for r in range(3, 5):
                for c in range(3, 5):
                    idx = r * 8 + c
                    grid[idx] = 65.0
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={f"pixel_{i:02d}": v for i, v in enumerate(grid)},
                raw=grid,
                unit="°C",
            )

        if self._bus is None:
            raise RuntimeError("AMG8833 SMBus not initialized")

        try:
            # Read 64 pixels (128 bytes) starting at 0x80
            data = self._bus.read_i2c_block_data(self.address, AMG8833_PIXEL_OFFSET, 128)

            temperatures: list[float] = []
            values: dict[str, float] = {}

            for i in range(64):
                # Each pixel is 12-bit signed, stored as 2 bytes
                raw = (data[i * 2 + 1] << 8) | data[i * 2]
                # Convert to signed 12-bit
                if raw & 0x800:
                    raw = raw - 0x1000
                # Scale: each LSB = 0.25°C
                temp = raw * 0.25
                temperatures.append(temp)
                values[f"pixel_{i:02d}"] = round(temp, 2)

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values=values,
                raw=temperatures,
                unit="°C",
            )

        except Exception as exc:
            logger.error("AMG8833 read error: %s", exc)
            raise

    async def get_thermistor(self) -> float:
        """Read the built-in thermistor (ambient reference temperature)."""
        if self.mock:
            return 25.0
        if self._bus is None:
            raise RuntimeError("AMG8833 SMBus not initialized")
        try:
            tthl = self._bus.read_byte_data(self.address, AMG8833_TTHL)
            tthh = self._bus.read_byte_data(self.address, AMG8833_TTHH)
            raw = (tthh << 8) | tthl
            if raw & 0x800:
                raw = raw - 0x1000
            return raw * 0.0625
        except Exception as exc:
            logger.error("AMG8833 thermistor read error: %s", exc)
            return 0.0

    async def close(self) -> None:
        if self._bus is not None:
            try:
                # Sleep mode
                self._bus.write_byte_data(self.address, AMG8833_PCTL, AMG8833_SLEEP_MODE)
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
