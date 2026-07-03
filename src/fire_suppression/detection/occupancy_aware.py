"""Occupancy-aware fire detection with automatic zone arming.

# MOD-008 — Occupancy-Aware Detection

Uses PIR, ultrasonic, or mmWave sensors to detect human presence.
Adjusts detection sensitivity and arming based on occupancy:
- Occupied: Normal sensitivity, immediate alerting
- Unoccupied: Elevated sensitivity (fewer false-positive constraints),
  delayed alerting (reduce nuisance alarms)
- Scheduled: Auto-arm/disarm based on building hours

Hardware: HC-SR501 PIR, RCWL-0516 microwave, or VL53L0X ToF.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

OCCUPANCY_TIMEOUT_SEC = 300  # 5 minutes without motion = unoccupied


@dataclass
class OccupancyState:
    zone: str
    occupied: bool
    occupant_count: int
    last_motion: float
    confidence: float  # 0-1


class OccupancyAwareDetector:
    """Occupancy-aware fire detection system.

    Reduces false alarms in unoccupied spaces by adjusting thresholds.
    Increases detection speed in occupied spaces for life safety.
    """

    def __init__(
        self,
        zones: list[str] | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.zones = zones or ["default"]
        self.mock = mock
        self._occupancy: dict[str, OccupancyState] = {
            z: OccupancyState(z, False, 0, 0.0, 0.0) for z in self.zones
        }
        self._schedule: dict[str, tuple[str, str]] = {}  # zone -> (arm_time, disarm_time)
        self._running = False

        logger.info("OccupancyAwareDetector: %d zones", len(self.zones))

    # ── Occupancy Sensing ───────────────────────────────────────────

    async def _read_occupancy(self, zone: str) -> OccupancyState:
        if self.mock:
            import random
            # Simulate intermittent occupancy
            occupied = random.random() < 0.3
            return OccupancyState(
                zone=zone,
                occupied=occupied,
                occupant_count=random.randint(1, 5) if occupied else 0,
                last_motion=time.time() - random.random() * 600,
                confidence=0.8 if occupied else 0.9,
            )

        try:
            # Try PIR first
            import RPi.GPIO as GPIO  # type: ignore
            pin = 18  # Configurable
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.IN)
            motion = GPIO.input(pin)
            return OccupancyState(
                zone=zone,
                occupied=bool(motion),
                occupant_count=1 if motion else 0,
                last_motion=time.time() if motion else time.time() - 600,
                confidence=0.7,
            )
        except Exception:
            logger.exception("Occupancy read failed for %s", zone)
            return OccupancyState(zone, False, 0, 0, 0.0)

    async def update_occupancy(self) -> None:
        """Poll all zones for occupancy status."""
        for zone in self.zones:
            state = await self._read_occupancy(zone)
            # Timeout: if no motion for OCCUPANCY_TIMEOUT_SEC, mark unoccupied
            if state.occupied and time.time() - state.last_motion > OCCUPANCY_TIMEOUT_SEC:
                state.occupied = False
                state.occupant_count = 0
            self._occupancy[zone] = state

    # ── Sensitivity Adjustment ───────────────────────────────────────

    def get_adjusted_thresholds(self, zone: str, base_thresholds: dict) -> dict:
        """Adjust detection thresholds based on occupancy."""
        state = self._occupancy.get(zone, OccupancyState(zone, False, 0, 0, 0.0))
        adjusted = dict(base_thresholds)

        if state.occupied:
            # Occupied: normal sensitivity for life safety
            adjusted["smoke_warning"] *= 1.0
            adjusted["smoke_alert"] *= 1.0
            adjusted["temp_rise_rate"] *= 1.0
            adjusted["alert_delay_sec"] = 0  # Immediate
        else:
            # Unoccupied: relaxed thresholds (fewer false alarms)
            adjusted["smoke_warning"] *= 1.3
            adjusted["smoke_alert"] *= 1.2
            adjusted["temp_rise_rate"] *= 1.2
            adjusted["alert_delay_sec"] = 30  # 30s confirmation delay

        # Schedule override
        if zone in self._schedule:
            arm_time, disarm_time = self._schedule[zone]
            now = time.strftime("%H:%M")
            if arm_time <= now < disarm_time:
                # Armed period
                adjusted["armed"] = True
            else:
                adjusted["armed"] = False

        adjusted["occupancy_adjusted"] = True
        adjusted["zone_occupied"] = state.occupied
        adjusted["occupant_count"] = state.occupant_count
        return adjusted

    def set_schedule(self, zone: str, arm_time: str, disarm_time: str) -> None:
        """Set automatic arm/disarm schedule for zone (HH:MM format)."""
        self._schedule[zone] = (arm_time, disarm_time)
        logger.info("Zone '%s' schedule: armed %s-%s", zone, arm_time, disarm_time)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        while self._running:
            await self.update_occupancy()
            await asyncio.sleep(10)  # Poll every 10 seconds

    async def stop(self) -> None:
        self._running = False

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "zones": self.zones,
            "occupancy": {
                z: {
                    "occupied": s.occupied,
                    "occupant_count": s.occupant_count,
                    "last_motion": s.last_motion,
                }
                for z, s in self._occupancy.items()
            },
            "schedules": self._schedule,
            "mock": self.mock,
        }
