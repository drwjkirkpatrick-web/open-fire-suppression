"""MLX90640 32×24 thermal camera sensor driver.

# S009 — MLX90640 Thermal Camera
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

MLX90640_I2C_ADDRESS = 0x33

# EEPROM addresses (832 bytes of calibration data)
MLX90640_EEPROM_START = 0x2400
MLX90640_EEPROM_SIZE = 832

# Frame buffer addresses
MLX90640_FRAME0 = 0x0400  # 832 bytes
MLX90640_FRAME1 = 0x0700  # 832 bytes
MLX90640_STATUS_REG = 0x8000
MLX90640_CONTROL_REG = 0x800D
MLX90640_I2C_CONFIG = 0x800F

# Frame rate settings
MLX90640_FPS_1HZ = 0x01
MLX90640_FPS_2HZ = 0x02
MLX90640_FPS_4HZ = 0x03
MLX90640_FPS_8HZ = 0x04
MLX90640_FPS_16HZ = 0x05
MLX90640_FPS_32HZ = 0x06
MLX90640_FPS_64HZ = 0x07

# Subpage flags
MLX90640_NEW_DATA = 0x0008
MLX90640_PAGE_FLAG = 0x0001


class MLX90640Sensor(BaseSensor):
    """Melexis MLX90640 32×24 thermal infrared array sensor.

    Higher resolution thermal camera (768 pixels) compared to AMG8833.
    Requires higher I2C speed (400kHz or 1MHz) for reliable operation.

    Note: Full calibration and temperature compensation are complex.
    For production use, consider the ``pimoroni`` or ``adafruit``
    MLX90640 Python libraries which include complete compensation.
    """

    def __init__(
        self,
        name: str = "mlx90640",
        *,
        bus_number: int = 1,
        address: int = MLX90640_I2C_ADDRESS,
        fps: int = 8,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.address = address
        self.fps = fps
        self._bus = None
        self._eeprom: list[int] = []

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
                self._read_eeprom()
                self._configure()
            except Exception as exc:
                logger.error("MLX90640 init failed: %s", exc)
                self._bus = None

    def _read_eeprom(self) -> None:
        """Read the 832-byte EEPROM calibration data."""
        if self._bus is None:
            return
        try:
            # MLX90640 EEPROM is at 0x2400–0x273F
            # Read in chunks (SMBus has a 32-byte limit per transaction)
            eeprom = []
            for offset in range(0, MLX90640_EEPROM_SIZE, 32):
                addr = MLX90640_EEPROM_START + offset
                chunk_size = min(32, MLX90640_EEPROM_SIZE - offset)
                chunk = self._bus.read_i2c_block_data(self.address, addr, chunk_size)
                eeprom.extend(chunk)
            self._eeprom = eeprom
            logger.info("MLX90640 EEPROM read: %d bytes", len(self._eeprom))
        except Exception as exc:
            logger.warning("MLX90640 EEPROM read failed: %s", exc)
            self._eeprom = []

    def _configure(self) -> None:
        if self._bus is None:
            return
        try:
            # Set frame rate
            fps_map = {1: MLX90640_FPS_1HZ, 2: MLX90640_FPS_2HZ, 4: MLX90640_FPS_4HZ,
                       8: MLX90640_FPS_8HZ, 16: MLX90640_FPS_16HZ, 32: MLX90640_FPS_32HZ,
                       64: MLX90640_FPS_64HZ}
            fps_reg = fps_map.get(self.fps, MLX90640_FPS_8HZ)
            self._bus.write_word_data(self.address, MLX90640_CONTROL_REG, fps_reg)
            time.sleep(0.01)
        except Exception:
            pass

    async def read(self) -> SensorReading:
        if self.mock:
            # Generate a 32×24 grid with a hotspot
            grid = [25.0] * 768
            # Hotspot near center
            for r in range(10, 14):
                for c in range(14, 18):
                    idx = r * 32 + c
                    grid[idx] = 80.0
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={f"pixel_{i:03d}": v for i, v in enumerate(grid)},
                raw=grid,
                unit="°C",
            )

        if self._bus is None:
            raise RuntimeError("MLX90640 SMBus not initialized")

        try:
            # Read frame data (simplified — full compensation would use EEPROM)
            # For this implementation, we do a raw read without full temp compensation
            # Production code should use adafruit/pimoroni libraries

            # Check which subpage is available
            status = self._read_register(MLX90640_STATUS_REG)
            new_data = bool(status & MLX90640_NEW_DATA)
            subpage = status & MLX90640_PAGE_FLAG

            if not new_data:
                time.sleep(0.01)
                status = self._read_register(MLX90640_STATUS_REG)
                new_data = bool(status & MLX90640_NEW_DATA)

            # Read frame buffer
            frame_addr = MLX90640_FRAME0 if subpage == 0 else MLX90640_FRAME1
            frame = []
            for offset in range(0, 832, 32):
                addr = frame_addr + offset
                chunk_size = min(32, 832 - offset)
                chunk = self._bus.read_i2c_block_data(self.address, addr, chunk_size)
                frame.extend(chunk)

            # Parse pixel data (simplified — each pixel is 16-bit raw)
            temperatures: list[float] = []
            values: dict[str, float] = {}

            for i in range(768):
                raw = (frame[i * 2 + 1] << 8) | frame[i * 2]
                # Simplified conversion (would normally use EEPROM calibration)
                # Approximate: raw value to temperature (very rough)
                temp = (raw - 27315) / 100.0  # Very approximate
                temp = max(-40.0, min(300.0, temp))
                temperatures.append(temp)
                values[f"pixel_{i:03d}"] = round(temp, 2)

            # Clear new data flag
            self._bus.write_word_data(self.address, MLX90640_STATUS_REG, status & ~MLX90640_NEW_DATA)

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values=values,
                raw=temperatures,
                unit="°C",
            )

        except Exception as exc:
            logger.error("MLX90640 read error: %s", exc)
            raise

    def _read_register(self, reg: int) -> int:
        if self._bus is None:
            return 0
        try:
            data = self._bus.read_word_data(self.address, reg)
            return ((data & 0xFF) << 8) | ((data >> 8) & 0xFF)
        except Exception:
            return 0

    async def close(self) -> None:
        if self._bus is not None:
            try:
                # Stop measurements
                self._bus.write_word_data(self.address, MLX90640_CONTROL_REG, 0x00)
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
