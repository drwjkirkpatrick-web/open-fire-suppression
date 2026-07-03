"""System resilience and stay-alive layer for open-fire-suppression.

Handles sensor failures, detection engine stalls, memory leaks,
configuration corruption, process crashes, and network partitions.
"""
import asyncio
import gc
import json
import logging
import os
import sqlite3
import time
import tracemalloc
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DegradationMode(Enum):
    FULL = "full"
    DEGRADED = "degraded"
    EMERGENCY = "emergency"
    FAILED = "failed"


@dataclass
class ResilienceState:
    mode: DegradationMode = DegradationMode.FULL
    active_sensors: list[str] = field(default_factory=list)
    failed_sensors: list[str] = field(default_factory=list)
    degradation_percent: float = 0.0
    detection_fallback: str = ""
    last_update: float = 0.0


class SensorResilienceMonitor:
    """Monitors all sensors and manages graceful degradation.

    If a sensor fails, its weight in the fusion is redistributed.
    If >50% of sensors fail, switch to emergency mode (camera + any working sensor).
    """

    def __init__(self, component_names: list[str], *, max_failures: int = 3) -> None:
        self._components = {name: {"fails": 0, "last_ok": time.time(), "degraded": False}
                           for name in component_names}
        self._max_failures = max_failures
        self._weights: dict[str, float] = {name: 1.0 for name in component_names}
        self._state = ResilienceState()
        self._state.active_sensors = list(component_names)

    def record_success(self, name: str) -> None:
        if name in self._components:
            self._components[name]["fails"] = 0
            self._components[name]["last_ok"] = time.time()
            self._components[name]["degraded"] = False

    def record_failure(self, name: str) -> None:
        if name not in self._components:
            return
        self._components[name]["fails"] += 1
        if self._components[name]["fails"] >= self._max_failures:
            self._components[name]["degraded"] = True
            logger.warning("Component %s marked degraded after %d failures", name, self._components[name]["fails"])
        self._recompute_weights()

    def _recompute_weights(self) -> None:
        active = [n for n, s in self._components.items() if not s["degraded"]]
        failed = [n for n, s in self._components.items() if s["degraded"]]
        if not active:
            self._state.mode = DegradationMode.FAILED
        elif len(failed) > len(active):
            self._state.mode = DegradationMode.EMERGENCY
            self._state.detection_fallback = "camera_only"
        elif len(failed) > 0:
            self._state.mode = DegradationMode.DEGRADED
        else:
            self._state.mode = DegradationMode.FULL
        if active:
            weight = 1.0 / len(active)
            for name in self._components:
                self._weights[name] = weight if not self._components[name]["degraded"] else 0.0
        else:
            for name in self._components:
                self._weights[name] = 0.0
        self._state.active_sensors = active
        self._state.failed_sensors = failed

    def get_weight(self, name: str) -> float:
        return self._weights.get(name, 0.0)

    def get_state(self) -> ResilienceState:
        return self._state


# ────────────────────────────────────────────────────────────────
# BOT-002 — Detection Engine Timeout + Fallback
# ────────────────────────────────────────────────────────────────

class DetectionTimeoutGuard:
    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self.timeout = timeout_seconds
        self._fallback_count = 0

    async def run_with_timeout(self, coro, fallback_coro, *args, **kwargs):
        try:
            result = await asyncio.wait_for(coro(*args, **kwargs), timeout=self.timeout)
            self._fallback_count = 0
            return result
        except asyncio.TimeoutError:
            self._fallback_count += 1
            logger.warning("Detection timeout #%d — falling back to threshold mode", self._fallback_count)
            return await fallback_coro(*args, **kwargs)


# ────────────────────────────────────────────────────────────────
# BOT-003 — SQLite Corruption Recovery
# ────────────────────────────────────────────────────────────────

