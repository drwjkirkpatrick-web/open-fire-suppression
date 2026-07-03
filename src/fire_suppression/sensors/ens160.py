"""ENS160 VOC / air quality sensor driver.

# S007 — ENS160 VOC / Air Quality
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

ENS160_I2C_ADDRESS = 0x53

# ENS160 registers
ENS160_PART_ID = 0x00
ENS160_OPMODE = 0x10
ENS160_CONFIG = 0x11
ENS160_COMMAND = 0x12
ENS160_TEMP_IN = 0x13
ENS160_RH_IN = 0x15
ENS160_STATUS = 0x20
ENS160_AQI = 0x21
ENS160_TVOC = 0x22
ENS160_ECO2 = 0x24
ENS160_BASELINE = 0x26
ENS160_DATA_N = 0x28
ENS160_DATA_A = 0x30
ENS160_DATA_T = 0x38
ENS160_DATA_M = 0x40
ENS160_GPR_READ = 0x48
ENS160_GPR_WRITE = 0x50

# Operating modes
ENS160_OPMODE_DEEP_SLEEP = 0x00
ENS160_OPMODE_IDLE = 0x01
ENS160_OPMODE_STANDARD = 0x02
ENS160_OPMODE_RESET = 0xF0

# Status flags
ENS160_STATUS_NEWDAT = 0x02
ENS160_STATUS_NEWGPR = 0x01
ENS160_STATUS_VALIDITY = 0x0C  # 0=normal, 4=warmup, 8=initial startup

# Warmup states
ENS160_VALIDITY_NORMAL = 0x00
ENS160_VALIDITY_WARMUP = 0x04
ENS160_VALIDITY_INITIAL = 0x08


class ENS160Sensor(BaseSensor):
    """ScioSense ENS160 digital multi-gas sensor.

    Replaces the older CCS811 with more stable readings.
    Reports TVOC (total volatile organic compounds), eCO2 (equivalent CO2),
    and an air quality index (AQI 1–5).
    """

    def __init__(
        self,
        name: str = "ens160",
        *,
        bus_number: int = 1,
        address: int = ENS160_I2C_ADDRESS,
        warmup_seconds: int = 30,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.address = address
        self.warmup_seconds = warmup_seconds
        self._bus = None
        self._start_time = time.time()

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
                self._reset()
                self._set_standard_mode()
            except Exception as exc:
                logger.error("ENS160 init failed: %s", exc)
                self._bus = None

    def _reset(self) -> None:
        if self._bus is None:
            return
        try:
            self._bus.write_byte_data(self.address, ENS160_OPMODE, ENS160_OPMODE_RESET)
            time.sleep(0.2)
        except Exception:
            pass

    def _set_standard_mode(self) -> None:
        if self._bus is None:
            return
        try:
            self._bus.write_byte_data(self.address, ENS160_OPMODE, ENS160_OPMODE_STANDARD)
            time.sleep(0.01)
        except Exception:
            pass

    @property
    def is_warmed_up(self) -> bool:
        return time.time() - self._start_time >= self.warmup_seconds

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "tvoc_ppb": 50.0,
                    "eco2_ppm": 400.0,
                    "aqi": 1,
                    "status": "normal",
                    "warmed_up": True,
                },
                raw=None,
                unit="ppb / ppm / index",
            )

        if self._bus is None:
            raise RuntimeError("ENS160 SMBus not initialized")

        try:
            # Read status
            status = self._bus.read_byte_data(self.address, ENS160_STATUS)
            new_data = bool(status & ENS160_STATUS_NEWDAT)
            validity = status & ENS160_STATUS_VALIDITY

            if validity == ENS160_VALIDITY_INITIAL:
                status_str = "initial_startup"
            elif validity == ENS160_VALIDITY_WARMUP:
                status_str = "warmup"
            elif validity == ENS160_VALIDITY_NORMAL:
                status_str = "normal"
            else:
                status_str = f"unknown_{validity}"

            if not new_data and validity == ENS160_VALIDITY_NORMAL:
                # No new data but sensor is ready — re-read
                time.sleep(0.01)
                status = self._bus.read_byte_data(self.address, ENS160_STATUS)
                new_data = bool(status & ENS160_STATUS_NEWDAT)

            # Read data registers
            aqi = self._bus.read_byte_data(self.address, ENS160_AQI)
            tvoc_raw = self._bus.read_word_data(self.address, ENS160_TVOC)
            eco2_raw = self._bus.read_word_data(self.address, ENS160_ECO2)

            # Fix endianness (little-endian from sensor)
            tvoc = ((tvoc_raw & 0xFF) << 8) | ((tvoc_raw >> 8) & 0xFF)
            eco2 = ((eco2_raw & 0xFF) << 8) | ((eco2_raw >> 8) & 0xFF)

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "tvoc_ppb": tvoc,
                    "eco2_ppm": eco2,
                    "aqi": aqi,
                    "status": status_str,
                    "warmed_up": self.is_warmed_up,
                    "new_data": new_data,
                },
                raw={"status_byte": status, "tvoc_raw": tvoc_raw, "eco2_raw": eco2_raw},
                unit="ppb / ppm / index",
            )

        except Exception as exc:
            logger.error("ENS160 read error: %s", exc)
            raise

    async def close(self) -> None:
        if self._bus is not None:
            try:
                # Put sensor to sleep before closing
                self._bus.write_byte_data(self.address, ENS160_OPMODE, ENS160_OPMODE_DEEP_SLEEP)
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
