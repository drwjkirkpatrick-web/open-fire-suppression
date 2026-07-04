"""V9-009 — Geo-Tagged Zone Configuration

Adds optional GPS coordinates to detection zones and computes distance/bearing
between zones. Useful for campuses, multi-building sites, or wildfire-adjacent
installations.

Personality: *Calcarea Carbonica* — the infrastructure guardian. Structural,
location-aware, and grounded.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


@dataclass
class GeoZone:
    """A detection zone with optional geographic coordinates."""

    zone_id: str
    name: str
    lat: float | None = None
    lon: float | None = None
    altitude_m: float | None = None
    radius_m: float = 10.0
    tags: list[str] = field(default_factory=list)


class GeoZoneManager:
    """Manage zones that carry GPS coordinates for public situational feeds."""

    PERSONALITY = "Calcarea Carbonica"

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._zones: dict[str, GeoZone] = {}
        self._load_from_config()

    def _load_from_config(self) -> None:
        """Load geo zones from config detection.zones list if present."""
        zones_cfg = self.config.section("detection").get("zones", [])
        for z in zones_cfg:
            if isinstance(z, dict):
                gz = GeoZone(
                    zone_id=str(z.get("id") or z.get("name") or "unknown"),
                    name=str(z.get("name", "unnamed")),
                    lat=_to_float(z.get("lat")),
                    lon=_to_float(z.get("lon")),
                    altitude_m=_to_float(z.get("altitude_m")),
                    radius_m=float(z.get("radius_m", 10.0)),
                    tags=list(z.get("tags", [])),
                )
                self._zones[gz.zone_id] = gz

        # Seed a few demo zones if nothing configured.
        if not self._zones:
            self._zones["main"] = GeoZone("main", "Main Building", lat=0.0, lon=0.0)
            self._zones["warehouse"] = GeoZone("warehouse", "Warehouse", lat=0.001, lon=0.001)

    def add_zone(self, zone: GeoZone) -> None:
        self._zones[zone.zone_id] = zone

    def get_zone(self, zone_id: str) -> GeoZone | None:
        return self._zones.get(zone_id)

    def list_zones(self) -> list[dict[str, Any]]:
        return [self._zone_to_dict(z) for z in self._zones.values()]

    @staticmethod
    def haversine(a: GeoZone, b: GeoZone) -> dict[str, float]:
        """Return distance (m) and bearing (degrees) from a to b."""
        if a.lat is None or a.lon is None or b.lat is None or b.lon is None:
            return {"distance_m": -1.0, "bearing_deg": -1.0}

        R = 6_371_000  # Earth radius in meters
        phi1 = math.radians(a.lat)
        phi2 = math.radians(b.lat)
        dphi = math.radians(b.lat - a.lat)
        dlambda = math.radians(b.lon - a.lon)

        h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        distance = 2 * R * math.asin(math.sqrt(h))

        y = math.sin(dlambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
        bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

        return {"distance_m": round(distance, 1), "bearing_deg": round(bearing, 1)}

    def situational_feed(self, reference_zone_id: str | None = None) -> dict[str, Any]:
        """Public feed of zones with relative distance/bearing from a reference."""
        zones = list(self._zones.values())
        reference = self._zones.get(reference_zone_id) or (zones[0] if zones else None)
        feed: list[dict[str, Any]] = []
        for z in zones:
            item = self._zone_to_dict(z)
            if reference and z.zone_id != reference.zone_id:
                item["relative"] = self.haversine(reference, z)
            feed.append(item)
        return {
            "personality": self.PERSONALITY,
            "reference_zone": reference.zone_id if reference else None,
            "zones": feed,
            "zone_count": len(feed),
        }

    def _zone_to_dict(self, zone: GeoZone) -> dict[str, Any]:
        return {
            "zone_id": zone.zone_id,
            "name": zone.name,
            "lat": zone.lat,
            "lon": zone.lon,
            "altitude_m": zone.altitude_m,
            "radius_m": zone.radius_m,
            "tags": zone.tags,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "personality": self.PERSONALITY,
            "zone_count": len(self._zones),
            "zones": self.list_zones(),
        }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
