"""Smoke plume direction tracking across multiple sensors.

# ADD-010 — Smoke Plume Direction Tracking

Uses multiple smoke/VOC sensors in different room sectors to
triangulate smoke source direction and velocity.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class SensorPosition:
    """Physical position of a sensor in the room."""
    name: str
    x_m: float  # meters from origin
    y_m: float  # meters from origin
    z_m: float = 0.0


class SmokePlumeTracker:
    """Tracks smoke plume origin and direction from multiple sensors.

    Usage::

        tracker = SmokePlumeTracker()
        tracker.add_sensor(SensorPosition("north", 0, 5))
        tracker.add_sensor(SensorPosition("south", 0, -5))
        tracker.add_sensor(SensorPosition("east", 5, 0))

        result = tracker.update({
            "north": {"smoke_ppm": 50},
            "south": {"smoke_ppm": 10},
            "east": {"smoke_ppm": 30},
        })
        # result = {"origin_estimate": (x, y), "direction_deg": 45, "velocity_ms": 0.5}
    """

    def __init__(self) -> None:
        self._sensors: dict[str, SensorPosition] = {}
        self._history: list[dict] = []

    def add_sensor(self, position: SensorPosition) -> None:
        self._sensors[position.name] = position
        logger.info("Smoke tracker sensor: %s at (%.1f, %.1f)", position.name, position.x_m, position.y_m)

    def update(self, readings: dict[str, dict]) -> dict:
        """Update plume tracking with latest sensor readings.

        Args:
            readings: Dict of sensor_name -> {"smoke_ppm": float, ...}

        Returns:
            Dict with origin_estimate, direction_deg, confidence.
        """
        valid_readings = {
            name: data["smoke_ppm"]
            for name, data in readings.items()
            if name in self._sensors and "smoke_ppm" in data
        }

        if len(valid_readings) < 2:
            return {"origin_estimate": None, "direction_deg": None, "confidence": 0.0}

        # Weighted centroid of highest readings
        total_weight = 0.0
        cx = cy = 0.0
        for name, ppm in valid_readings.items():
            pos = self._sensors[name]
            weight = max(0, ppm)  # Higher ppm = closer to source
            cx += pos.x_m * weight
            cy += pos.y_m * weight
            total_weight += weight

        if total_weight == 0:
            return {"origin_estimate": None, "direction_deg": None, "confidence": 0.0}

        origin = (cx / total_weight, cy / total_weight)

        # Direction from room center to origin
        dx = origin[0]
        dy = origin[1]
        direction_deg = math.degrees(math.atan2(dy, dx))

        # Confidence based on spread of readings
        max_ppm = max(valid_readings.values())
        min_ppm = min(valid_readings.values())
        spread = max_ppm - min_ppm
        confidence = min(1.0, spread / 100.0)  # Normalize

        self._history.append({
            "timestamp": __import__("time").time(),
            "origin": origin,
            "direction_deg": direction_deg,
            "confidence": confidence,
            "readings": valid_readings.copy(),
        })

        return {
            "origin_estimate": origin,
            "direction_deg": direction_deg,
            "confidence": confidence,
            "sensor_count": len(valid_readings),
        }

    def get_history(self, limit: int = 10) -> list[dict]:
        return self._history[-limit:]
