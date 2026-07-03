"""Memory Monitor for the fire suppression platform.

# BOT-004 — Memory Monitor

Monitors RSS/VMS memory usage via ``/proc/self/status`` (Linux) or
``tracemalloc`` as a cross-platform fallback.  Runs a periodic
background check every 60 s, logs alerts when configurable
thresholds are exceeded, and can optionally trigger garbage
collection on critical conditions.

Tracks memory trend (increasing / stable / decreasing) and reports
bilingual (English / Swahili) status messages.

Usage::

    from fire_suppression.diagnostics.memory_monitor import MemoryMonitor
    mm = MemoryMonitor(max_mb=512, warn_percent=80, critical_percent=90)
    await mm.start()
    # ... later ...
    status = mm.to_dict()
    await mm.stop()
"""
from __future__ import annotations

import asyncio
import gc
import logging
import time
import tracemalloc
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

DEFAULT_MAX_MB = 512
DEFAULT_WARN_PERCENT = 80
DEFAULT_CRITICAL_PERCENT = 90
DEFAULT_INTERVAL_S = 60


# ── Bilingual messages ─────────────────────────────────────────────────

_MSGS: Dict[str, Dict[str, str]] = {
    "init_ok": {
        "en": "Memory monitor initialised — max {max_mb} MB, warn {warn}%, critical {critical}%",
        "sw": "Kiolesura kumbukumbu kimeanzishwa — kiwango cha juu {max_mb} MB, onyo {warn}%, hatari {critical}%",
    },
    "warn_threshold": {
        "en": "Memory usage {current:.1f} MB exceeds warning threshold ({warn:.1f} MB)",
        "sw": "Matumizi ya kumbukumbu {current:.1f} MB yamezidi kiwango cha onyo ({warn:.1f} MB)",
    },
    "critical_threshold": {
        "en": "Memory usage {current:.1f} MB exceeds CRITICAL threshold ({critical:.1f} MB)",
        "sw": "Matumizi ya kumbukumbu {current:.1f} MB yamezidi kiwango cha HATARI ({critical:.1f} MB)",
    },
    "gc_triggered": {
        "en": "Garbage collection triggered after critical memory alert",
        "sw": "Mkusanyaji takataka umeanzishwa baada ya onyo la kumbukumbu hatari",
    },
    "stopped": {
        "en": "Memory monitor stopped",
        "sw": "Kiolesura kumbukumbu kimeacha kufanya kazi",
    },
    "mock_mode": {
        "en": "Memory monitor running in mock mode",
        "sw": "Kiolesura kumbukumbu kinafanya kazi katika hali ya uigizo",
    },
}


def _msg(key: str, lang: str = "en", **kwargs: Any) -> str:
    m = _MSGS.get(key, {})
    return m.get(lang, m.get("en", key)).format(**kwargs)


# ── Enums ──────────────────────────────────────────────────────────────

class MemoryTrend(Enum):
    """Direction of memory usage over time."""

    INCREASING = "increasing"
    STABLE = "stable"
    DECREASING = "decreasing"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """Severity of a memory alert."""

    NONE = "none"
    WARN = "warn"
    CRITICAL = "critical"


# ── Data classes ───────────────────────────────────────────────────────

@dataclass
class MemorySnapshot:
    """A single memory reading."""

    timestamp: float
    rss_mb: float
    vms_mb: float
    percent_of_max: float
    alert_level: AlertLevel
    trend: MemoryTrend
    message_en: str = ""
    message_sw: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "rss_mb": self.rss_mb,
            "vms_mb": self.vms_mb,
            "percent_of_max": self.percent_of_max,
            "alert_level": self.alert_level.value,
            "trend": self.trend.value,
            "message_en": self.message_en,
            "message_sw": self.message_sw,
        }


@dataclass
class MemoryAlert:
    """A single memory threshold alert."""

    timestamp: float
    level: AlertLevel
    rss_mb: float
    threshold_mb: float
    message_en: str
    message_sw: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "rss_mb": self.rss_mb,
            "threshold_mb": self.threshold_mb,
            "message_en": self.message_en,
            "message_sw": self.message_sw,
        }


# ── Main class ─────────────────────────────────────────────────────────

