"""Telemetry, logging, and event database for open-fire-suppression.

# T001 — SQLite Event Logging
# T006 — Log Rotation
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from fire_suppression.config import Config

if TYPE_CHECKING:
    from fire_suppression.sensors.base import SensorReading

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    sensor_name TEXT NOT NULL,
    values_json TEXT NOT NULL,
    raw_json TEXT,
    unit TEXT,
    health_status TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sensor_time ON sensor_readings(sensor_name, timestamp);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    message TEXT,
    details_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

CREATE TABLE IF NOT EXISTS detection_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    state TEXT NOT NULL,
    confidence REAL NOT NULL,
    triggered_sensors_json TEXT,
    thermal_hotspots_json TEXT,
    latency_ms REAL,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_detection_time ON detection_results(timestamp);

CREATE TABLE IF NOT EXISTS actuation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    duration REAL DEFAULT 0.0,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS power_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    source TEXT,
    battery_percent REAL,
    battery_voltage REAL,
    is_charging INTEGER,
    is_low_battery INTEGER,
    is_critical_battery INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS safety_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    state TEXT NOT NULL,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class TelemetryLogger:
    """SQLite-based telemetry and event logger with automatic rotation.

    All sensor readings, detection results, safety events, power status,
    and actuation events are logged to a local SQLite database.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        telem = self.config.section("telemetry")

        self.db_path = Path(telem.get("db_path", "/var/lib/fire-suppression/events.db"))
        self.max_size_mb = int(telem.get("max_db_size_mb", 100))
        self.archives_keep = int(telem.get("db_archives_keep", 10))
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Create tables and set up database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(CREATE_TABLES_SQL)
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
        self._conn.commit()
        logger.info("Telemetry DB initialized: %s", self.db_path)

    # ── Write methods ──

    def log_sensor_reading(self, reading: SensorReading, health_status: str = "ok") -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO sensor_readings
                   (timestamp, sensor_name, values_json, raw_json, unit, health_status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    reading.timestamp,
                    reading.sensor_name,
                    json.dumps(reading.values),
                    json.dumps(reading.raw) if reading.raw is not None else None,
                    reading.unit,
                    health_status,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Sensor reading log failed: %s", exc)

    def log_event(
        self,
        event_type: str,
        severity: str = "info",
        message: str = "",
        details: dict | None = None,
    ) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO events (timestamp, event_type, severity, message, details_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (time.time(), event_type, severity, message, json.dumps(details) if details else None),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Event log failed: %s", exc)

    def log_detection(self, result: dict) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO detection_results
                   (timestamp, state, confidence, triggered_sensors_json, thermal_hotspots_json, latency_ms, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.get("timestamp", time.time()),
                    result.get("state", ""),
                    result.get("confidence", 0.0),
                    json.dumps(result.get("triggered_sensors", [])),
                    json.dumps(result.get("thermal_hotspots", [])),
                    result.get("latency_ms", 0.0),
                    result.get("reason", ""),
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Detection log failed: %s", exc)

    def log_actuation(self, event_type: str, duration: float = 0.0, reason: str = "") -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO actuation_events (timestamp, event_type, duration, reason)
                   VALUES (?, ?, ?, ?)""",
                (time.time(), event_type, duration, reason),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Actuation log failed: %s", exc)

    def log_power_status(self, status: dict) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT INTO power_status
                   (timestamp, source, battery_percent, battery_voltage, is_charging, is_low_battery, is_critical_battery)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    status.get("timestamp", time.time()),
                    status.get("source", ""),
                    status.get("battery_percent", 0.0),
                    status.get("battery_voltage", 0.0),
                    1 if status.get("is_charging", False) else 0,
                    1 if status.get("is_low_battery", False) else 0,
                    1 if status.get("is_critical_battery", False) else 0,
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Power status log failed: %s", exc)

    def log_safety_state(self, state: str, reason: str = "") -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO safety_state (timestamp, state, reason) VALUES (?, ?, ?)",
                (time.time(), state, reason),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("Safety state log failed: %s", exc)

    # ── Read methods ──

    def get_sensor_history(
        self,
        sensor_name: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 100,
    ) -> list[dict]:
        if self._conn is None:
            return []
        query = "SELECT * FROM sensor_readings WHERE 1=1"
        params: list = []
        if sensor_name:
            query += " AND sensor_name = ?"
            params.append(sensor_name)
        if start_time is not None:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time is not None:
            query += " AND timestamp <= ?"
            params.append(end_time)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_events(
        self,
        event_type: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        if self._conn is None:
            return []
        query = "SELECT * FROM events WHERE 1=1"
        params: list = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_latest_status(self) -> dict:
        """Return a summary of the latest system state from all tables."""
        if self._conn is None:
            return {}
        status = {}
        # Latest detection
        row = self._conn.execute(
            "SELECT * FROM detection_results ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row:
            status["latest_detection"] = dict(row)
        # Latest power
        row = self._conn.execute(
            "SELECT * FROM power_status ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row:
            status["latest_power"] = dict(row)
        # Latest safety
        row = self._conn.execute(
            "SELECT * FROM safety_state ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row:
            status["latest_safety"] = dict(row)
        # Event count (last hour)
        hour_ago = time.time() - 3600
        count = self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE timestamp > ?", (hour_ago,)
        ).fetchone()[0]
        status["events_last_hour"] = count
        return status

    # ── Rotation ──

    def check_and_rotate(self) -> bool:
        """Check database size and rotate if exceeding threshold.

        Returns True if rotation occurred.
        """
        if not self.db_path.exists():
            return False
        size_mb = self.db_path.stat().st_size / (1024 * 1024)
        if size_mb < self.max_size_mb:
            return False

        logger.info("DB size %.1f MB exceeds %d MB threshold — rotating", size_mb, self.max_size_mb)

        # Close connection
        if self._conn:
            self._conn.close()
            self._conn = None

        # Rotate: rename current db with timestamp
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        archive = self.db_path.parent / f"{self.db_path.stem}_{timestamp}.db"
        shutil.move(str(self.db_path), str(archive))
        logger.info("Rotated DB to %s", archive)

        # Clean up old archives
        archives = sorted(
            self.db_path.parent.glob(f"{self.db_path.stem}_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in archives[self.archives_keep:]:
            old.unlink()
            logger.info("Removed old archive: %s", old)

        # Re-init new database
        self._init_db()
        return True

    # ── Cleanup ──

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        logger.info("Telemetry logger closed")
