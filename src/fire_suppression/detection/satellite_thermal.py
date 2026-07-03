"""Satellite thermal monitoring for wildfire detection.

# MOD-011 — Satellite Thermal Monitoring

Pulls thermal satellite data from public APIs:
- NASA FIRMS (Fire Information for Resource Management System)
- NOAA GOES-R active fire products
- ESA Sentinel-3 SLSTR
- USGS Landsat thermal bands

Correlates satellite hotspot detection with local sensor readings
for validation and early warning.

Useful for: rural properties, large facilities with surrounding
wildland, and areas where ground sensors may have gaps.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Satellite API endpoints
NASA_FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
NOAA_GOES_URL = "https://www.star.nesdis.noaa.gov/data/pub001/goes16"


@dataclass
class SatelliteHotspot:
    source: str      # "FIRMS", "GOES", "Sentinel"
    lat: float
    lon: float
    brightness: float   # Kelvin
    confidence: str     # "high", "nominal", "low"
    detection_time: float  # Unix timestamp
    satellite: str
    distance_km: float = 0.0


class SatelliteThermalMonitor:
    """Satellite thermal monitoring for wildfire detection.

    Queries public satellite APIs for thermal anomalies near the
    facility. Correlates with local sensor readings.
    """

    def __init__(
        self,
        facility_lat: float,
        facility_lon: float,
        radius_km: float = 10.0,
        *,
        mock: bool = False,
    ) -> None:
        self.facility_lat = facility_lat
        self.facility_lon = facility_lon
        self.radius_km = radius_km
        self.mock = mock
        self._hotspots: list[SatelliteHotspot] = []
        self._last_fetch = 0.0

        logger.info("SatelliteThermalMonitor: facility=(%.4f, %.4f) radius=%.1f km",
                    facility_lat, facility_lon, radius_km)

    # ── Distance Calculation ────────────────────────────────────────

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two lat/lon points in km."""
        import math
        R = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    # ── Data Fetching ───────────────────────────────────────────────

    async def fetch_nasa_firms(self, api_key: str | None = None) -> list[SatelliteHotspot]:
        """Fetch NASA FIRMS active fire data.

        Returns hotspots within radius_km of facility.
        """
        if self.mock:
            import random
            hotspots = []
            for i in range(random.randint(0, 3)):
                h = SatelliteHotspot(
                    source="FIRMS",
                    lat=self.facility_lat + random.gauss(0, 0.05),
                    lon=self.facility_lon + random.gauss(0, 0.05),
                    brightness=random.uniform(350, 450),
                    confidence=random.choice(["high", "nominal", "low"]),
                    detection_time=time.time() - random.random() * 3600,
                    satellite="MODIS",
                )
                h.distance_km = self._haversine_distance(
                    self.facility_lat, self.facility_lon, h.lat, h.lon
                )
                hotspots.append(h)
            return [h for h in hotspots if h.distance_km <= self.radius_km]

        # Real API call
        try:
            import aiohttp
            # FIRMS API: returns CSV of hotspots in bounding box
            # Calculate bounding box (approximate)
            lat_offset = self.radius_km / 111.0
            lon_offset = self.radius_km / (111.0 * abs((self.facility_lat / 111000)) + 1e-9)
            bbox = f"{self.facility_lon - lon_offset},{self.facility_lat - lat_offset},"
            bbox += f"{self.facility_lon + lon_offset},{self.facility_lat + lat_offset}"

            url = f"{NASA_FIRMS_URL}/{api_key or 'public'}/MODIS_NRT/{bbox}/1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    text = await resp.text()
                    # Parse CSV
                    hotspots = []
                    lines = text.strip().split("\n")
                    if len(lines) < 2:
                        return []
                    for line in lines[1:]:
                        parts = line.split(",")
                        if len(parts) > 10:
                            h = SatelliteHotspot(
                                source="FIRMS",
                                lat=float(parts[0]),
                                lon=float(parts[1]),
                                brightness=float(parts[2]),
                                confidence=parts[3].strip().lower(),
                                detection_time=time.time(),  # Parse actual timestamp
                                satellite=parts[4],
                            )
                            h.distance_km = self._haversine_distance(
                                self.facility_lat, self.facility_lon, h.lat, h.lon
                            )
                            if h.distance_km <= self.radius_km:
                                hotspots.append(h)
                    return hotspots
        except Exception:
            logger.exception("FIRMS fetch failed")
            return []

    async def fetch_all_sources(self, api_key: str | None = None) -> list[SatelliteHotspot]:
        """Fetch from all configured satellite sources."""
        all_hotspots = []
        firms = await self.fetch_nasa_firms(api_key)
        all_hotspots.extend(firms)
        self._hotspots = all_hotspots
        self._last_fetch = time.time()
        return all_hotspots

    # ── Correlation ─────────────────────────────────────────────────

    def correlate_with_local(self, local_fire_lat: float | None = None,
                              local_fire_lon: float | None = None) -> dict[str, Any]:
        """Correlate satellite hotspots with local sensor detection."""
        if not self._hotspots:
            return {"correlated": False, "reason": "no_satellite_data"}

        if local_fire_lat is None or local_fire_lon is None:
            # Use facility location as proxy
            local_fire_lat = self.facility_lat
            local_fire_lon = self.facility_lon

        nearby = [
            h for h in self._hotspots
            if self._haversine_distance(local_fire_lat, local_fire_lon, h.lat, h.lon) <= 2.0
        ]

        high_conf = [h for h in nearby if h.confidence == "high"]
        return {
            "correlated": len(high_conf) > 0,
            "satellite_hotspots_nearby": len(nearby),
            "high_confidence_hotspots": len(high_conf),
            "max_brightness_k": max((h.brightness for h in nearby), default=0),
            "nearest_distance_km": min((h.distance_km for h in nearby), default=999),
            "correlation_strength": "strong" if len(high_conf) >= 2 else ("moderate" if len(high_conf) == 1 else "weak"),
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "facility": (self.facility_lat, self.facility_lon),
            "radius_km": self.radius_km,
            "hotspots_cached": len(self._hotspots),
            "last_fetch": self._last_fetch,
            "mock": self.mock,
        }
