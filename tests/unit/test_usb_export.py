"""Tests for USB data export for legal/insurance inspections.

# USB-EXPORT — Tamper-evident inspection package
"""
import time

import pytest

from fire_suppression.telemetry.usb_export import ExportPackage, USBExporter


class TestUSBExporter:
    def test_init(self) -> None:
        exporter = USBExporter(mock=True)
        assert exporter.mock is True
        assert exporter.usb_mount.name == "usb0"

    def test_validate_usb_mock(self) -> None:
        exporter = USBExporter(mock=True)
        result = exporter.validate_usb()
        assert result["ready"] is True
        assert result["filesystem"] == "FAT32 (mock)"
        assert result["free_gb"] == 8.0

    def test_hash_file(self, tmp_path) -> None:
        exporter = USBExporter(mock=True)
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        hash_val = exporter._hash_file(test_file)
        assert len(hash_val) == 64  # SHA-256 is 64 hex chars
        assert hash_val == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_hash_directory(self, tmp_path) -> None:
        exporter = USBExporter(mock=True)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        hashes = exporter._hash_directory(tmp_path)
        assert len(hashes) == 2
        assert "a.txt" in hashes
        assert "b.txt" in hashes

    def test_sign_manifest(self) -> None:
        exporter = USBExporter(mock=True)
        manifest = {"key1": "value1", "key2": "value2"}
        sig = exporter._sign_manifest(manifest)
        assert len(sig) == 64  # SHA-256 hex
        # Same manifest should produce same signature
        sig2 = exporter._sign_manifest(manifest)
        assert sig == sig2

    @pytest.mark.asyncio
    async def test_export_inspection_package_mock(self, tmp_path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        exporter = USBExporter(mock=True, usb_mount=str(tmp_path), data_dir=str(data_dir))

        # Create mock databases
        import sqlite3
        conn = sqlite3.connect(str(data_dir / "events.db"))
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL, event_type TEXT)")
        conn.execute("INSERT INTO events (timestamp, event_type) VALUES (?, ?)", (time.time(), "fire_alert"))
        conn.execute("CREATE TABLE sensor_history (id INTEGER PRIMARY KEY, timestamp REAL, sensor_name TEXT, value REAL)")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(str(data_dir / "audit.db"))
        conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, timestamp REAL, event_type TEXT, actor TEXT, details TEXT)")
        conn.execute("INSERT INTO audit_log (timestamp, event_type, actor, details) VALUES (?, ?, ?, ?)",
                     (time.time(), "fire_alert", "detection_engine", '{"zone": "kitchen"}'))
        conn.commit()
        conn.close()

        pkg = await exporter.export_inspection_package(
            include_logs=True,
            include_audit=True,
            include_config=True,
            include_sensor_data=True,
            include_incident_reports=True,
        )
        assert pkg.package_id.startswith("FIRE-PKG-")
        assert pkg.file_count > 0
        assert pkg.total_size_bytes > 0
        assert pkg.encrypted is False
        assert "json" in pkg.formats or "csv" in pkg.formats
        assert pkg.manifest_path is not None

    @pytest.mark.asyncio
    async def test_verify_package_integrity(self, tmp_path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        exporter = USBExporter(mock=True, usb_mount=str(tmp_path), data_dir=str(data_dir))

        import sqlite3
        conn = sqlite3.connect(str(data_dir / "events.db"))
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL, event_type TEXT)")
        conn.execute("INSERT INTO events VALUES (1, ?, 'test')", (time.time(),))
        conn.execute("CREATE TABLE sensor_history (id INTEGER PRIMARY KEY, timestamp REAL, sensor_name TEXT, value REAL)")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(str(data_dir / "audit.db"))
        conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, timestamp REAL, event_type TEXT, actor TEXT, details TEXT)")
        conn.commit()
        conn.close()

        pkg = await exporter.export_inspection_package()
        result = exporter.verify_package_integrity(pkg.package_id)
        assert result["valid"] is True
        assert result["verified"] > 0

    @pytest.mark.asyncio
    async def test_list_exported_packages(self, tmp_path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        exporter = USBExporter(mock=True, usb_mount=str(tmp_path), data_dir=str(data_dir))

        import sqlite3
        conn = sqlite3.connect(str(data_dir / "events.db"))
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL, event_type TEXT)")
        conn.execute("INSERT INTO events VALUES (1, ?, 'test')", (time.time(),))
        conn.execute("CREATE TABLE sensor_history (id INTEGER PRIMARY KEY, timestamp REAL, sensor_name TEXT, value REAL)")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(str(data_dir / "audit.db"))
        conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, timestamp REAL, event_type TEXT, actor TEXT, details TEXT)")
        conn.commit()
        conn.close()

        pkg = await exporter.export_inspection_package()
        packages = exporter.list_exported_packages()
        assert len(packages) >= 1
        assert packages[0]["package_id"] == pkg.package_id

    def test_empty_list(self, tmp_path) -> None:
        exporter = USBExporter(mock=True, usb_mount=str(tmp_path))
        packages = exporter.list_exported_packages()
        assert packages == []

    def test_generate_audit_html(self) -> None:
        exporter = USBExporter(mock=True)
        entries = [
            {"timestamp": time.time(), "event_type": "fire_alert", "actor": "detection", "details": '{"zone": "kitchen"}'},
            {"timestamp": time.time(), "event_type": "suppression_activated", "actor": "actuation", "details": '{"zone": "kitchen", "relay": 1}'},
        ]
        html = exporter._generate_audit_html(entries, watermark=True)
        assert "<!DOCTYPE html>" in html
        assert "LEGAL HOLD" in html
        assert "fire_alert" in html
        assert "suppression_activated" in html