class MemoryMonitor:
    """Periodic memory usage monitor with threshold alerting.

    Args:
        max_mb: Maximum memory ceiling in megabytes (default 512).
        warn_percent: Percentage of ``max_mb`` that triggers a warning.
        critical_percent: Percentage of ``max_mb`` that triggers a critical alert.
        interval_s: Seconds between background checks.
        auto_gc: If ``True``, run ``gc.collect()`` when critical is breached.
        mock: If ``True``, operate with synthetic / fixed values.
        lang: Preferred language for log messages (``"en"`` or ``"sw"``).
    """

    def __init__(
        self,
        max_mb: int = DEFAULT_MAX_MB,
        warn_percent: float = DEFAULT_WARN_PERCENT,
        critical_percent: float = DEFAULT_CRITICAL_PERCENT,
        interval_s: float = DEFAULT_INTERVAL_S,
        auto_gc: bool = True,
        mock: bool = False,
        lang: str = "en",
    ) -> None:
        self.max_mb = max_mb
        self.warn_mb = (warn_percent / 100.0) * max_mb
        self.critical_mb = (critical_percent / 100.0) * max_mb
        self.interval_s = interval_s
        self.auto_gc = auto_gc
        self.mock = mock
        self.lang = lang
        self.feature_id = "BOT-004"

        self._task: Optional[asyncio.Task[Any]] = None
        self._running = False
        self._history: List[MemorySnapshot] = []
        self._alerts: List[MemoryAlert] = []
        self._last_rss: float = 0.0

        if mock:
            logger.info(_msg("mock_mode", lang=self.lang))

        logger.info(
            _msg(
                "init_ok",
                lang=self.lang,
                max_mb=max_mb,
                warn=warn_percent,
                critical=critical_percent,
            )
        )

    # ── Sampling ───────────────────────────────────────────────────────

    def _read_proc_status(self) -> Tuple[float, float]:
        """Return (rss_mb, vms_mb) from ``/proc/self/status``.

        Falls back to ``(0.0, 0.0)`` on error or non-Linux platforms.
        """
        proc = Path("/proc/self/status")
        if not proc.exists():
            return 0.0, 0.0

        rss = 0.0
        vms = 0.0
        try:
            text = proc.read_text()
            for line in text.splitlines():
                if line.startswith("VmRSS"):
                    # VmRSS:   12345 kB
                    parts = line.split()
                    if len(parts) >= 2:
                        rss = float(parts[1]) / 1024.0
                elif line.startswith("VmSize"):
                    parts = line.split()
                    if len(parts) >= 2:
                        vms = float(parts[1]) / 1024.0
        except Exception:
            logger.exception("Failed to parse /proc/self/status")
        return rss, vms

    def _read_tracemalloc(self) -> Tuple[float, float]:
        """Return (rss_mb, vms_mb) via ``tracemalloc``.

        ``tracemalloc`` only tracks Python-allocated memory, so RSS is
        approximated from the current + peak size and VMS is set equal.
        """
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        current, peak = tracemalloc.get_traced_memory()
        mb = current / (1024 * 1024)
        return mb, mb

    def _sample(self) -> MemorySnapshot:
        """Take a single memory sample, record it in history, and trigger alerts."""
        if self.mock:
            rss = self._last_rss if self._last_rss else 100.0
            vms = rss * 1.5
        else:
            rss, vms = self._read_proc_status()
            if rss == 0.0:
                rss, vms = self._read_tracemalloc()

        percent = (rss / self.max_mb) * 100.0 if self.max_mb else 0.0

        if percent >= (self.critical_mb / self.max_mb) * 100.0:
            alert = AlertLevel.CRITICAL
        elif percent >= (self.warn_mb / self.max_mb) * 100.0:
            alert = AlertLevel.WARN
        else:
            alert = AlertLevel.NONE

        trend = self._compute_trend(rss)
        self._last_rss = rss

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=rss,
            vms_mb=vms,
            percent_of_max=percent,
            alert_level=alert,
            trend=trend,
            message_en="",
            message_sw="",
        )
        self._history.append(snapshot)
        alert_obj = self._maybe_alert(snapshot)
        if alert_obj and alert_obj.level == AlertLevel.CRITICAL and self.auto_gc:
            self._handle_critical()
        return snapshot

    def _compute_trend(self, current_rss: float) -> MemoryTrend:
        """Compare current RSS to the previous sample to determine trend."""
        if len(self._history) < 1:
            return MemoryTrend.UNKNOWN

        previous = self._history[-1].rss_mb
        delta = current_rss - previous
        threshold = self.max_mb * 0.02  # 2 % of max considered noise

        if delta > threshold:
            return MemoryTrend.INCREASING
        if delta < -threshold:
            return MemoryTrend.DECREASING
        return MemoryTrend.STABLE

    # ── Alerting ───────────────────────────────────────────────────────

    def _maybe_alert(self, snapshot: MemorySnapshot) -> Optional[MemoryAlert]:
        if snapshot.alert_level == AlertLevel.NONE:
            return None

        if snapshot.alert_level == AlertLevel.CRITICAL:
            msg_en = _msg(
                "critical_threshold",
                lang="en",
                current=snapshot.rss_mb,
                critical=self.critical_mb,
            )
            msg_sw = _msg(
                "critical_threshold",
                lang="sw",
                current=snapshot.rss_mb,
                critical=self.critical_mb,
            )
            threshold = self.critical_mb
        else:
            msg_en = _msg(
                "warn_threshold",
                lang="en",
                current=snapshot.rss_mb,
                warn=self.warn_mb,
            )
            msg_sw = _msg(
                "warn_threshold",
                lang="sw",
                current=snapshot.rss_mb,
                warn=self.warn_mb,
            )
            threshold = self.warn_mb

        alert = MemoryAlert(
            timestamp=snapshot.timestamp,
            level=snapshot.alert_level,
            rss_mb=snapshot.rss_mb,
            threshold_mb=threshold,
            message_en=msg_en,
            message_sw=msg_sw,
        )
        self._alerts.append(alert)
        return alert

    def _handle_critical(self) -> None:
        if self.auto_gc:
            collected = gc.collect()
            logger.warning(
                _msg("gc_triggered", lang=self.lang) + f" — objects collected: {collected}"
            )

    # ── Background loop ──────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            snapshot = self._sample()
            self._history.append(snapshot)

            alert = self._maybe_alert(snapshot)
            if alert:
                log_fn = logger.critical if alert.level == AlertLevel.CRITICAL else logger.warning
                log_fn("[MEMORY] %s | %s", alert.message_en, alert.message_sw)
                if alert.level == AlertLevel.CRITICAL:
                    self._handle_critical()

            await asyncio.sleep(self.interval_s)

    # ── Public lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        """Begin periodic background monitoring."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Memory monitor background task started")

    async def stop(self) -> None:
        """Stop background monitoring and clean up."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info(_msg("stopped", lang=self.lang))

    # ── Health & introspection ─────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Return current health status."""
        latest = self._history[-1] if self._history else None
        return {
            "healthy": latest.alert_level != AlertLevel.CRITICAL if latest else True,
            "rss_mb": latest.rss_mb if latest else 0.0,
            "vms_mb": latest.vms_mb if latest else 0.0,
            "percent_of_max": latest.percent_of_max if latest else 0.0,
            "trend": latest.trend.value if latest else MemoryTrend.UNKNOWN.value,
            "alert_level": latest.alert_level.value if latest else AlertLevel.NONE.value,
            "max_mb": self.max_mb,
            "warn_mb": self.warn_mb,
            "critical_mb": self.critical_mb,
            "auto_gc": self.auto_gc,
            "mock": self.mock,
        }

    def get_feature_overview(self) -> Dict[str, Any]:
        """Return feature metadata."""
        return {
            "feature_id": self.feature_id,
            "feature_name": "Memory Monitor",
            "mock": self.mock,
            "supports": [
                "rss_vms_monitoring",
                "threshold_alerts",
                "trend_tracking",
                "periodic_background_check",
                "auto_garbage_collection",
                "bilingual_messages",
            ],
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return full serialisable state."""
        latest = self._history[-1] if self._history else None
        return {
            **self.health_check(),
            "feature_id": self.feature_id,
            "feature_name": "Memory Monitor",
            "history_count": len(self._history),
            "alerts_count": len(self._alerts),
            "interval_s": self.interval_s,
            "lang": self.lang,
            "latest_snapshot": latest.to_dict() if latest else None,
            "recent_alerts": [a.to_dict() for a in self._alerts[-5:]],
        }

    # ── Convenience ──────────────────────────────────────────────────────

    def set_mock_rss(self, rss_mb: float) -> None:
        """Manually set the mock RSS value (only effective when ``mock=True``)."""
        self._last_rss = rss_mb

    def get_history(self) -> List[MemorySnapshot]:
        """Return all recorded snapshots."""
        return list(self._history)

    def get_alerts(self) -> List[MemoryAlert]:
        """Return all recorded alerts."""
        return list(self._alerts)