class SQLiteResilience:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.corrupt_count = 0

    def _is_corrupt(self) -> bool:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA integrity_check")
            conn.close()
            return False
        except sqlite3.DatabaseError:
            return True

    def recover(self) -> bool:
        if self._is_corrupt():
            self.corrupt_count += 1
            backup = self.db_path.with_suffix(".corrupt")
            self.db_path.rename(backup)
            logger.warning("Database corrupt — moved to %s, will rebuild", backup)
            return True
        return False


# ────────────────────────────────────────────────────────────────
# BOT-004 — Memory Leak Guard
# ────────────────────────────────────────────────────────────────

class MemoryGuard:
    def __init__(self, check_interval: float = 60.0, growth_threshold_mb: float = 50.0) -> None:
        self.interval = check_interval
        self.threshold_mb = growth_threshold_mb
        self._baseline: int | None = None
        self._high_water: int = 0

    def check(self) -> dict[str, Any]:
        if self._baseline is None:
            self._baseline = self._current_mb()
        current = self._current_mb()
        growth = current - self._baseline
        self._high_water = max(self._high_water, current)
        status = "OK"
        if growth > self.threshold_mb * 2:
            status = "CRITICAL"
            gc.collect()
        elif growth > self.threshold_mb:
            status = "WARNING"
        return {"current_mb": current, "growth_mb": growth, "high_water_mb": self._high_water, "status": status}

    def _current_mb(self) -> int:
        try:
            import psutil
            return int(psutil.Process().memory_info().rss / 1024 / 1024)
        except ImportError:
            return 0


# ────────────────────────────────────────────────────────────────
# BOT-005 — Network Partition Alert Queue
# ────────────────────────────────────────────────────────────────

class NetworkPartitionQueue:
    """Persistent store-and-forward queue for fire alerts."""

    def __init__(self, queue_path: Path | None = None) -> None:
        self.queue_path = queue_path or Path("/tmp/fire_alert_queue.json")
        self._queue: list[dict] = []
        self._load()

    def enqueue(self, alert: dict) -> None:
        alert["queued_at"] = time.time()
        self._queue.append(alert)
        self._save()

    def dequeue_all(self) -> list[dict]:
        items = list(self._queue)
        self._queue = []
        self._save()
        return items

    def _save(self) -> None:
        with open(self.queue_path, "w", encoding="utf-8") as f:
            json.dump(self._queue, f)

    def _load(self) -> None:
        if not self.queue_path.exists():
            return
        try:
            with open(self.queue_path, "r", encoding="utf-8") as f:
                self._queue = json.load(f)
        except Exception:
            self._queue = []


# ────────────────────────────────────────────────────────────────
# BOT-006 — Relay Fuse Monitor
# ────────────────────────────────────────────────────────────────

class RelayHealthMonitor:
    def __init__(self, relay_pins: dict[str, int]) -> None:
        self.relay_pins = relay_pins
        self._health: dict[str, dict] = {
            name: {"ok": True, "last_toggle": 0.0, "toggle_count": 0}
            for name in relay_pins
        }

    def record_toggle(self, name: str, success: bool) -> None:
        if name not in self._health:
            return
        self._health[name]["last_toggle"] = time.time()
        self._health[name]["toggle_count"] += 1
        if not success:
            self._health[name]["ok"] = False
            logger.error("Relay %s toggle failure — isolating", name)
        else:
            self._health[name]["ok"] = True

    def is_healthy(self, name: str) -> bool:
        return self._health.get(name, {}).get("ok", False)

    def get_all_health(self) -> dict[str, bool]:
        return {name: h["ok"] for name, h in self._health.items()}


# ────────────────────────────────────────────────────────────────
# BOT-007 — Config Corruption Recovery
# ────────────────────────────────────────────────────────────────

class ConfigResilience:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.lkg_path = self.config_path.parent / (self.config_path.stem + ".lkg" + self.config_path.suffix)

    def atomic_write(self, content: str) -> None:
        temp = self.config_path.with_suffix(".tmp")
        try:
            temp.write_text(content, encoding="utf-8")
            if self.config_path.exists():
                import shutil
                shutil.copy(str(self.config_path), str(self.lkg_path))
            temp.replace(self.config_path)
        except Exception:
            logger.exception("Atomic write failed")

    def recover(self) -> str | None:
        if self.lkg_path.exists():
            return self.lkg_path.read_text(encoding="utf-8")
        return None


