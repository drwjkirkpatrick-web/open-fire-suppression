"""Tests for BOT-010 — System Watchdog."""
from pathlib import Path

import pytest

from fire_suppression.diagnostics.watchdog import Watchdog


class TestWatchdog:
    def test_init_mock(self, tmp_path: Path) -> None:
        wd = Watchdog(data_dir=tmp_path, mock=True)
        health = wd.health_check()
        assert health["mock"] is True
        assert health["total_feeds"] == 0
        assert health["total_timeouts"] == 0

    def test_feed_resets_timeout(self, tmp_path: Path) -> None:
        wd = Watchdog(timeout_sec=1.0, data_dir=tmp_path, mock=True)
        wd.start()
        wd.feed()
        import time
        time.sleep(0.2)
        health = wd.health_check()
        assert health["elapsed_since_feed"] < 1.0
        wd.stop()

    def test_start_stop(self, tmp_path: Path) -> None:
        wd = Watchdog(data_dir=tmp_path, mock=True)
        assert wd._running is False
        wd.start()
        assert wd._running is True
        wd.stop()
        assert wd._running is False

    def test_health_degrades_when_not_fed(self, tmp_path: Path) -> None:
        wd = Watchdog(timeout_sec=0.5, data_dir=tmp_path, mock=True)
        wd.start()
        import time
        time.sleep(0.7)
        health = wd.health_check()
        assert health["elapsed_since_feed"] >= 0.5
        assert health["healthy"] is False
        wd.stop()

    def test_total_feeds_increment(self, tmp_path: Path) -> None:
        wd = Watchdog(data_dir=tmp_path, mock=True)
        wd.feed()
        wd.feed()
        assert wd.health_check()["total_feeds"] == 2

    def test_set_on_timeout(self, tmp_path: Path) -> None:
        called = False

        def cb():
            nonlocal called
            called = True

        wd = Watchdog(data_dir=tmp_path, mock=True)
        wd.set_on_timeout(cb)
        assert wd._on_timeout is cb

    def test_feature_overview(self, tmp_path: Path) -> None:
        wd = Watchdog(data_dir=tmp_path, mock=True)
        ov = wd.get_feature_overview()
        assert ov["feature_id"] == "BOT-010"
        assert "heartbeat" in ov["supports"]

    def test_to_dict(self, tmp_path: Path) -> None:
        wd = Watchdog(data_dir=tmp_path, mock=True)
        d = wd.to_dict()
        assert "healthy" in d
        assert "total_feeds" in d
