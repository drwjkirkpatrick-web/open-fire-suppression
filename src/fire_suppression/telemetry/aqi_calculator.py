"""Air Quality Index (AQI) publishing from sensor data.

# ADD-014 — AQI Publishing

Computes EPA-style Air Quality Index from PM2.5 and VOC data.
Publishes to local display and optionally to public health feeds.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# EPA AQI breakpoints for PM2.5 (μg/m³)
PM25_BREAKPOINTS = [
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 500.4, 301, 500),
]

# VOC ppb to AQI approximation
VOC_BREAKPOINTS = [
    (0, 220, 0, 50),
    (221, 660, 51, 100),
    (661, 2200, 101, 150),
    (2201, 3300, 151, 200),
    (3301, 4400, 201, 300),
]


def _calculate_aqi(concentration: float, breakpoints: list[tuple[float, float, int, int]]) -> int:
    """Calculate AQI from concentration using EPA breakpoints."""
    for c_low, c_high, aqi_low, aqi_high in breakpoints:
        if c_low <= concentration <= c_high:
            return int(
                ((aqi_high - aqi_low) / (c_high - c_low)) * (concentration - c_low) + aqi_low
            )
    return 500 if concentration > 0 else 0


def _aqi_category(aqi: int) -> str:
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


class AQICalculator:
    """Computes and tracks Air Quality Index from sensor readings.

    Usage::

        aqi = AQICalculator()
        result = aqi.update(pm25_ug_m3=35.0, voc_ppb=500)
        # result = {"aqi": 101, "category": "Unhealthy for Sensitive Groups", ...}
    """

    def __init__(self) -> None:
        self._last_pm25 = 0.0
        self._last_voc = 0.0
        self._last_aqi = 0
        self._last_category = "Unknown"

    def update(self, pm25_ug_m3: float | None = None, voc_ppb: float | None = None) -> dict:
        """Update AQI with latest sensor readings.

        Args:
            pm25_ug_m3: PM2.5 concentration in μg/m³ (from ENS160 or external sensor).
            voc_ppb: VOC concentration in ppb.

        Returns:
            Dict with aqi, category, dominant_pollutant, and health_recommendation.
        """
        if pm25_ug_m3 is not None:
            self._last_pm25 = pm25_ug_m3
        if voc_ppb is not None:
            self._last_voc = voc_ppb

        aqi_pm25 = _calculate_aqi(self._last_pm25, PM25_BREAKPOINTS)
        aqi_voc = _calculate_aqi(self._last_voc, VOC_BREAKPOINTS)

        self._last_aqi = max(aqi_pm25, aqi_voc)
        self._last_category = _aqi_category(self._last_aqi)
        dominant = "PM2.5" if aqi_pm25 >= aqi_voc else "VOCs"

        return {
            "aqi": self._last_aqi,
            "category": self._last_category,
            "dominant_pollutant": dominant,
            "pm25_ug_m3": self._last_pm25,
            "pm25_aqi": aqi_pm25,
            "voc_ppb": self._last_voc,
            "voc_aqi": aqi_voc,
            "health_recommendation": self._health_recommendation(self._last_aqi),
        }

    def _health_recommendation(self, aqi: int) -> str:
        if aqi <= 50:
            return "Air quality is satisfactory."
        elif aqi <= 100:
            return "Sensitive individuals should limit prolonged outdoor exertion."
        elif aqi <= 150:
            return "Sensitive groups: reduce outdoor activities. General public: moderate exertion."
        elif aqi <= 200:
            return "Everyone: avoid prolonged outdoor exertion. Sensitive groups: stay indoors."
        elif aqi <= 300:
            return "Health alert: everyone may experience serious health effects."
        return "Emergency conditions: everyone should avoid all physical activity outdoors."

    def get_current(self) -> dict:
        return {
            "aqi": self._last_aqi,
            "category": self._last_category,
            "pm25_ug_m3": self._last_pm25,
            "voc_ppb": self._last_voc,
        }
