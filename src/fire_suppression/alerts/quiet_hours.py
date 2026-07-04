"""V9-003 — Quiet Hours / Do-Not-Disturb Scheduler

Suppresses non-critical notifications during configured rest windows.
Confirmed fires and other life-safety CRITICAL alerts always break through.

Personality: *Bryonia Alba* — the deep-work hermit. Quiet hours protect
focused/rest time; the system does not disturb unless the house is literally on
fire.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


@dataclass
class QuietWindow:
    """A daily quiet-hours window in local 24-hour time."""

    start_hour: int  # 0-23
    start_minute: int  # 0-59
    end_hour: int
    end_minute: int


class QuietHoursScheduler:
    """Decides whether a notification should be allowed right now.

    Configuration sources (in order of priority):
    1. ``alerts.quiet_hours`` section in Config.
    2. Environment variables ``FIRE_QUIET_START`` / ``FIRE_QUIET_END`` (HH:MM).
    3. Hard-coded default 22:00 - 07:00.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.personality = "Bryonia Alba"
        self._window = self._load_window()
        # Register on the config object so the daily digest can see us.
        setattr(self.config, "_quiet_hours", self)

    def _load_window(self) -> QuietWindow:
        """Load quiet window from config or environment."""
        cfg = self.config.section("alerts").get("quiet_hours", {})
        start = self._parse_time(
            cfg.get("start") or self.config.get("alerts", "quiet_hours", "start", default=None)
        )
        end = self._parse_time(
            cfg.get("end") or self.config.get("alerts", "quiet_hours", "end", default=None)
        )

        # Environment overrides config.
        env_start = self._parse_time(_get_env("FIRE_QUIET_START"))
        env_end = self._parse_time(_get_env("FIRE_QUIET_END"))
        if env_start and env_end:
            start, end = env_start, env_end

        if start is None or end is None:
            # Default 22:00 - 07:00.
            start = (22, 0)
            end = (7, 0)

        return QuietWindow(
            start_hour=start[0],
            start_minute=start[1],
            end_hour=end[0],
            end_minute=end[1],
        )

    @staticmethod
    def _parse_time(value: Any) -> tuple[int, int] | None:
        """Parse "HH:MM" into (hour, minute)."""
        if not value:
            return None
        try:
            h, m = str(value).strip().split(":")
            return int(h), int(m)
        except Exception:
            logger.warning("Invalid quiet-hours time format: %r", value)
            return None

    def in_quiet_hours(self, timestamp: float | None = None) -> bool:
        """Return True if the given time falls inside the quiet window."""
        # Use local time; production systems should set TZ correctly.
        t = time.localtime(timestamp or time.time())
        now_minutes = t.tm_hour * 60 + t.tm_min
        start_minutes = self._window.start_hour * 60 + self._window.start_minute
        end_minutes = self._window.end_hour * 60 + self._window.end_minute

        if start_minutes <= end_minutes:
            return start_minutes <= now_minutes <= end_minutes
        # Window wraps midnight.
        return now_minutes >= start_minutes or now_minutes <= end_minutes

    def should_suppress(self, severity: str, _category: str = "") -> bool:
        """Non-critical notifications are suppressed during quiet hours."""
        if not self.in_quiet_hours():
            return False
        # Life-safety severities always break through.
        if severity.lower() in {"critical", "confirmed", "emergency", "alert"}:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "personality": self.personality,
            "window": {
                "start": f"{self._window.start_hour:02d}:{self._window.start_minute:02d}",
                "end": f"{self._window.end_hour:02d}:{self._window.end_minute:02d}",
            },
            "in_quiet_hours": self.in_quiet_hours(),
        }


def _get_env(name: str) -> str | None:
    import os
    return os.environ.get(name)
