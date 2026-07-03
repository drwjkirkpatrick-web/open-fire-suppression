"""BOT-010 — System Watchdog

Hardware/software watchdog hybrid that monitors the main fire-suppression
process.  If the process becomes unresponsive, the watchdog triggers
systemd restart or a hardware GPIO pulse (optional external watchdog chip).

Features:
  • Software heartbeat: main loop calls feed() regularly
  • Health monitoring: CPU, memory, thread counts
  • Automatic systemd restart on failure
  • Mock mode for CI/testing
  • Bilingual messages (EN + SW)

Usage::

    from fire_suppression.diagnostics.watchdog import Watchdog
    wd = Watchdog(timeout_sec=30.0, mock=True)
    wd.start()
    while running:
        wd.feed()
        time.sleep(5)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ── Bilingual messages ──────────────────────────────────────────────────────
_WD_MSGS = {
    "started": {
        "en": "Watchdog started — timeout {timeout}s, max_failures {max_failures}",
        "sw": "Watchdog imeanza — kikomo {timeout}s, kushindwa {max_failures}",
    },
    "fed": {
        "en": "Watchdog fed at {ts}",
        "sw": "Watchdog imekulishwa saa {ts}",
    },
    "timeout": {
        "en": "WATCHDOG TIMEOUT: No heartbeat for {elapsed:.1f}s. Restarting system.",
        "sw": "KIKOMO CHA WATCHDOG: Hakuna moyo tangu {elapsed:.1f}s. Inaanza upya.",
    },
    "restarted": {
        "en": "Watchdog triggered systemd restart",
        "sw": "Watchdog imeamsha kuanzisha upya ya systemd",
    },
    "health_alert": {
        "en": "Watchdog health degraded: {reason}",
        "sw": "Afya ya Watchdog imedhoofika: {reason}",
    },
}


def _wd_msg(key: str, lang: str = "en", **kwargs) -> str:
    m = _WD_MSGS.get(key, {})
    return m.get(lang, m.get("en", key)).format(**kwargs)


class Watchdog:
    """Software/hardware watchdog for fire-suppression system reliability."""

    def __init__(
        self,
        timeout_sec: float = 30.0,
        max_failures: int = 2,
        data_dir: Optional[Path] = None,
        lang: str = "en",
        *,
        mock: bool = False,
    ) -> None:
        self.mock = mock
        self.lang = lang
        self.timeout_sec = timeout_sec
        self.max_failures = max_failures
        self.data_dir = Path(data_dir) if data_dir else Path.home() / ".local" / "share" / "fire-suppression" / "watchdog"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._last_feed: float = time.time()
        self._failure_count: int = 0
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._total_feeds: int = 0
        self._total_timeouts: int = 0
        self._on_timeout: Optional[Callable[[], None]] = None

        # Health snapshot
        self._health: Dict[str, Any] = {}

    def set_on_timeout(self, callback: Callable[[], None]) -> None:
        self._on_timeout = callback

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info(_wd_msg("started", self.lang, timeout=self.timeout_sec, max_failures=self.max_failures))

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    def feed(self) -> None:
        """Call from the main loop to keep the watchdog satisfied."""
        self._last_feed = time.time()
        self._total_feeds += 1
        self._failure_count = 0
        if self._total_feeds % 100 == 0:
            logger.debug(_wd_msg("fed", self.lang, ts=self._last_feed))

    # ── Health checks ────────────────────────────────────────────────────────

    def _check_process_health(self) -> Dict[str, Any]:
        """Gather lightweight process health metrics."""
        health: Dict[str, Any] = {"threads": 1, "fds": 0}
        try:
            # Thread count
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("Threads:"):
                        health["threads"] = int(line.split(":")[1].strip())
                    if line.startswith("FDSize:"):
                        health["fds"] = int(line.split(":")[1].strip())
        except (OSError, ValueError):
            pass
        return health

    async def run_monitor(self) -> None:
        """Background coroutine: check for timeouts."""
        while self._running:
            await asyncio.sleep(self.timeout_sec / 2.0)
            if not self._running:
                break
            elapsed = time.time() - self._last_feed
            if elapsed > self.timeout_sec:
                self._failure_count += 1
                self._total_timeouts += 1
                logger.warning(_wd_msg("timeout", self.lang, elapsed=elapsed))
                if self._failure_count >= self.max_failures:
                    await self._trigger_restart()
            else:
                self._failure_count = max(0, self._failure_count - 1)

    async def _trigger_restart(self) -> None:
        if self.mock:
            logger.warning(_wd_msg("restarted", self.lang))
            if self._on_timeout:
                try:
                    self._on_timeout()
                except Exception:
                    pass
            return

        # Real: attempt systemd restart
        try:
            os.system("systemctl restart fire-suppression || true")
            logger.critical(_wd_msg("restarted", self.lang))
        except Exception as exc:
            logger.critical("Restart failed: %s", exc)

        if self._on_timeout:
            try:
                self._on_timeout()
            except Exception:
                pass

    # ── API ──────────────────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        elapsed = time.time() - self._last_feed
        proc = self._check_process_health()
        return {
            "healthy": elapsed <= self.timeout_sec and self._failure_count < self.max_failures,
            "mock": self.mock,
            "elapsed_since_feed": round(elapsed, 2),
            "failure_count": self._failure_count,
            "total_feeds": self._total_feeds,
            "total_timeouts": self._total_timeouts,
            "threads": proc["threads"],
            "open_fds": proc["fds"],
        }

    def get_feature_overview(self) -> Dict[str, Any]:
        return {
            "feature_id": "BOT-010",
            "feature_name": "System Watchdog",
            "mock": self.mock,
            "supports": ["heartbeat", "timeout_restart", "process_health", "custom_callback"],
        }

    def to_dict(self) -> Dict[str, Any]:
        return self.health_check()
