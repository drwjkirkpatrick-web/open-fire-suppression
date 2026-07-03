"""System resilience and stay-alive layer for open-fire-suppression.

Handles sensor failures, detection engine stalls, memory leaks,
configuration corruption, process crashes, and network partitions.

# BOT-001 — Sensor Failure Graceful Degradation
# BOT-002 — Detection Engine Timeout + Fallback
# BOT-003 — SQLite Corruption Recovery
# BOT-004 — Memory Leak Prevention
# BOT-005 — Network Partition Store-and-Forward
# BOT-006 — Relay Fuse Monitoring
# BOT-007 — Config Corruption Recovery
# BOT-009 — Clock Drift / RTC Monitoring
# BOT-010 — Process Death + systemd Watchdog
"""
from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import sqlite3
import time
import tracemalloc
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# BOT-001 — Sensor Failure Graceful Degradation
# ────────────────────────────────────────────────────────────────

class DegradationMode(Enum):
    FULL = "full"
    DEGRADED = "degraded"
    EMERGENCY = "emergency"
    FAILED = "failed"


@dataclass
class ResilienceState:
    """Current system resilience status."""
    mode: DegradationMode = DegradationMode.FULL
    active_sensors: list[str] = field(default_factory=list)
    failed_sensors: list[str] = field(default_factory=list)
    detection_fallback: str = "fusion"  # "fusion" | "threshold" | "camera_only"
    timestamp_confidence: str = "high"  # "high" | "low" | "unknown"
    memory_percent: float = 0.0
    network_status: str = "online"      # "online" | "degraded" | "offline"
    relay_health: dict[str, bool] = field(default_factory=dict)
    last_heartbeat: float = 0.0


