"""MQ-2 smoke and combustible gas sensor driver (via ADS1115).

# S003 — MQ-2 Smoke Sensor Calibration
"""
from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# MQ-2 typical load resistance (datasheet value; adjustable via potentiometer on module)
MQ2_RL = 10000.0  # ohms

# Calibration curves (from MQ-2 datasheet, log-log scale)
# Rs/R0 = a * (ppm)^b  →  ppm = (Rs/(R0*a))^(1/b)
MQ2_CURVES = {
    "lpg": {"a": 947.0, "b": -2.32},
    "propane": {"a": 947.0, "b": -2.32},
    "methane": {"a": 1096.0, "b": -2.67},
    "smoke": {"a": 322.0, "b": -2.47},
    "hydrogen": {"a": 987.0, "b": -2.27},
}


class MQ2Sensor(BaseSensor):
    """MQ-2 smoke and gas sensor using ADS1115 for analog-to-digital conversion.

    The MQ-2 requires ~60 seconds of warm-up after power-on for stable readings.
    R0 (resistance in clean air) must be calibrated in fresh air before use.
    """

    def __init__(
        self,
        name: str = "mq2",
        *,
        bus_number: int = 1,
        adc_address: int = 0x48,
        adc_channel: int = 0,
        r0: float = 10000.0,  # Calibrated in clean air
        warmup_seconds: int = 60,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.adc_address = adc_address
        self.adc_channel = adc_channel
        self.r0 = r0
        self.warmup_seconds = warmup_seconds
        self._bus = None
        self._start_time = time.time()

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
            except Exception as exc:
                logger.error("MQ-2 init failed: %s", exc)
                self._bus = None

    @property
    def is_warmed_up(self) -> bool:
        return time.time() - self._start_time >= self.warmup_seconds

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "rs": 15000.0,
                    "rs_over_r0": 1.5,
                    "lpg_ppm": 100.0,
                    "methane_ppm": 80.0,
                    "smoke_ppm": 120.0,
                    "hydrogen_ppm": 60.0,
                    "voltage": 2.5,
                    "warmed_up": True,
                },
                raw={"voltage": 2.5, "rs": 15000.0},
                unit="ppm / V / Ω",
            )

        if self._bus is None:
            raise RuntimeError("MQ-2 SMBus not initialized")

        try:
            voltage = self._read_adc_voltage()
            rs = self._calculate_rs(voltage)
            ratio = rs / self.r0 if self.r0 > 0 else 0.0

            values: dict[str, float | bool] = {
                "rs": round(rs, 1),
                "rs_over_r0": round(ratio, 3),
                "voltage": round(voltage, 3),
                "warmed_up": self.is_warmed_up,
            }

            if self.is_warmed_up:
                for gas, params in MQ2_CURVES.items():
                    ppm = self._ratio_to_ppm(ratio, params["a"], params["b"])
                    values[f"{gas}_ppm"] = round(ppm, 1)
            else:
                # During warmup, just report raw values
                for gas in MQ2_CURVES:
                    values[f"{gas}_ppm"] = -1.0

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values=values,
                raw={"voltage": voltage, "rs": rs},
                unit="ppm / V / Ω",
            )

        except Exception as exc:
            logger.error("MQ-2 read error: %s", exc)
            raise

    def _read_adc_voltage(self) -> float:
        """Read voltage from ADS1115 via direct SMBus (simplified)."""
        if self._bus is None:
            return 0.0
        # Simplified ADS1115 single-shot read
        import struct

        # Config: OS=1, MUX=AIN0, PGA=±4.096V, MODE=single-shot, DR=128SPS
        config = 0xC283  # OS=1, MUX=100 (AIN0), PGA=001 (±4.096V), MODE=1, DR=100 (128SPS)
        try:
            self._bus.write_i2c_block_data(
                self.adc_address, 0x01, [(config >> 8) & 0xFF, config & 0xFF]
            )
            time.sleep(0.01)
            result = self._bus.read_i2c_block_data(self.adc_address, 0x00, 2)
            raw = struct.unpack(">h", bytes(result))[0]
            # Convert to voltage: ±4.096V full scale, 16-bit
            return (raw / 32767.0) * 4.096
        except Exception:
            return 0.0

    @staticmethod
    def _calculate_rs(voltage: float, vcc: float = 5.0, rl: float = MQ2_RL) -> float:
        """Calculate sensor resistance from ADC voltage reading."""
        if voltage <= 0:
            return float("inf")
        return rl * ((vcc / voltage) - 1.0)

    @staticmethod
    def _ratio_to_ppm(ratio: float, a: float, b: float) -> float:
        """Convert Rs/R0 ratio to ppm using datasheet log-log curve."""
        if ratio <= 0:
            return 0.0
        return math.pow(ratio / a, 1.0 / b)

    async def calibrate_r0(self, samples: int = 100) -> float:
        """Calibrate R0 in clean air by averaging readings.

        Call this in clean air conditions before deploying.
        Returns the calculated R0 value.
        """
        if self.mock:
            return 10000.0

        readings: list[float] = []
        for _ in range(samples):
            voltage = self._read_adc_voltage()
            rs = self._calculate_rs(voltage)
            readings.append(rs)
            time.sleep(0.1)

        r0 = sum(readings) / len(readings) if readings else MQ2_RL
        self.r0 = r0
        logger.info("MQ-2 calibrated: R0 = %.1f Ω (from %d samples)", r0, samples)
        return r0

    async def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
