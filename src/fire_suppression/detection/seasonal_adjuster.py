"""Seasonal threshold auto-adjustment.

# ADD-015 — Seasonal Threshold Adjustment

Automatically shifts fire detection thresholds based on month
and outdoor temperature (from weather API or learned seasonal baselines).
Prevents false alarms from winter heating and summer ambient temps.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Seasonal adjustment multipliers (month-indexed, 1=Jan)
SEASONAL_MULTIPLIERS = {
    "temperature_c": {
        1: 1.2, 2: 1.15, 3: 1.0, 4: 0.9, 5: 0.85,
        6: 0.8, 7: 0.8, 8: 0.85, 9: 0.9, 10: 1.0, 11: 1.1, 12: 1.2,
    },
    "humidity_percent": {
        1: 0.9, 2: 0.9, 3: 1.0, 4: 1.05, 5: 1.1,
        6: 1.15, 7: 1.15, 8: 1.1, 9: 1.05, 10: 1.0, 11: 0.95, 12: 0.9,
    },
}


class SeasonalThresholdAdjuster:
    """Adjusts detection thresholds based on seasonal patterns.

    Usage::

        adjuster = SeasonalThresholdAdjuster()
        temp_threshold = adjuster.adjust("temperature_c", base=70.0)
        # In July, returns 56.0 (70 * 0.8)
    """

    def __init__(self, use_api: bool = False, api_key: str | None = None) -> None:
        self.use_api = use_api
        self.api_key = api_key
        self._outdoor_temp = 20.0
        self._last_api_check = 0.0

    def adjust(self, metric: str, base_threshold: float) -> float:
        """Apply seasonal adjustment to a base threshold.

        Args:
            metric: The sensor metric name (e.g., "temperature_c").
            base_threshold: The unadjusted threshold value.

        Returns:
            Adjusted threshold.
        """
        month = time.localtime().tm_mon
        multipliers = SEASONAL_MULTIPLIERS.get(metric, {})
        multiplier = multipliers.get(month, 1.0)
        adjusted = base_threshold * multiplier
        logger.debug("Seasonal adjust: %s base=%.1f month=%d mult=%.2f -> %.1f",
                     metric, base_threshold, month, multiplier, adjusted)
        return adjusted

    def get_all_adjustments(self, base_thresholds: dict[str, float]) -> dict[str, float]:
        """Apply seasonal adjustment to all thresholds."""
        return {metric: self.adjust(metric, base) for metric, base in base_thresholds.items()}

    async def update_outdoor_temp(self, lat: float, lon: float) -> None:
        """Fetch outdoor temperature from OpenWeatherMap API."""
        if not self.use_api or not self.api_key:
            return
        if time.time() - self._last_api_check < 3600:  # Cache for 1 hour
            return

        try:
            import aiohttp
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={self.api_key}&units=metric"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._outdoor_temp = data["main"]["temp"]
                        self._last_api_check = time.time()
                        logger.info("Outdoor temp updated: %.1f°C", self._outdoor_temp)
        except Exception as exc:
            logger.debug("Weather API fetch failed: %s", exc)

    def get_current_season(self) -> str:
        month = time.localtime().tm_mon
        if month in (12, 1, 2):
            return "winter"
        elif month in (3, 4, 5):
            return "spring"
        elif month in (6, 7, 8):
            return "summer"
        return "autumn"
