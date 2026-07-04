"""V9-008 — Battery Forecast / Time-to-Empty Estimator

Estimates minutes of runtime remaining from recent battery samples rather than
from a static percentage. Helps operators make better shutdown decisions during
outages.

Personality: *Lycopodium Clavatum* — the strategic intellectual. Looks ahead,
plans for the worst, and presents the conclusion calmly.
"""
from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass
from typing import Any

from fire_suppression.config import Config
from fire_suppression.power.manager import PowerManager, PowerSource

logger = logging.getLogger(__name__)


@dataclass
class BatteryForecast:
    """Runtime forecast for a UPS/battery-backed system."""

    timestamp: float
    battery_percent: float
    source: str
    minutes_to_empty: int
    minutes_to_critical: int
    trend: str  # "rising" | "stable" | "falling" | "unknown"
    confidence: str  # "high" | "medium" | "low"
    sample_count: int


class BatteryForecaster:
    """Estimate remaining runtime from recent power status samples."""

    PERSONALITY = "Lycopodium Clavatum"

    def __init__(
        self,
        power_manager: PowerManager | None = None,
        config: Config | None = None,
        history_minutes: float = 10.0,
    ) -> None:
        self.power_manager = power_manager
        self.config = config or Config()
        self.history_minutes = history_minutes
        self._samples: list[tuple[float, float]] = []  # (timestamp, percent)

    async def update(self) -> BatteryForecast:
        """Read power status, append to history, and return a forecast."""
        if self.power_manager is None:
            # Mock fallback: pretend AC power with full battery.
            status = PowerStatusLike(percent=100.0, source=PowerSource.AC.value, is_charging=True)
        else:
            raw = await self.power_manager.get_status()
            status = PowerStatusLike(
                percent=getattr(raw, "battery_percent", 0.0),
                source=getattr(raw, "source", PowerSource.UNKNOWN),
                is_charging=getattr(raw, "is_charging", False),
            )

        now = time.time()
        self._samples.append((now, status.percent))
        self._trim_history(now)
        return self._forecast(status, now)

    def _trim_history(self, now: float) -> None:
        cutoff = now - self.history_minutes * 60
        self._samples = [(t, p) for t, p in self._samples if t >= cutoff]

    def _forecast(self, status: "PowerStatusLike", now: float) -> BatteryForecast:
        """Compute minutes-to-empty and minutes-to-critical."""
        if status.source == PowerSource.AC.value or status.is_charging:
            return BatteryForecast(
                timestamp=now,
                battery_percent=round(status.percent, 1),
                source=status.source,
                minutes_to_empty=9999,
                minutes_to_critical=9999,
                trend="rising" if status.percent > 95 else "stable",
                confidence="high",
                sample_count=len(self._samples),
            )

        if len(self._samples) < 2:
            # Not enough data; fall back to a rough rule of thumb.
            minutes = int(status.percent * 2.4)
            return BatteryForecast(
                timestamp=now,
                battery_percent=round(status.percent, 1),
                source=status.source,
                minutes_to_empty=minutes,
                minutes_to_critical=max(0, minutes - 15),
                trend="unknown",
                confidence="low",
                sample_count=len(self._samples),
            )

        # Linear drain estimate from recent samples.
        times, percents = zip(*self._samples)
        drain_per_minute = self._drain_rate(times, percents)

        if drain_per_minute <= 0:
            trend = "stable" if status.is_charging else "unknown"
            minutes_to_empty = int(status.percent * 2.4)
        else:
            minutes_to_empty = int(status.percent / drain_per_minute)
            trend = "falling"

        critical_pct = float(self.config.get("power", "critical_battery_percent", default=5.0))
        if drain_per_minute <= 0:
            minutes_to_critical = minutes_to_empty
        else:
            minutes_to_critical = int(max(0.0, status.percent - critical_pct) / drain_per_minute)

        return BatteryForecast(
            timestamp=now,
            battery_percent=round(status.percent, 1),
            source=status.source,
            minutes_to_empty=minutes_to_empty,
            minutes_to_critical=minutes_to_critical,
            trend=trend,
            confidence="high" if len(self._samples) >= 5 else "medium",
            sample_count=len(self._samples),
        )

    @staticmethod
    def _drain_rate(times: tuple[float, ...], percents: tuple[float, ...]) -> float:
        """Compute percent-per-minute drain from the most recent samples."""
        if len(times) < 2:
            return 0.0
        # Use last 5 minutes (or all if fewer).
        recent_count = min(len(times), 5)
        t = times[-recent_count:]
        p = percents[-recent_count:]
        elapsed = t[-1] - t[0]
        if elapsed <= 0:
            return 0.0
        delta = p[0] - p[-1]
        # percent per minute
        return max(0.0, delta / (elapsed / 60.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "personality": self.PERSONALITY,
            "history_minutes": self.history_minutes,
            "sample_count": len(self._samples),
        }


class PowerStatusLike:
    """Minimal read-only adapter for power status values."""

    def __init__(self, percent: float, source: Any, is_charging: bool) -> None:
        self.percent = percent
        self.source = source.value if hasattr(source, "value") else str(source)
        self.is_charging = is_charging
