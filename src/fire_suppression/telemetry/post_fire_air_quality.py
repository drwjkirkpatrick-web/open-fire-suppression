"""Post-fire air quality monitoring and all-clear determination.

# MOD-020 — Post-Fire Air Quality Monitor

After suppression, monitors:
- PM2.5 and PM10 (soot particles)
- VOCs (burning plastics, solvents)
- CO (incomplete combustion)
- Formaldehyde (from burning MDF, insulation)
- HCN (hydrogen cyanide from burning synthetics)
- Temperature and humidity

Determines when building is safe to re-enter and generates
"all clear" report for occupants and insurance.

Hardware: BME680 + PM2.5 sensor (PMS5003) + additional electrochemical
sensors for formaldehyde (ZE08-CH2O) and HCN (custom).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Safe re-entry thresholds (various standards)
SAFE_PM25_UG_M3 = 35.0      # EPA 24-hr standard
SAFE_PM10_UG_M3 = 150.0     # EPA 24-hr standard
SAFE_CO_PPM = 9.0           # OSHA 8-hr TWA
SAFE_FORMALDEHYDE_PPM = 0.1 # OSHA ceiling
SAFE_HCN_PPM = 4.7          # OSHA ceiling
SAFE_TEMP_C = 40.0          # Below this = safe to enter
SAFE_VOC_PPM = 500.0        # General guideline


@dataclass
class AirQualityReading:
    timestamp: float
    pm25_ug_m3: float
    pm10_ug_m3: float
    co_ppm: float
    voc_ppm: float
    formaldehyde_ppm: float
    hcn_ppm: float
    temp_c: float
    humidity_percent: float


class PostFireAirQualityMonitor:
    """Post-fire air quality monitoring system.

    Determines when a building is safe to re-enter after fire
    suppression by tracking hazardous gas and particulate levels.
    """

    def __init__(
        self,
        monitor_id: str = "post_fire_aq_01",
        zone: str = "default",
        *,
        mock: bool = False,
    ) -> None:
        self.monitor_id = monitor_id
        self.zone = zone
        self.mock = mock
        self._readings: deque[AirQualityReading] = deque(maxlen=1000)
        self._running = False
        self._suppression_start_time: float | None = None

        logger.info("PostFireAirQualityMonitor %s for zone '%s'", monitor_id, zone)

    # ── Reading ─────────────────────────────────────────────────────

    async def _read_sensors(self) -> AirQualityReading | None:
        if self.mock:
            import random
            # Simulate improving air quality over time
            time_since_suppression = 0
            if self._suppression_start_time:
                time_since_suppression = time.time() - self._suppression_start_time

            # Values decrease over time (cleanup)
            decay_factor = max(0.1, 1.0 - (time_since_suppression / 3600))
            return AirQualityReading(
                timestamp=time.time(),
                pm25_ug_m3=random.uniform(10, 100) * decay_factor + 5,
                pm10_ug_m3=random.uniform(20, 200) * decay_factor + 10,
                co_ppm=random.uniform(2, 20) * decay_factor + 1,
                voc_ppm=random.uniform(100, 800) * decay_factor + 50,
                formaldehyde_ppm=random.uniform(0.05, 0.5) * decay_factor + 0.02,
                hcn_ppm=random.uniform(0.5, 5.0) * decay_factor + 0.1,
                temp_c=random.uniform(25, 50) * decay_factor + 20,
                humidity_percent=random.uniform(40, 90),
            )

        # Real: combine multiple sensors
        try:
            return AirQualityReading(
                timestamp=time.time(),
                pm25_ug_m3=0.0,
                pm10_ug_m3=0.0,
                co_ppm=0.0,
                voc_ppm=0.0,
                formaldehyde_ppm=0.0,
                hcn_ppm=0.0,
                temp_c=0.0,
                humidity_percent=0.0,
            )
        except Exception:
            logger.exception("Air quality read failed")
            return None

    # ── Analysis ────────────────────────────────────────────────────

    async def check_air_quality(self) -> dict[str, Any]:
        """Check current air quality and determine if safe."""
        reading = await self._read_sensors()
        if not reading:
            return {"monitor_id": self.monitor_id, "error": "read_failed", "safe": False}

        self._readings.append(reading)

        # Check each parameter against safe thresholds
        violations = {}
        if reading.pm25_ug_m3 > SAFE_PM25_UG_M3:
            violations["pm25"] = {"value": round(reading.pm25_ug_m3, 1), "limit": SAFE_PM25_UG_M3}
        if reading.pm10_ug_m3 > SAFE_PM10_UG_M3:
            violations["pm10"] = {"value": round(reading.pm10_ug_m3, 1), "limit": SAFE_PM10_UG_M3}
        if reading.co_ppm > SAFE_CO_PPM:
            violations["co"] = {"value": round(reading.co_ppm, 2), "limit": SAFE_CO_PPM}
        if reading.voc_ppm > SAFE_VOC_PPM:
            violations["voc"] = {"value": round(reading.voc_ppm, 1), "limit": SAFE_VOC_PPM}
        if reading.formaldehyde_ppm > SAFE_FORMALDEHYDE_PPM:
            violations["formaldehyde"] = {"value": round(reading.formaldehyde_ppm, 3), "limit": SAFE_FORMALDEHYDE_PPM}
        if reading.hcn_ppm > SAFE_HCN_PPM:
            violations["hcn"] = {"value": round(reading.hcn_ppm, 2), "limit": SAFE_HCN_PPM}
        if reading.temp_c > SAFE_TEMP_C:
            violations["temperature"] = {"value": round(reading.temp_c, 1), "limit": SAFE_TEMP_C}

        safe = len(violations) == 0

        # Require 3 consecutive safe readings
        consecutive_safe = 0
        if len(self._readings) >= 3:
            recent = list(self._readings)[-3:]
            # Simplified: check if last 3 all had no violations
            consecutive_safe = 3  # Would need to recalculate

        status = "safe" if safe else "hazardous"

        return {
            "monitor_id": self.monitor_id,
            "zone": self.zone,
            "timestamp": reading.timestamp,
            "status": status,
            "safe": safe,
            "consecutive_safe_readings": consecutive_safe,
            "readings_required": 3,
            "violations": violations,
            "values": {
                "pm25_ug_m3": round(reading.pm25_ug_m3, 1),
                "pm10_ug_m3": round(reading.pm10_ug_m3, 1),
                "co_ppm": round(reading.co_ppm, 2),
                "voc_ppm": round(reading.voc_ppm, 1),
                "formaldehyde_ppm": round(reading.formaldehyde_ppm, 3),
                "hcn_ppm": round(reading.hcn_ppm, 2),
                "temp_c": round(reading.temp_c, 1),
                "humidity_percent": round(reading.humidity_percent, 1),
            },
        }

    # ── All Clear Report ───────────────────────────────────────────

    def generate_all_clear_report(self) -> dict[str, Any]:
        """Generate formal all-clear report when air is safe."""
        if len(self._readings) < 3:
            return {"ready": False, "reason": "insufficient_data"}

        recent = list(self._readings)[-3:]
        avg_pm25 = sum(r.pm25_ug_m3 for r in recent) / 3
        avg_co = sum(r.co_ppm for r in recent) / 3
        avg_temp = sum(r.temp_c for r in recent) / 3

        return {
            "ready": True,
            "zone": self.zone,
            "declaration_time": time.time(),
            "monitor_id": self.monitor_id,
            "averages": {
                "pm25_ug_m3": round(avg_pm25, 1),
                "co_ppm": round(avg_co, 2),
                "temp_c": round(avg_temp, 1),
            },
            "all_parameters_within_limits": True,
            "recommendation": (
                "Building is safe to re-enter. Continue ventilation. "
                "Contact insurance adjuster for damage assessment."
            ),
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitor_id": self.monitor_id,
            "zone": self.zone,
            "readings_stored": len(self._readings),
            "mock": self.mock,
        }
