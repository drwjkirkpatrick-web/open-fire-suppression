"""Tests for the memory monitor module.

# BOT-004 — Memory Monitor Tests
"""
import asyncio

import pytest

from fire_suppression.diagnostics.memory_monitor import (
    AlertLevel,
    MemoryAlert,
    MemoryMonitor,
    MemorySnapshot,
    MemoryTrend,
)


class TestMemoryMonitor:
    """# BOT-004 — Memory Monitor"""

    def test_init_defaults(self) -> None:
        mm = MemoryMonitor(mock=True)
        assert mm.max_mb == 512
        assert mm.warn_mb == pytest.approx(409.6, rel=1e-3)
        assert mm.critical_mb == pytest.approx(460.8, rel=1e-3)
        assert mm.auto_gc is True
        assert mm.mock is True
        assert mm.feature_id == "BOT-004"

    def test_init_custom_thresholds(self) -> None:
        mm = MemoryMonitor(max_mb=256, warn_percent=70, critical_percent=85, mock=True)
        assert mm.max_mb == 256
        assert mm.warn_mb == pytest.approx(179.2, rel=1e-3)
        assert mm.critical_mb == pytest.approx(217.6, rel=1e-3)

    def test_sample_mock(self) -> None:
        mm = MemoryMonitor(mock=True)
        snap = mm._sample()
        assert isinstance(snap, MemorySnapshot)
        assert snap.rss_mb > 0
        assert snap.vms_mb > 0
        assert snap.alert_level in {AlertLevel.NONE, AlertLevel.WARN, AlertLevel.CRITICAL}
        assert snap.trend in {MemoryTrend.UNKNOWN, MemoryTrend.INCREASING, MemoryTrend.STABLE, MemoryTrend.DECREASING}

    def test_sample_warn_threshold(self) -> None:
        mm = MemoryMonitor(max_mb=100, warn_percent=80, critical_percent=90, mock=True)
        mm.set_mock_rss(85.0)
        snap = mm._sample()
        assert snap.alert_level == AlertLevel.WARN

    def test_sample_critical_threshold(self) -> None:
        mm = MemoryMonitor(max_mb=100, warn_percent=80, critical_percent=90, mock=True)
        mm.set_mock_rss(95.0)
        snap = mm._sample()
        assert snap.alert_level == AlertLevel.CRITICAL

    def test_trend_increasing(self) -> None:
        mm = MemoryMonitor(mock=True)
        mm.set_mock_rss(100.0)
        mm._sample()
        mm.set_mock_rss(120.0)
        snap = mm._sample()
        assert snap.trend == MemoryTrend.INCREASING

    def test_trend_stable(self) -> None:
        mm = MemoryMonitor(mock=True)
        mm.set_mock_rss(100.0)
        mm._sample()
        mm.set_mock_rss(100.5)
        snap = mm._sample()
        assert snap.trend == MemoryTrend.STABLE

    def test_trend_decreasing(self) -> None:
        mm = MemoryMonitor(mock=True)
        mm.set_mock_rss(200.0)
        mm._sample()
        mm.set_mock_rss(150.0)
        snap = mm._sample()
        assert snap.trend == MemoryTrend.DECREASING

    def test_alert_recorded(self) -> None:
        mm = MemoryMonitor(max_mb=100, warn_percent=80, critical_percent=90, mock=True)
        mm.set_mock_rss(85.0)
        mm._sample()
        alerts = mm.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARN
        assert "warning threshold" in alerts[0].message_en.lower() or "onyo" in alerts[0].message_sw.lower()

    def test_health_check(self) -> None:
        mm = MemoryMonitor(mock=True)
        mm.set_mock_rss(123.0)
        mm._sample()
        health = mm.health_check()
        assert health["healthy"] is True
        assert health["rss_mb"] == pytest.approx(123.0, rel=1e-3)
        assert health["mock"] is True
        assert "trend" in health
        assert "alert_level" in health

    def test_get_feature_overview(self) -> None:
        mm = MemoryMonitor(mock=True)
        overview = mm.get_feature_overview()
        assert overview["feature_id"] == "BOT-004"
        assert overview["feature_name"] == "Memory Monitor"
        assert "supports" in overview
        assert "rss_vms_monitoring" in overview["supports"]

    def test_to_dict(self) -> None:
        mm = MemoryMonitor(mock=True)
        mm.set_mock_rss(50.0)
        mm._sample()
        d = mm.to_dict()
        assert d["feature_id"] == "BOT-004"
        assert d["rss_mb"] == pytest.approx(50.0, rel=1e-3)
        assert d["history_count"] == 1
        assert "latest_snapshot" in d
        assert d["latest_snapshot"]["rss_mb"] == pytest.approx(50.0, rel=1e-3)

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        mm = MemoryMonitor(mock=True, interval_s=0.1)
        await mm.start()
        assert mm._running is True
        assert mm._task is not None
        await asyncio.sleep(0.25)
        await mm.stop()
        assert mm._running is False
        assert mm._task is None

    def test_alert_to_dict(self) -> None:
        alert = MemoryAlert(
            timestamp=0.0,
            level=AlertLevel.WARN,
            rss_mb=123.0,
            threshold_mb=100.0,
            message_en="warn",
            message_sw="onyo",
        )
        d = alert.to_dict()
        assert d["level"] == "warn"
        assert d["rss_mb"] == 123.0
        assert d["message_sw"] == "onyo"

    def test_snapshot_to_dict(self) -> None:
        snap = MemorySnapshot(
            timestamp=0.0,
            rss_mb=10.0,
            vms_mb=20.0,
            percent_of_max=5.0,
            alert_level=AlertLevel.NONE,
            trend=MemoryTrend.UNKNOWN,
        )
        d = snap.to_dict()
        assert d["rss_mb"] == 10.0
        assert d["trend"] == "unknown"
        assert d["alert_level"] == "none"