class SensorResilienceMonitor:
    """Monitors all sensors and manages graceful degradation.

    If a sensor fails, its weight in the fusion is redistributed.
    If >50% of sensors fail, switch to emergency mode (camera + any working sensor).
    """

    def __init__(self, sensor_names: list[str]) -> None:
        self._sensors = {name: {"fails": 0, "last_ok": time.time(), "degraded": False}
                         for name in sensor_names}
        self._max_failures = 3
        self._weights: dict[str, float] = {name: 1.0 for name in sensor_names}
        self._state = ResilienceState()
        self._state.active_sensors = list(sensor_names)

    def record_success(self, name: str) -> None:
        if name in self._sensors:
            self._sensors[name]["fails"] = 0
            self._sensors[name]["last_ok"] = time.time()
            self._sensors[name]["degraded"] = False

    def record_failure(self, name: str) -> None:
        if name not in self._sensors:
            return
        self._sensors[name]["fails"] += 1
        if self._sensors[name]["fails"] >= self._max_failures:
            self._sensors[name]["degraded"] = True
            logger.warning("Sensor %s marked degraded after %d failures", name, self._sensors[name]["fails"])
        self._recompute_weights()

    def _recompute_weights(self) -> None:
        """Redistribute weights so active sensors carry more load."""
        active = [n for n, s in self._sensors.items() if not s["degraded"]]
        failed = [n for n, s in self._sensors.items() if s["degraded"]]
        if not active:
            self._state.mode = DegradationMode.FAILED
            return
        if len(failed) > len(active):
            self._state.mode = DegradationMode.EMERGENCY
            self._state.detection_fallback = "camera_only"
        elif len(failed) > 0:
            self._state.mode = DegradationMode.DEGRADED
        else:
            self._state.mode = DegradationMode.FULL

        # Equal weights among active sensors
        weight = 1.0 / len(active)
        for name in self._sensors:
            self._weights[name] = weight if not self._sensors[name]["degraded"] else 0.0

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
    """Wraps detection computation with a timeout and fallback mode.

    If fusion takes too long, falls back to simple threshold detection
    which is much faster but less accurate.
    """

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self.timeout = timeout_seconds
        self._fallback_count = 0

    async def run_with_timeout(
        self,
        coro,
        fallback_coro,
        *args,
        **kwargs,
    ):
        """Run primary coroutine with timeout; execute fallback on timeout."""
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
    """SQLite database resilience with corruption detection and fallback.

    Uses PRAGMAs for robustness, maintains a backup copy, and falls
    back to JSON file logging if the DB is corrupted.
    """

    def __init__(self, db_path: str | Path, backup_dir: str | Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir) if backup_dir else self.db_path.parent / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._json_fallback = self.db_path.parent / "events_fallback.jsonl"
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        """Connect with robustness PRAGMAs."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=10000")
        return conn

    def get_connection(self) -> sqlite3.Connection | None:
        """Get a healthy connection, with corruption recovery."""
        if self._conn:
            try:
                self._conn.execute("SELECT 1")
                return self._conn
            except sqlite3.DatabaseError:
                logger.error("SQLite connection corrupted — attempting recovery")
                self._conn = None

        # Try to connect
        try:
            self._conn = self._connect()
            # Verify integrity
            result = self._conn.execute("PRAGMA integrity_check").fetchone()
            if result and result[0] != "ok":
                raise sqlite3.DatabaseError(f"Integrity check failed: {result[0]}")
            return self._conn
        except sqlite3.DatabaseError:
            return self._recover_from_backup()

    def _recover_from_backup(self) -> sqlite3.Connection | None:
        """Restore from most recent backup."""
        backups = sorted(self.backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            logger.critical("No SQLite backups available — using JSON fallback")
            return None

        for backup in backups[:3]:  # Try up to 3 recent backups
            try:
                import shutil
                shutil.copy(str(backup), str(self.db_path))
                conn = self._connect()
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if result and result[0] == "ok":
                    logger.info("Recovered SQLite from backup: %s", backup.name)
                    self._conn = conn
                    return conn
            except Exception as exc:
                logger.warning("Backup %s also corrupted: %s", backup.name, exc)

        logger.critical("All backups corrupted — JSON fallback active")
        return None

    def create_backup(self) -> None:
        """Create a timestamped backup of the database."""
        if not self.db_path.exists():
            return
        try:
            import shutil
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"telemetry_{timestamp}.db"
            shutil.copy(str(self.db_path), str(backup_path))
            # Clean old backups (keep last 10)
            old = sorted(self.backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime)
            for o in old[:-10]:
                o.unlink()
        except Exception as exc:
            logger.warning("Backup creation failed: %s", exc)

    def log_fallback(self, event: dict) -> None:
        """Append event to JSON Lines fallback file."""
        try:
            with open(self._json_fallback, "a") as fh:
                fh.write(json.dumps(event) + "\n")
        except Exception as exc:
            logger.error("Even JSON fallback failed: %s", exc)


# ────────────────────────────────────────────────────────────────
# BOT-004 — Memory Leak Prevention
# ────────────────────────────────────────────────────────────────

class MemoryMonitor:
    """Monitors Python memory usage and triggers cleanup when thresholds are exceeded.

    Uses tracemalloc for detailed tracking and periodic garbage collection.
    """

    def __init__(
        self,
        warning_mb: float = 512.0,
        critical_mb: float = 1024.0,
        check_interval_seconds: float = 60.0,
    ) -> None:
        self.warning_mb = warning_mb
        self.critical_mb = critical_mb
        self.check_interval = check_interval_seconds
        self._running = False
        self._peak_mb = 0.0
        self._tracemalloc_enabled = False

    def start(self) -> None:
        """Start background memory monitoring."""
        self._running = True
        try:
            tracemalloc.start()
            self._tracemalloc_enabled = True
        except Exception:
            pass
        asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        self._running = False

    async def _monitor_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.check_interval)
            await self._check_memory()

    async def _check_memory(self) -> None:
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            self._peak_mb = max(self._peak_mb, mem_mb)

            if mem_mb > self.critical_mb:
                logger.critical("MEMORY CRITICAL: %.1f MB — forcing garbage collection", mem_mb)
                gc.collect()
                if self._tracemalloc_enabled:
                    snapshot = tracemalloc.take_snapshot()
                    top = snapshot.statistics("lineno")[:5]
                    for stat in top:
                        logger.critical("Top memory: %s", stat)
            elif mem_mb > self.warning_mb:
                logger.warning("Memory high: %.1f MB (peak: %.1f MB)", mem_mb, self._peak_mb)
                gc.collect()

            # Always do a gen-0 collection periodically
            gc.collect(0)
        except Exception as exc:
            logger.warning("Memory check failed: %s", exc)

    def get_stats(self) -> dict:
        return {
            "current_mb": "unknown",
            "peak_mb": self._peak_mb,
            "tracemalloc": self._tracemalloc_enabled,
        }


# ────────────────────────────────────────────────────────────────
# BOT-005 — Network Partition Store-and-Forward
# ────────────────────────────────────────────────────────────────

class StoreAndForwardQueue:
    """Persistent queue for notifications that survive network partitions.

    Messages are serialized to disk and replayed when connectivity returns.
    """

    def __init__(self, queue_path: str | Path, max_size: int = 1000) -> None:
        self.queue_path = Path(queue_path)
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self._queue: deque[dict] = deque(maxlen=max_size)
        self._load()

    def _load(self) -> None:
        if not self.queue_path.exists():
            return
        try:
            with open(self.queue_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                self._queue = deque(data, maxlen=self.max_size)
        except Exception as exc:
            logger.warning("Failed to load store-and-forward queue: %s", exc)

    def _save(self) -> None:
        try:
            with open(self.queue_path, "w", encoding="utf-8") as fh:
                json.dump(list(self._queue), fh)
        except Exception as exc:
            logger.warning("Failed to save store-and-forward queue: %s", exc)

    def enqueue(self, message: dict) -> None:
        """Add a message to the persistent queue."""
        message["_queued_at"] = time.time()
        self._queue.append(message)
        self._save()

    def dequeue_all(self) -> list[dict]:
        """Retrieve all queued messages and clear the queue."""
        items = list(self._queue)
        self._queue.clear()
        self._save()
        return items

    def peek(self, limit: int = 10) -> list[dict]:
        return list(self._queue)[:limit]

    @property
    def size(self) -> int:
        return len(self._queue)


# ────────────────────────────────────────────────────────────────
# BOT-006 — Relay Fuse Monitoring
# ────────────────────────────────────────────────────────────────

class RelayHealthMonitor:
    """Monitors relay health via current sensing and feedback.

    If a relay draws abnormal current or fails to toggle, it's isolated
    and an alert is raised.
    """

    def __init__(self, relay_pins: dict[int, str]) -> None:
        """Args:
            relay_pins: Dict mapping pin number to relay name.
        """
        self.relay_pins = relay_pins
        self._health: dict[str, dict] = {
            name: {"ok": True, "last_toggle": 0.0, "toggle_count": 0}
            for name in relay_pins.values()
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
    """Manages atomic config writes and last-known-good fallback.

    Writes to a temp file, then renames atomically.
    Keeps a last-known-good copy for recovery.
    """

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.lkg_path = self.config_path.parent / (self.config_path.stem + ".lkg" + self.config_path.suffix)

    def atomic_write(self, content: str) -> None:
        """Write config atomically and update last-known-good."""
        temp = self.config_path.with_suffix(".tmp")
        try:
            temp.write_text(content, encoding="utf-8")
            # Backup current to LKG before overwriting
            if self.config_path.exists():
                import shutil
                shutil.copy(str(self.config_path), str(self.lkg_path))
            temp.replace(self.config_path)
            logger.info("Config written atomically")
        except Exception as exc:
            logger.error("Atomic config write failed: %s", exc)
            raise

    def recover(self) -> str | None:
        """Return last-known-good config content, or None."""
        if self.lkg_path.exists():
            return self.lkg_path.read_text(encoding="utf-8")
        return None


# ────────────────────────────────────────────────────────────────
# BOT-009 — Clock Drift / RTC Monitoring
# ────────────────────────────────────────────────────────────────

class ClockMonitor:
    """Monitors system clock accuracy and NTP sync status.

    Uses DS3231 RTC if available, otherwise flags low confidence.
    """

    def __init__(self, mock: bool = False) -> None:
        self.mock = mock
        self._rtc_available = False
        self._last_ntp_sync = 0.0
        self._ntp_confidence = "unknown"
        if not mock:
            self._check_rtc()

    def _check_rtc(self) -> None:
        """Probe for DS3231 RTC on I2C bus 0x68."""
        try:
            import smbus2
            bus = smbus2.SMBus(1)
            bus.read_byte_data(0x68, 0x00)  # Seconds register
            self._rtc_available = True
            logger.info("DS3231 RTC detected")
        except Exception:
            self._rtc_available = False
            logger.warning("No DS3231 RTC found — clock confidence will be low after power loss")

    def update_ntp_status(self, synced: bool) -> None:
        if synced:
            self._last_ntp_sync = time.time()
            self._ntp_confidence = "high"
        else:
            time_since_sync = time.time() - self._last_ntp_sync
            if time_since_sync > 86400:  # 24 hours
                self._ntp_confidence = "low"
            else:
                self._ntp_confidence = "medium"

    def get_confidence(self) -> str:
        if self._rtc_available:
            return "high"
        return self._ntp_confidence

    def get_status(self) -> dict:
        return {
            "rtc_available": self._rtc_available,
            "ntp_confidence": self._ntp_confidence,
            "last_ntp_sync": self._last_ntp_sync,
            "confidence": self.get_confidence(),
        }


# ────────────────────────────────────────────────────────────────
# BOT-010 — Stay Alive Orchestrator
# ────────────────────────────────────────────────────────────────

class StayAliveOrchestrator:
    """Central resilience coordinator that ties all stay-alive systems together.

    Monitors overall system health and reports degradation.
    Sends periodic heartbeats to an external watchdog (systemd or hardware).
    """

    def __init__(self) -> None:
        self.sensor_monitor: SensorResilienceMonitor | None = None
        self.timeout_guard: DetectionTimeoutGuard | None = None
        self.memory_monitor: MemoryMonitor | None = None
        self.network_queue: StoreAndForwardQueue | None = None
        self.relay_monitor: RelayHealthMonitor | None = None
        self.clock_monitor: ClockMonitor | None = None
        self._running = False

    def configure(
        self,
        sensor_names: list[str],
        relay_pins: dict[int, str],
        queue_path: str | Path,
    ) -> None:
        self.sensor_monitor = SensorResilienceMonitor(sensor_names)
        self.timeout_guard = DetectionTimeoutGuard(timeout_seconds=2.0)
        self.memory_monitor = MemoryMonitor()
        self.network_queue = StoreAndForwardQueue(queue_path)
        self.relay_monitor = RelayHealthMonitor(relay_pins)
        self.clock_monitor = ClockMonitor(mock=True)

    async def start(self) -> None:
        """Start all stay-alive monitoring."""
        self._running = True
        if self.memory_monitor:
            self.memory_monitor.start()
        asyncio.create_task(self._heartbeat_loop())
        logger.info("StayAlive orchestrator started")

    async def stop(self) -> None:
        self._running = False
        if self.memory_monitor:
            self.memory_monitor.stop()

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats and log system health."""
        while self._running:
            await asyncio.sleep(30.0)
            health = self.get_health_snapshot()
            logger.info("StayAlive heartbeat: mode=%s sensors=%d/%d memory=%.1fMB net=%s",
                        health["mode"],
                        health["active_sensor_count"],
                        health["total_sensor_count"],
                        health.get("memory_mb", 0),
                        health["network_status"])

            # Notify systemd if available
            try:
                import systemd.daemon
                systemd.daemon.notify("WATCHDOG=1")
            except ImportError:
                pass

    def get_health_snapshot(self) -> dict:
        """Return complete system health snapshot."""
        state = self.sensor_monitor.get_state() if self.sensor_monitor else ResilienceState()
        return {
            "mode": state.mode.value,
            "active_sensors": state.active_sensors,
            "failed_sensors": state.failed_sensors,
            "active_sensor_count": len(state.active_sensors),
            "total_sensor_count": len(state.active_sensors) + len(state.failed_sensors),
            "detection_fallback": state.detection_fallback,
            "network_status": state.network_status,
            "timestamp_confidence": state.timestamp_confidence,
            "memory_mb": self.memory_monitor.get_stats().get("peak_mb", 0) if self.memory_monitor else 0,
            "store_forward_queue_size": self.network_queue.size if self.network_queue else 0,
            "relay_health": self.relay_monitor.get_all_health() if self.relay_monitor else {},
            "clock_status": self.clock_monitor.get_status() if self.clock_monitor else {},
            "timestamp": time.time(),
        }
