"""Tests for tamper-evident audit log.

# IMP-010 — Comprehensive Audit Log & Compliance Reporting
"""
from pathlib import Path

import pytest

from fire_suppression.telemetry.audit import AuditEntry, AuditLogger


class TestAuditLogger:
    """# IMP-010 — Comprehensive Audit Log & Compliance Reporting"""

    def test_log_returns_hash(self, tmp_path) -> None:
        audit = AuditLogger(tmp_path / "audit.db")
        h = audit.log("test_event", actor="test", details={"foo": "bar"})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_verify_chain_with_one_entry(self, tmp_path) -> None:
        audit = AuditLogger(tmp_path / "audit.db")
        audit.log("event1")
        assert audit.verify_chain() is True

    def test_verify_chain_with_multiple_entries(self, tmp_path) -> None:
        audit = AuditLogger(tmp_path / "audit.db")
        audit.log("event1")
        audit.log("event2")
        audit.log("event3")
        assert audit.verify_chain() is True

    def test_get_entries_by_type(self, tmp_path) -> None:
        audit = AuditLogger(tmp_path / "audit.db")
        audit.log("fire_alert", details={"zone": "kitchen"})
        audit.log("system_start")
        audit.log("fire_alert", details={"zone": "garage"})
        entries = audit.get_entries(event_type="fire_alert")
        assert len(entries) == 2
        assert entries[0].event_type == "fire_alert"

    def test_entry_structure(self, tmp_path) -> None:
        audit = AuditLogger(tmp_path / "audit.db")
        h = audit.log("test", actor="admin", details={"x": 1})
        entries = audit.get_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, AuditEntry)
        assert entry.event_type == "test"
        assert entry.actor == "admin"
        assert entry.details == {"x": 1}
        assert entry.entry_hash == h

    def test_html_report_generation(self, tmp_path) -> None:
        audit = AuditLogger(tmp_path / "audit.db")
        audit.log("event1")
        audit.log("event2")
        report_path = audit.generate_html_report(tmp_path / "report.html")
        assert report_path.exists()
        content = report_path.read_text()
        assert "Fire Suppression Audit Report" in content
        assert "event1" in content
        assert "event2" in content

    def test_tamper_detection(self, tmp_path) -> None:
        audit = AuditLogger(tmp_path / "audit.db")
        audit.log("safe_event")
        # Tamper with the database directly
        audit._conn.execute("UPDATE audit_entries SET event_type = 'tampered' WHERE id = 1")
        audit._conn.commit()
        assert audit.verify_chain() is False
