"""ADS1115 16-bit ADC sensor driver.

# S002 — ADS1115 ADC Reading
"""
from __future__ import annotations

import logging
import struct
import time
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading

if TYPE_CHECKING:
    pass  # smbus2 types not strictly needed here

logger = logging.getLogger(__name__)

# ADS1115 register addresses
ADS_POINTER_CONVERSION = 0x00
ADS_POINTER_CONFIG = 0x01

# Config register bit positions
ADS_OS_SINGLE = 0x8000
ADS_MUX_AIN0 = 0x4000  # Differential P=AIN0, N=AIN1
ADS_MUX_AIN1 = 0x5000
ADS_MUX_AIN2 = 0x6000
ADSADS_MUX_AIN3 = 0x7000  # Single-ended AIN3
ADS_MUX_SINGLE_0 = 0x4000
ADS_MUX_SINGLE_1 = 0x5000
ADS_MUX_SINGLE_2 = 0x6000
ADS_MUX_SINGLE_3 = 0x7000

ADS_GAIN_6_144V = 0x0000
ADS_GAIN_4_096V = 0x0200
ADS_GAIN_2_048V = 0x0400
ADS_GAIN_1_024V = 0x0600
ADS_GAIN_0_512V = 0x0800
ADS_GAIN_0_256V = 0x0A00

ADS_MODE_SINGLE = 0x0100
ADS_MODE_CONTINUOUS = 0x0000

ADS_DR_8SPS = 0x0000
ADS_DR_16SPS = 0x0020
ADS_DR_32SPS = 0x0040
ADS_DR_64SPS = 0x0060
ADS_DR_128SPS = 0x0080
ADS_DR_250SPS = 0x00A0
ADS_DR_475SPS = 0x00C0
ADS_DR_860SPS = 0x00E0

# Gain voltage full-scale values (for raw-to-voltage conversion)
GAIN_VOLTAGES = {
    0: 6.144,
    1: 4.096,
    2: 2.048,
    3: 1.024,
    4: 0.512,
    5: 0.256,
}


class ADS1115Sensor(BaseSensor):
    """ADS1115 4-channel 16-bit ADC sensor.

    Reads analog voltages from up to 4 channels. Used for MQ-2 smoke sensor,
    optical dust sensor, and battery voltage monitoring.
    """

    def __init__(
        self,
        name: str = "ads1115",
        *,
        bus_number: int = 1,
        address: int = 0x48,
        gain: int = 1,  # 1 = ±4.096V
        channels: list[int] | None = None,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.address = address
        self.gain = gain
        self.channels = channels if channels is not None else [0, 1, 2, 3]
        self._bus = None
        self._gain_voltage = GAIN_VOLTAGES.get(gain, 4.096)

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
                self._configure()
            except Exception as exc:
                logger.error("ADS1115 init failed: %s", exc)
                self._bus = None

    def _configure(self) -> None:
        """Set default configuration (continuous conversion on channel 0)."""
        if self._bus is None:
            return
        config = (
            ADS_OS_SINGLE
            | ADS_MUX_SINGLE_0
            | (self.gain << 8)
            | ADS_MODE_CONTINUOUS
            | ADS_DR_128SPS
        )
        try:
            self._bus.write_i2c_block_data(
                self.address, ADS_POINTER_CONFIG, [(config >> 8) & 0xFF, config & 0xFF]
            )
        except Exception as exc:
            logger.warning("ADS1115 config write failed: %s", exc)

    async def read(self) -> SensorReading:
        if self.mock:
            values = {f"channel_{ch}": 1.65 + (ch * 0.2) for ch in self.channels}
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values=values,
                raw={ch: values[f"channel_{ch}"] for ch in self.channels},
                unit="V",
            )

        if self._bus is None:
            raise RuntimeError("ADS1115 SMBus not initialized")

        values: dict[str, float] = {}
        raw_values: dict[int, int] = {}

        for ch in self.channels:
            raw = self._read_single(ch)
            voltage = (raw / 32767.0) * self._gain_voltage if raw is not None else 0.0
            values[f"channel_{ch}"] = round(voltage, 4)
            raw_values[ch] = raw if raw is not None else 0

        return SensorReading(
            sensor_name=self.name,
            timestamp=time.time(),
            values=values,
            raw=raw_values,
            unit="V",
        )

    def _read_single(self, channel: int) -> int | None:
        """Trigger a single conversion on *channel* and return raw 16-bit signed value."""
        if self._bus is None:
            return None

        mux_codes = [ADS_MUX_SINGLE_0, ADS_MUX_SINGLE_1, ADS_MUX_SINGLE_2, ADS_MUX_SINGLE_3]
        config = (
            ADS_OS_SINGLE
            | mux_codes[channel]
            | (self.gain << 8)
            | ADS_MODE_SINGLE
            | ADS_DR_128SPS
        )

        try:
            self._bus.write_i2c_block_data(
                self.address, ADS_POINTER_CONFIG, [(config >> 8) & 0xFF, config & 0xFF]
            )
        except Exception:
            return None

        # Wait for conversion (~8ms at 128 SPS)
        time.sleep(0.01)

        try:
            result = self._bus.read_i2c_block_data(self.address, ADS_POINTER_CONVERSION, 2)
            raw = struct.unpack(">h", bytes(result))[0]
            return raw
        except Exception:
            return None

    async def read_channel(self, channel: int) -> float | None:
        """Read a single channel and return voltage (convenience method)."""
        if self.mock:
            return 1.65 + (channel * 0.2)
        raw = self._read_single(channel)
        if raw is None:
            return None
        return round((raw / 32767.0) * self._gain_voltage, 4)

    async def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
