"""Thermal-camera-based water mist targeting system.

# IMP-009 — Water Mist Zone Targeting

Uses thermal camera hotspot data to estimate fire location and activate
the suppression nozzle(s) closest to the fire centroid.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class NozzlePosition:
    """Physical position of a suppression nozzle in camera pixel space."""
    name: str
    row: float  # Thermal camera row coordinate
    col: float  # Thermal camera column coordinate
    relay_index: int
    spray_angle_deg: float = 0.0  # Direction nozzle sprays (0 = straight ahead)
    spray_range_px: float = 50.0   # Effective spray radius in thermal pixels


@dataclass
class TargetingResult:
    """Result of fire targeting calculation."""
    hotspots_detected: int
    target_nozzles: list[int]  # Relay indices to activate
    target_centroid: tuple[float, float] | None
    distance_to_closest: float | None


class WaterMistTargeter:
    """Maps thermal hotspots to physical nozzle positions for targeted suppression.

    Usage::

        targeter = WaterMistTargeter()
        targeter.add_nozzle(NozzlePosition("north", row=4, col=2, relay_index=0))
        targeter.add_nozzle(NozzlePosition("south", row=12, col=5, relay_index=1))

        result = targeter.target(hotspots=[{"centroid_row": 5, "centroid_col": 3, "size": 4}])
        # result.target_nozzles = [0]  # Activate north nozzle
    """

    def __init__(self, thermal_rows: int = 8, thermal_cols: int = 8) -> None:
        self.thermal_rows = thermal_rows
        self.thermal_cols = thermal_cols
        self._nozzles: list[NozzlePosition] = []

    def add_nozzle(self, nozzle: NozzlePosition) -> None:
        """Register a suppression nozzle with its thermal camera position."""
        self._nozzles.append(nozzle)
        logger.info("Nozzle registered: %s at (%.1f, %.1f) → relay %d",
                    nozzle.name, nozzle.row, nozzle.col, nozzle.relay_index)

    def target(self, hotspots: list[dict]) -> TargetingResult:
        """Calculate which nozzles to activate for the given hotspots.

        Args:
            hotspots: List of hotspot dicts with ``centroid_row``, ``centroid_col``, ``size``.

        Returns:
            TargetingResult with relay indices and targeting metadata.
        """
        if not hotspots or not self._nozzles:
            return TargetingResult(
                hotspots_detected=len(hotspots),
                target_nozzles=list(range(len(self._nozzles))) if not hotspots else [],
                target_centroid=None,
                distance_to_closest=None,
            )

        # Find the largest hotspot (primary fire)
        primary = max(hotspots, key=lambda h: h.get("size", 0))
        centroid = (primary["centroid_row"], primary["centroid_col"])

        # Find closest nozzle(s)
        distances = []
        for nozzle in self._nozzles:
            dist = math.sqrt(
                (nozzle.row - centroid[0]) ** 2 +
                (nozzle.col - centroid[1]) ** 2
            )
            distances.append((dist, nozzle))

        distances.sort(key=lambda x: x[0])
        closest_dist, closest_nozzle = distances[0]

        # Activate nozzle if within spray range
        target_nozzles = []
        if closest_dist <= closest_nozzle.spray_range_px:
            target_nozzles.append(closest_nozzle.relay_index)
            logger.info("Targeting nozzle %s for hotspot at (%.1f, %.1f) (dist=%.1fpx)",
                        closest_nozzle.name, centroid[0], centroid[1], closest_dist)
        else:
            # Fire too far from any nozzle — activate all as fallback
            target_nozzles = [n.relay_index for n in self._nozzles]
            logger.warning("Hotspot at (%.1f, %.1f) beyond nozzle range — activating all nozzles",
                           centroid[0], centroid[1])

        # Also activate adjacent nozzles if fire is spreading
        if len(distances) > 1:
            second_dist, second_nozzle = distances[1]
            if second_dist <= second_nozzle.spray_range_px * 1.5:
                target_nozzles.append(second_nozzle.relay_index)
                logger.info("Also targeting adjacent nozzle %s", second_nozzle.name)

        return TargetingResult(
            hotspots_detected=len(hotspots),
            target_nozzles=list(set(target_nozzles)),
            target_centroid=centroid,
            distance_to_closest=closest_dist,
        )

    def get_nozzle_positions(self) -> list[dict]:
        """Return all registered nozzle positions."""
        return [
            {
                "name": n.name,
                "row": n.row,
                "col": n.col,
                "relay_index": n.relay_index,
            }
            for n in self._nozzles
        ]
