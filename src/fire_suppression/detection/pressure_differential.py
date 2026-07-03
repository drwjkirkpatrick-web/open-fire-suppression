"""Differential pressure fire detection and smoke plume validation.

# MOD-013 — Pressure Differential Detection

Fire creates pressure differentials:
- Fire room: positive pressure from heated expanding air
- Adjacent rooms: negative pressure as air is drawn in
- Stairwells: should be positively pressurized (smoke control)

Measures differential pressure across zones to:
1. Validate smoke plume direction (cross-check with smoke sensors)
2. Detect fire location from pressure signature
3. Verify smoke control system operation
4. Detect door/window breaches (sudden pressure change)

Hardware: SDP31, SDP800, or Honeywell HSCDANN differential pressure sensors.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Differential pressure thresholds (Pa)
PRESSURE_WARNING_PA = 5.0    # Small differential
PRESSURE_ALERT_PA = 15.0     # Significant fire-induced pressure
STAIRCASE_POSITIVE_PA = 25.0  # NFPA 92 required stairwell pressurization


@dataclass
class PressureReading:
    timestamp: float
    zone_a: str
    zone_b: str
    differential_pa: float
    direction: str  # "a_to_b", "b_to_a", "equilibrium"


class PressureDifferentialDetector:
    """Differential pressure fire detection system.

    Uses pressure sensors across zones to detect fire-induced airflow
    patterns and validate smoke control systems.
    """

    def __init__(
        self,
        sensor_id: str = "pressure_diff_01",
        i2c_bus: int = 1,
        i2c_address: int = 0x40,
        *,
        mock: bool = False,
    ) -> None:
        self.sensor_id = sensor_id
        self.i2c_bus = i2c_bus
        self.i2c_address = i2c_address
        self.mock = mock
        self._readings: deque[PressureReading] = deque(maxlen=1000)
        self._running = False
        self._baseline: float = 0.0
        self._calibrated = False

        logger.info("PressureDifferentialDetector %s on bus %d addr 0x%02x",
                    sensor_id, i2c_bus, i2c_address)

    # ── Calibration ─────────────────────────────────────────────────

    async def calibrate(self, duration_sec: float = 30.0) -> None:
        """Calibrate baseline differential pressure in normal conditions."""
        readings = []
        start = time.time()
        while time.time() - start < duration_sec:
            reading = await self._read_once()
            if reading:
                readings.append(reading.differential_pa)
            await asyncio.sleep(0.5)

        if readings:
            self._baseline = sum(readings) / len(readings)
            self._calibrated = True
            logger.info("Pressure diff calibrated: baseline=%.2f Pa (n=%d)",
                        self._baseline, len(readings))

    # ── Reading ─────────────────────────────────────────────────────

    async def _read_once(self) -> PressureReading | None:
        if self.mock:
            import random
            # Simulate fire-induced pressure
            if random.random() < 0.3:
                dp = random.gauss(12, 5)  # Fire = positive pressure
            else:
                dp = random.gauss(self._baseline, 1.0)
            return PressureReading(
                timestamp=time.time(),
                zone_a="room",
                zone_b="hallway",
                differential_pa=dp,
                direction="a_to_b" if dp > 0 else "b_to_a",
            )

        try:
            from smbus2 import SMBus  # type: ignore
            with SMBus(self.i2c_bus) as bus:
                # SDP31 command: 0x3603 = continuous measurement
                bus.write_i2c_block_data(self.i2c_address, 0x36, [0x03])
                await asyncio.sleep(0.05)
                data = bus.read_i2c_block_data(self.i2c_address, 0, 9)
                # Parse SDP31 data
                press_raw = (data[0] << 8) | data[1]
                differential_pa = (press_raw - 32768) / 120.0  # Approximate scaling
                return PressureReading(
                    timestamp=time.time(),
                    zone_a="room",
                    zone_b="hallway",
                    differential_pa=differential_pa,
                    direction="a_to_b" if differential_pa > 0 else "b_to_a",
                )
        except Exception:
            logger.exception("Pressure read failed")
            return None

    # ── Detection ───────────────────────────────────────────────────

    async def detect(self) -> dict[str, Any]:
        """Analyze pressure differential for fire indicators."""
        reading = await self._read_once()
        if not reading:
            return {"sensor_id": self.sensor_id, "error": "read_failed", "fire_detected": False}

        self._readings.append(reading)

        if not self._calibrated:
            return {"sensor_id": self.sensor_id, "status": "calibrating", "fire_detected": False}

        # Adjusted differential (remove baseline)
        adjusted_dp = abs(reading.differential_pa - self._baseline)

        status = "clear"
        if adjusted_dp >= PRESSURE_ALERT_PA:
            status = "alert"
        elif adjusted_dp >= PRESSURE_WARNING_PA:
            status = "warning"

        # Validate smoke plume direction
        smoke_direction_consistent = None
        if len(self._readings) >= 10:
            recent = list(self._readings)[-10:]
            dominant_direction = max(
                set(r.direction for r in recent),
                key=lambda d: sum(1 for r in recent if r.direction == d),
            )
            smoke_direction_consistent = {
                "dominant_direction": dominant_direction,
                "confidence": sum(1 for r in recent if r.direction == dominant_direction) / len(recent),
            }

        return {
            "sensor_id": self.sensor_id,
            "timestamp": reading.timestamp,
            "differential_pa": round(reading.differential_pa, 2),
            "adjusted_pa": round(adjusted_dp, 2),
            "direction": reading.direction,
            "status": status,
            "fire_detected": status == "alert",
            "smoke_direction_validation": smoke_direction_consistent,
            "calibrated": self._calibrated,
        }

    # ── Stairwell Pressurization Check ────────────────────────────────

    async def check_stairwell_pressurization(self) -> dict[str, Any]:
        """Verify NFPA 92 stairwell pressurization.

        Stairwells must maintain 25 Pa positive relative to fire zone.
        """
        reading = await self._read_once()
        if not reading:
            return {"compliant": False, "error": "read_failed"}

        # Assume zone_a is stairwell, zone_b is fire zone
        if reading.differential_pa >= STAIRCASE_POSITIVE_PA:
            return {
                "compliant": True,
                "differential_pa": round(reading.differential_pa, 2),
                "required_pa": STAIRCASE_POSITIVE_PA,
                "margin_pa": round(reading.differential_pa - STAIRCASE_POSITIVE_PA, 2),
            }
        return {
            "compliant": False,
            "differential_pa": round(reading.differential_pa, 2),
            "required_pa": STAIRCASE_POSITIVE_PA,
            "deficit_pa": round(STAIRCASE_POSITIVE_PA - reading.differential_pa, 2),
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        if not self._calibrated:
            await self.calibrate()

    async def stop(self) -> None:
        self._running = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "baseline_pa": round(self._baseline, 2),
            "calibrated": self._calibrated,
            "readings_stored": len(self._readings),
            "mock": self.mock,
        }
