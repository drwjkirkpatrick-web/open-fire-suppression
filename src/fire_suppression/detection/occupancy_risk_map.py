"""V7-009 — Occupancy-Aware Risk Map

Builds a real-time per-zone risk score combining occupancy, sensor readings,
and fire state. Drives LED evacuation routing and dashboard heatmaps.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class OccupancyAwareRiskMap:
    """Real-time per-zone risk map using occupancy and sensor fusion."""

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        cfg = self.config.section("risk_map")
        self.fire_weight = float(cfg.get("fire_weight", 0.5))
        self.occupancy_weight = float(cfg.get("occupancy_weight", 0.2))
        self.smoke_weight = float(cfg.get("smoke_weight", 0.15))
        self.heat_weight = float(cfg.get("heat_weight", 0.15))
        self._zones: dict[str, dict[str, Any]] = {}

    def update_zone(
        self,
        zone_id: str,
        occupancy: int = 0,
        fire_state: str = "clear",
        smoke_ppm: float = 0.0,
        heat_c: float = 0.0,
        exits: list[str] | None = None,
    ) -> dict[str, Any]:
        # Heat score only contributes when above ambient 20C
        heat_score = min(max((heat_c - 20.0) / 60.0, 0.0), 1.0) if heat_c > 20.0 else 0.0
        smoke_score = min(smoke_ppm / 300.0, 1.0)
        occupancy_score = min(occupancy / 10.0, 1.0)
        fire_score = {"clear": 0.0, "warning": 0.5, "alert": 0.9, "confirmed": 1.0}.get(fire_state, 0.0)

        risk = (
            self.fire_weight * fire_score +
            self.smoke_weight * smoke_score +
            self.heat_weight * heat_score +
            self.occupancy_weight * occupancy_score
        )
        risk = max(0.0, min(1.0, risk))

        self._zones[zone_id] = {
            "zone_id": zone_id,
            "occupancy": occupancy,
            "fire_state": fire_state,
            "smoke_ppm": round(smoke_ppm, 2),
            "heat_c": round(heat_c, 2),
            "risk": round(risk, 3),
            "exits": exits or [],
            "updated_at": time.time(),
        }
        return self._zones[zone_id]

    def safest_exit(self, zone_id: str) -> str | None:
        """Choose the lowest-risk adjacent exit for a zone."""
        zone = self._zones.get(zone_id)
        if not zone:
            return None
        exits = zone.get("exits", [])
        if not exits:
            return None
        best = min(exits, key=lambda e: self._zones.get(e, {}).get("risk", 1.0))
        return best

    def global_risk(self) -> float:
        if not self._zones:
            return 0.0
        return max(z.get("risk", 0.0) for z in self._zones.values())

    def risk_report(self) -> dict[str, Any]:
        sorted_zones = sorted(self._zones.values(), key=lambda z: -z["risk"])
        return {
            "feature_id": "V7-009",
            "global_risk": round(self.global_risk(), 3),
            "zone_count": len(self._zones),
            "zones": sorted_zones,
            "timestamp": time.time(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-009",
            "healthy": True,
            "weights": {
                "fire": self.fire_weight,
                "occupancy": self.occupancy_weight,
                "smoke": self.smoke_weight,
                "heat": self.heat_weight,
            },
            "zone_count": len(self._zones),
            "mock": self.mock,
        }
