"""Tests for the Intrusion Detection System (SEC-003).

# SEC-003 — Intrusion Detection System Tests
"""
import asyncio
import os
import time
from pathlib import Path

import pytest

from fire_suppression.diagnostics.intrusion_detection import (
    IDSAlert,
    IntrusionDetectionSystem,
    Severity,
)


class TestIDSAlert:
    def test_alert_to_dict(self) -> None:
        alert = IDSAlert(
            alert_id="abc123",
            timestamp=time.time(),
            severity=Severity.HIGH,
            category="usb",
            message_en="USB inserted",
            message_sw="USB kimeingizwa",
            details={"vid": "1234"},
        )
        d = alert.to_dict()
        assert d["severity"] == "high"
        assert d["message_en"] == "USB inserted"
        assert d["details"]["vid"] == "1234"


class TestIntrusionDetectionSystem:
    def test_init_mock(self, tmp_path: Path) -> None:
        ids = IntrusionDetectionSystem(db_path=str(tmp_path / "ids.db"), mock=True)
        assert ids.mock is True
        assert ids._last_usb == set()
        assert ids._fs_baseline is None

    def test_init_creates_db_schema(self, tmp_path: Path) -> None:
        db = tmp_path / "ids.db"
        ids = IntrusionDetectionSystem(db_path=str(db), mock=False)
        assert db.exists()
        alert = IDSAlert(
            alert_id="test-001",
            timestamp=time.time(),
            severity=Severity.LOW,
            category="test",
            message_en="Test alert",
            message_sw="Tahadhari ya mtihani",
            details={},
        )
        ids._log_event(alert)
        events = ids.get_recent_events(limit=1)
        assert len(events) == 1
        assert events[0].alert_id == "test-001"

    def test_hash_alert_deterministic(self) -> None:
        h1 = IntrusionDetectionSystem._hash("usb", "/dev/bus/usb/001/001")
        h2 = IntrusionDetectionSystem._hash("usb", "/dev/bus/usb/001/001")
        assert h1 == h2
        assert len(h1) == 16

    def test_acknowledge_alert(self, tmp_path: Path) -> None:
        ids = IntrusionDetectionSystem(db_path=str(tmp_path / "ids.db"), mock=False)
        alert = IDSAlert(
            alert_id="ack-001",
            timestamp=time.time(),
            severity=Severity.MEDIUM,
            category="process",
            message_en="Unexpected process",
            message_sw="Mchakato usiotarajiwa",
            details={},
        )
        ids._log_event(alert)
        assert ids.acknowledge_alert("ack-001") is True
        events = ids.get_recent_events(category="process")
        assert events[0].acknowledged is True
        assert ids.acknowledge_alert("missing") is False

    def test_get_recent_events_filtering(self, tmp_path: Path) -> None:
        ids = IntrusionDetectionSystem(db_path=str(tmp_path / "ids.db"), mock=False)
        for cat in ("usb", "network", "usb"):
            ids._log_event(IDSAlert(
                alert_id=f"evt-{cat}-{time.time()}",
                timestamp=time.time(),
                severity=Severity.LOW,
                category=cat,
                message_en="msg",
                message_sw="ujumbe",
                details={},
            ))
        assert len(ids.get_recent_events(category="usb")) == 2
        assert len(ids.get_recent_events(category="network")) == 1
        assert len(ids.get_recent_events(severity=Severity.HIGH)) == 0

    def test_sweep_mock_mode(self, tmp_path: Path) -> None:
        ids = IntrusionDetectionSystem(db_path=str(tmp_path / "ids.db"), mock=True)
        alerts = asyncio.run(ids.sweep())
        categories = {a.category for a in alerts}
        assert "usb" in categories
        assert "process" in categories
        assert "network" in categories
        critical = [a for a in alerts if a.severity == Severity.CRITICAL]
        assert any("CPU" in a.message_en for a in critical)

    def test_to_dict(self, tmp_path: Path) -> None:
        ids = IntrusionDetectionSystem(db_path=str(tmp_path / "ids.db"), mock=True)
        d = ids.to_dict()
        assert d["mock"] is True
        assert "usb_devices_tracked" in d

    def test_config_tampering_outside_window(self, tmp_path: Path) -> None:
        ids = IntrusionDetectionSystem(db_path=str(tmp_path / "ids.db"), mock=False, project_root=str(tmp_path))
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("system:\n  name: test\n", encoding="utf-8")
        asyncio.run(ids._check_config_tampering())
        original_localtime = time.localtime
        try:
            class FakeTime:
                tm_hour = 12
                tm_min = 0
                tm_sec = 0
                tm_year = 2026
                tm_mon = 1
                tm_mday = 1
                tm_wday = 0
                tm_yday = 1
                tm_isdst = 0
            time.localtime = lambda _t=None: FakeTime()
            config_file.write_text("system:\n  name: tampered\n", encoding="utf-8")
            alerts = asyncio.run(ids._check_config_tampering())
            assert len(alerts) == 1
            assert alerts[0].severity == Severity.CRITICAL
            assert "OUTSIDE" in alerts[0].message_en
        finally:
            time.localtime = original_localtime

    def test_filesystem_baseline_and_new_file(self, tmp_path: Path) -> None:
        ids = IntrusionDetectionSystem(db_path=str(tmp_path / "ids.db"), mock=False, project_root=str(tmp_path))
        sensitive = tmp_path / "config"
        sensitive.mkdir()
        (sensitive / "config.yaml").write_text("baseline", encoding="utf-8")
        asyncio.run(ids._check_filesystem())
        assert ids._fs_baseline is not None
        (sensitive / "new_secret.yaml").write_text("secret", encoding="utf-8")
        alerts = asyncio.run(ids._check_filesystem())
        assert any(a.category == "filesystem" and "New file" in a.message_en for a in alerts)
