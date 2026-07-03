"""SQLite database resilience layer with corruption recovery.

# BOT-003 — SQLite DB Resilience

Wraps sqlite3 connections with robustness PRAGMAs, auto-detects corruption,
recreates from rotated backups, retries on busy/locked, and tracks health
metrics.  All lifecycle messages are bilingual (English / Swahili).

Usage::

    from fire_suppression.telemetry.db_resilience import DBResilience
    db = DBResilience("/opt/fire-suppression/data/events.db", mock=True)
    conn = db.connect()
    db.safe_execute(conn, "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY)")
    conn.close()

    health = db.health_check()
    overview = db.get_feature_overview()
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Bilingual messages ──────────────────────────────────────────────────────
_DB_MSGS = {
    "init": {
        "en": "DB resilience layer initialised for {path}",
        "sw": "Tabaka la uimara wa DB limeanzishwa kwa {path}",
    },
    "pragma_applied": {
        "en": "Robustness PRAGMAs applied (WAL, NORMAL sync, memory temp_store).",
        "sw": "PRAGMA za uimara zimetumika (WAL, NORMAL sync, memory temp_store).",
    },
    "corrupt_detected": {
        "en": "Database corruption detected — rotating backups and rebuilding.",
        "sw": "Uharibifu wa hifadhidata umeonekana — backup zinarotetiwa na kujengwa upya.",
    },
    "recovered": {
        "en": "Database recovered from backup {backup}",
        "sw": "Hifadhidata imepona kutoka kwenye backup {backup}",
    },
    "no_backup": {
        "en": "No valid backup found — creating fresh database.",
        "sw": "Hakuna backup sahihi — hifadhidata mpya inatengenezwa.",
    },
    "backup_created": {
        "en": "Backup created at {path}",
        "sw": "Backup imetengenezwa kwenye {path}",
    },
    "backup_rotated": {
        "en": "Old backup {path} removed (keep={keep})",
        "sw": "Backup ya zamani {path} imeondolewa (keep={keep})",
    },
    "busy_retry": {
        "en": "Database busy/locked — retrying ({attempt}/{max_attempts}).",
        "sw": "Hifadhidata busy/fungwa — inajaribu tena ({attempt}/{max_attempts}).",
    },
    "exec_failed": {
        "en": "Safe execute failed after {attempts} attempts: {error}",
        "sw": "Kutekeleza salama kumeshindwa baada ya majaribu {attempts}: {error}",
    },
}


def _db_msg(key: str, lang: str = "en", **kwargs: Any) -> str:
    m = _DB_MSGS.get(key, {})
    return m.get(lang, m.get("en", key)).format(**kwargs)


class DBResilience:
    """Robust SQLite wrapper with corruption recovery and health tracking.

    Usage::

        db = DBResilience("/var/lib/fire-suppression/events.db", mock=True)
        conn = db.connect()
        db.safe_execute(conn, "SELECT 1")
        conn.close()
    """

    feature_id: str = "BOT-003"

    def __init__(
        self,
        db_path: str | Path,
        *,
        mock: bool = False,
        max_backups: int = 5,
        busy_retries: int = 5,
        busy_delay: float = 0.05,
    ) -> None:
        self.db_path = Path(db_path)
        self.mock = mock
        self.max_backups = max_backups
        self.busy_retries = busy_retries
        self.busy_delay = busy_delay
        self._backup_dir = self.db_path.parent / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # Health metrics
        self._metrics = {
            "total_connections": 0,
            "total_executions": 0,
            "total_busy_retries": 0,
            "corruption_events": 0,
            "recovery_events": 0,
            "backup_creates": 0,
            "backup_rotations": 0,
            "last_health_check": 0.0,
            "healthy": True,
        }

        logger.info(_db_msg("init", path=str(self.db_path)))

    # ── Connection wrapper ──────────────────────────────────────────────────

    def connect(self, **kwargs: Any) -> sqlite3.Connection:
        """Open a connection with robustness PRAGMAs applied."""
        kwargs.setdefault("timeout", 10.0)
        conn = sqlite3.connect(str(self.db_path), **kwargs)
        self._apply_pragmas(conn)
        self._metrics["total_connections"] += 1
        return conn

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply WAL, NORMAL sync, and memory temp_store."""
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=memory")
        conn.execute("PRAGMA foreign_keys=ON")
        logger.debug(_db_msg("pragma_applied"))

    # ── Safe execution wrappers ───────────────────────────────────────────────

    def safe_execute(
        self,
        conn: sqlite3.Connection,
        sql: str,
        parameters: tuple[Any, ...] | list[Any] | None = None,
    ) -> sqlite3.Cursor:
        """Execute with retry on busy/locked."""
        params = parameters or ()
        last_exc: Exception | None = None
        for attempt in range(1, self.busy_retries + 1):
            try:
                cur = conn.execute(sql, params)
                self._metrics["total_executions"] += 1
                return cur
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "busy" in str(exc).lower() or "locked" in str(exc).lower():
                    self._metrics["total_busy_retries"] += 1
                    logger.warning(
                        _db_msg("busy_retry", attempt=attempt, max_attempts=self.busy_retries)
                    )
                    time.sleep(self.busy_delay * attempt)
                    continue
                raise
        logger.error(
            _db_msg("exec_failed", attempts=self.busy_retries, error=last_exc)
        )
        raise last_exc  # type: ignore[misc]

    def safe_executemany(
        self,
        conn: sqlite3.Connection,
        sql: str,
        parameters: list[tuple[Any, ...]],
    ) -> sqlite3.Cursor:
        """Execute many with retry on busy/locked."""
        last_exc: Exception | None = None
        for attempt in range(1, self.busy_retries + 1):
            try:
                cur = conn.executemany(sql, parameters)
                self._metrics["total_executions"] += 1
                return cur
            except sqlite3.OperationalError as exc:
                last_exc = exc
                if "busy" in str(exc).lower() or "locked" in str(exc).lower():
                    self._metrics["total_busy_retries"] += 1
                    logger.warning(
                        _db_msg("busy_retry", attempt=attempt, max_attempts=self.busy_retries)
                    )
                    time.sleep(self.busy_delay * attempt)
                    continue
                raise
        logger.error(
            _db_msg("exec_failed", attempts=self.busy_retries, error=last_exc)
        )
        raise last_exc  # type: ignore[misc]

    # ── Corruption detection & recovery ───────────────────────────────────────

    def is_corrupt(self) -> bool:
        """Check if the database is corrupt via PRAGMA integrity_check."""
        if not self.db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=2.0)
            cur = conn.execute("PRAGMA integrity_check")
            result = cur.fetchone()
            conn.close()
            return result is None or result[0] != "ok"
        except sqlite3.DatabaseError:
            return True

    def recover(self) -> bool:
        """Recover from corruption by restoring the most recent valid backup.

        Returns True if recovery succeeded, False if no backup was available
        and a fresh DB was created.
        """
        if not self.is_corrupt():
            return True

        self._metrics["corruption_events"] += 1
        logger.critical(_db_msg("corrupt_detected"))

        # Move corrupt DB out of the way
        corrupt_path = self.db_path.with_suffix(f".corrupt.{int(time.time())}.db")
        if self.db_path.exists():
            shutil.move(str(self.db_path), str(corrupt_path))

        # Find most recent valid backup
        backups = self._list_backups()
        for backup in sorted(backups, reverse=True):
            if self._verify_backup(backup):
                shutil.copy(str(backup), str(self.db_path))
                self._metrics["recovery_events"] += 1
                logger.info(_db_msg("recovered", backup=str(backup)))
                return True

        # No valid backup — create empty database
        logger.warning(_db_msg("no_backup"))
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
        conn.close()
        return False

    def _verify_backup(self, backup_path: Path) -> bool:
        """Verify a backup file is a valid SQLite database."""
        try:
            conn = sqlite3.connect(str(backup_path), timeout=2.0)
            cur = conn.execute("PRAGMA integrity_check")
            result = cur.fetchone()
            conn.close()
            return result is not None and result[0] == "ok"
        except sqlite3.DatabaseError:
            return False

    # ── Backup rotation ───────────────────────────────────────────────────────

    def create_backup(self) -> Path:
        """Create a timestamped backup of the current database."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Cannot backup — DB does not exist: {self.db_path}")

        ts = int(time.time() * 1000)
        backup_path = self._backup_dir / f"{self.db_path.stem}_backup_{ts}.db"
        shutil.copy2(str(self.db_path), str(backup_path))
        self._metrics["backup_creates"] += 1
        logger.info(_db_msg("backup_created", path=str(backup_path)))
        self._rotate_backups()
        return backup_path

    def _list_backups(self) -> list[Path]:
        """List all backup files for this database, sorted oldest first."""
        pattern = f"{self.db_path.stem}_backup_*.db"
        # Sort by embedded timestamp in filename for deterministic order
        return sorted(self._backup_dir.glob(pattern), key=lambda p: p.name)

    def _rotate_backups(self) -> None:
        """Remove oldest backups exceeding max_backups."""
        backups = self._list_backups()
        while len(backups) > self.max_backups:
            oldest = backups.pop(0)
            try:
                oldest.unlink()
                self._metrics["backup_rotations"] += 1
                logger.info(
                    _db_msg("backup_rotated", path=str(oldest), keep=self.max_backups)
                )
            except OSError as exc:
                logger.warning("Failed to remove old backup %s: %s", oldest, exc)

    # ── Health check ──────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Return current health metrics and status."""
        corrupt = self.is_corrupt()
        healthy = not corrupt
        self._metrics["healthy"] = healthy
        self._metrics["last_health_check"] = time.time()

        return {
            "feature_id": self.feature_id,
            "db_path": str(self.db_path),
            "db_exists": self.db_path.exists(),
            "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "corrupt": corrupt,
            "healthy": healthy,
            "mock": self.mock,
            **self._metrics,
        }

    # ── Feature overview ──────────────────────────────────────────────────────

    def get_feature_overview(self) -> dict[str, Any]:
        """Return feature metadata for dashboards / introspection."""
        return {
            "feature_id": self.feature_id,
            "feature_name": "SQLite DB Resilience",
            "description": (
                "Robust SQLite wrapper with WAL, corruption recovery, "
                "backup rotation, and busy-retry execution."
            ),
            "mock": self.mock,
            "supports": [
                "pragma_wal",
                "corruption_detection",
                "backup_rotation",
                "busy_retry",
                "health_metrics",
            ],
            "max_backups": self.max_backups,
            "busy_retries": self.busy_retries,
            "busy_delay_sec": self.busy_delay,
        }

    # ── Dict representation ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Merge health check and overview for serialization."""
        return {
            **self.health_check(),
            "overview": self.get_feature_overview(),
            "backup_count": len(self._list_backups()),
            "backup_dir": str(self._backup_dir),
        }
