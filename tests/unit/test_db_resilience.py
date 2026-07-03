"""Tests for BOT-003 — SQLite DB Resilience.

8-10 unit tests using mock mode and tmp_path for DB files.
"""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from fire_suppression.telemetry.db_resilience import DBResilience, _db_msg


class TestDBResilience:
    """DBResilience unit tests."""

    # ── Core functionality ────────────────────────────────────────────────────

    def test_connect_applies_pragmas(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        conn = db.connect()
        cur = conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        conn.close()
        assert mode.lower() == "wal"

    def test_safe_execute_success(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        conn = db.connect()
        db.safe_execute(conn, "CREATE TABLE events (id INTEGER PRIMARY KEY)")
        db.safe_execute(conn, "INSERT INTO events (id) VALUES (?)", (1,))
        conn.commit()
        cur = conn.execute("SELECT id FROM events")
        assert cur.fetchone()[0] == 1
        conn.close()

    def test_safe_executemany_success(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        conn = db.connect()
        db.safe_execute(conn, "CREATE TABLE events (id INTEGER PRIMARY KEY)")
        db.safe_executemany(conn, "INSERT INTO events (id) VALUES (?)", [(2,), (3,), (4,)])
        conn.commit()
        cur = conn.execute("SELECT count(*) FROM events")
        assert cur.fetchone()[0] == 3
        conn.close()

    # ── Busy / retry ────────────────────────────────────────────────────────

    def test_safe_execute_retries_on_busy(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True, busy_retries=3, busy_delay=0.01)
        call_count = 0
        real_conn = sqlite3.connect(":memory:")

        class FakeConn:
            """Fake sqlite3 connection that fails twice with busy."""
            def execute(self, sql, params=()):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise sqlite3.OperationalError("database is locked")
                return real_conn.execute(sql, params)

            def close(self):
                pass

        with patch.object(db, "_apply_pragmas"), patch("sqlite3.connect", return_value=FakeConn()):
            conn = db.connect()
            cur = db.safe_execute(conn, "SELECT 1")
            result = cur.fetchone()[0]
            conn.close()

        real_conn.close()
        assert call_count == 2
        assert result == 1
        assert db._metrics["total_busy_retries"] >= 1

    def test_safe_execute_raises_after_max_retries(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True, busy_retries=2, busy_delay=0.01)

        class FakeConn:
            def execute(self, sql, params=()):
                raise sqlite3.OperationalError("database is busy")

            def close(self):
                pass

        with patch.object(db, "_apply_pragmas"), patch("sqlite3.connect", return_value=FakeConn()):
            conn = db.connect()
            with pytest.raises(sqlite3.OperationalError):
                db.safe_execute(conn, "SELECT 1")
            conn.close()

    # ── Corruption detection & recovery ─────────────────────────────────────

    def test_is_corrupt_returns_false_for_new_db(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        # DB doesn't exist yet
        assert db.is_corrupt() is False
        # Create valid DB
        conn = db.connect()
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.commit()
        conn.close()
        assert db.is_corrupt() is False

    def test_is_corrupt_returns_true_for_garbage(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db_path.write_text("this is not a valid sqlite database")
        db = DBResilience(str(db_path), mock=True)
        assert db.is_corrupt() is True

    def test_recover_restores_from_backup(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        # Build a valid DB with data
        conn = db.connect()
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.execute("INSERT INTO t (x) VALUES ('hello')")
        conn.commit()
        conn.close()

        # Create backup
        db.create_backup()

        # Corrupt the DB
        Path(db.db_path).write_text("garbage data")
        assert db.is_corrupt() is True

        # Recover
        recovered = db.recover()
        assert recovered is True
        assert db.is_corrupt() is False
        conn = db.connect()
        cur = conn.execute("SELECT x FROM t")
        assert cur.fetchone()[0] == "hello"
        conn.close()

    def test_recover_creates_fresh_when_no_backup(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db_path.write_text("not sqlite")
        db = DBResilience(str(db_path), mock=True)
        recovered = db.recover()
        assert recovered is False
        assert db.db_path.exists()
        assert db.is_corrupt() is False

    # ── Backup rotation ───────────────────────────────────────────────────────

    def test_backup_rotation(self, tmp_path: Path) -> None:
        import time as _time
        db = DBResilience(str(tmp_path / "test.db"), mock=True, max_backups=3)
        conn = db.connect()
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.commit()
        conn.close()

        # Create 5 backups; only 3 should remain
        for _ in range(5):
            db.create_backup()
            _time.sleep(0.02)  # ensure unique timestamps

        backups = db._list_backups()
        assert len(backups) == 3
        assert db._metrics["backup_rotations"] == 2

    # ── Introspection ─────────────────────────────────────────────────────────

    def test_health_check(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        conn = db.connect()
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.commit()
        conn.close()
        health = db.health_check()
        assert health["feature_id"] == "BOT-003"
        assert health["db_exists"] is True
        assert health["corrupt"] is False
        assert health["healthy"] is True
        assert "total_connections" in health
        assert "total_executions" in health

    def test_feature_overview(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        overview = db.get_feature_overview()
        assert overview["feature_id"] == "BOT-003"
        assert overview["feature_name"] == "SQLite DB Resilience"
        assert "pragma_wal" in overview["supports"]
        assert overview["max_backups"] == 5

    def test_to_dict(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "test.db"), mock=True)
        conn = db.connect()
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.commit()
        conn.close()
        data = db.to_dict()
        assert "overview" in data
        assert data["backup_count"] == 0
        assert data["backup_dir"] == str(db._backup_dir)

    # ── Bilingual messages ──────────────────────────────────────────────────

    def test_db_msg_bilingual(self) -> None:
        assert "initialised" in _db_msg("init", lang="en", path="/tmp/x.db")
        assert "imeanzishwa" in _db_msg("init", lang="sw", path="/tmp/x.db")

    def test_create_backup_no_db_raises(self, tmp_path: Path) -> None:
        db = DBResilience(str(tmp_path / "missing.db"), mock=True)
        with pytest.raises(FileNotFoundError):
            db.create_backup()