# ────────────────────────────────────────────────────────────────
# BOT-008 — Disk Full Guard
# ────────────────────────────────────────────────────────────────

class DiskGuard:
    def __init__(self, path: str = "/", min_free_gb: float = 1.0) -> None:
        self.path = path
        self.min_free_gb = min_free_gb

    def check(self) -> dict[str, Any]:
        try:
            stat = os.statvfs(self.path)
            free_gb = stat.f_bavail * stat.f_frsize / (1024**3)
            total_gb = stat.f_blocks * stat.f_frsize / (1024**3)
            return {
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "status": "OK" if free_gb >= self.min_free_gb else "CRITICAL",
                "action": "Prune old logs" if free_gb < self.min_free_gb else None,
            }
        except Exception:
            return {"status": "ERROR", "free_gb": 0}


# ────────────────────────────────────────────────────────────────
# BOT-009 — Clock Drift Monitor
# ────────────────────────────────────────────────────────────────

class ClockMonitor:
    def __init__(self, *, has_rtc: bool = True) -> None:
        self.has_rtc = has_rtc
        self._ntp_confidence = 1.0
        self._last_sync = time.time()

    def check(self) -> dict[str, Any]:
        age = time.time() - self._last_sync
        if age > 86400:
            self._ntp_confidence *= 0.9
        return {
            "has_rtc": self.has_rtc,
            "ntp_confidence": round(self._ntp_confidence, 2),
            "last_sync_sec_ago": int(age),
            "status": "OK" if self._ntp_confidence > 0.5 else "WARNING",
        }

    def mark_sync(self) -> None:
        self._last_sync = time.time()
        self._ntp_confidence = 1.0


# ────────────────────────────────────────────────────────────────
# BOT-010 — Process Watchdog
# ────────────────────────────────────────────────────────────────

class StayAliveManager:
    """Top-level manager coordinating all resilience components."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        sensor_names = cfg.get("sensor_names", [])
        self.sensor_monitor = SensorResilienceMonitor(sensor_names)
        self.timeout_guard = DetectionTimeoutGuard(
            cfg.get("detection_timeout_sec", 2.0)
        )
        self.sqlite_resilience = SQLiteResilience(
            cfg.get("db_path", "/opt/fire-suppression/data/events.db")
        )
        self.memory_guard = MemoryGuard(
            check_interval=cfg.get("memory_check_interval_sec", 60.0),
            growth_threshold_mb=cfg.get("memory_growth_threshold_mb", 50.0),
        )
        self.network_queue = NetworkPartitionQueue(
            queue_path=Path(cfg.get("queue_path", "/tmp/fire_alert_queue.json"))
        )
        self.relay_monitor = RelayHealthMonitor(
            cfg.get("relay_pins", {})
        )
        self.config_resilience = ConfigResilience(
            cfg.get("config_path", "/opt/fire-suppression/config.yaml")
        )
        self.disk_guard = DiskGuard(
            cfg.get("disk_path", "/"),
            cfg.get("min_free_gb", 1.0),
        )
        self.clock_monitor = ClockMonitor(has_rtc=cfg.get("has_rtc", True))

    def health_snapshot(self) -> dict[str, Any]:
        state = self.sensor_monitor.get_state()
        return {
            "timestamp": time.time(),
            "mode": state.mode.value,
            "active_sensors": state.active_sensors,
            "failed_sensors": state.failed_sensors,
            "active_sensor_count": len(state.active_sensors),
            "total_sensor_count": len(state.active_sensors) + len(state.failed_sensors),
            "degradation_percent": state.degradation_percent,
            "detection_fallback": state.detection_fallback,
            "memory": self.memory_guard.check(),
            "disk": self.disk_guard.check(),
            "clock": self.clock_monitor.check(),
            "queue_size": len(self.network_queue._queue),
        }
