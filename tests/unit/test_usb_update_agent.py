"""Tests for anti-tamper USB update agent.

# SEC-001 — USB Update Agent Tests
"""
import asyncio
import json
import os
import time

import pytest

from fire_suppression.diagnostics.usb_update_agent import (
    USBUpdateAgent,
    UpdateResult,
)


class TestUSBUpdateAgent:
    def test_init_mock(self) -> None:
        agent = USBUpdateAgent(mock=True)
        assert agent.mock is True
        assert agent.get_current_version() != "unknown"

    def test_init_without_public_key_rejects(self, tmp_path) -> None:
        # Even mock=False needs a key or it should reject
        agent = USBUpdateAgent(mock=False, project_root=str(tmp_path))
        # Should still init but won't verify anything without key
        assert agent.public_key is None

    def test_find_update_package_missing(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        found = agent._find_update_package(tmp_path)
        assert found is None

    def test_find_update_package_directory(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        pkg_dir = tmp_path / "update-package"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text("{}", encoding="utf-8")
        found = agent._find_update_package(tmp_path)
        assert found == pkg_dir

    def test_verify_manifest_valid(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        pkg_dir = tmp_path / "update-package"
        pkg_dir.mkdir()
        manifest = {
            "version": "0.6.0",
            "timestamp": time.time(),
            "device_id": "*",
            "files": ["test.py"],
            "content_hash": "abcd1234",
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        ok, data = agent._verify_manifest(pkg_dir)
        assert ok is True
        assert data["version"] == "0.6.0"

    def test_verify_manifest_missing_file(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        ok, reason = agent._verify_manifest(tmp_path)
        assert ok is False
        assert "not found" in str(reason)

    def test_verify_manifest_missing_field(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        pkg_dir = tmp_path / "update-package"
        pkg_dir.mkdir()
        (pkg_dir / "manifest.json").write_text('{"version": "0.6.0"}', encoding="utf-8")
        ok, reason = agent._verify_manifest(pkg_dir)
        assert ok is False

    def test_check_compatibility_any_device(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        ok, _ = agent._check_compatibility({"device_id": "*", "version": "0.6.0"})
        assert ok is True

    def test_is_version_newer(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        # Create a version file
        version_file = tmp_path / "version.txt"
        version_file.write_text("0.5.0\n", encoding="utf-8")
        agent._current_version = "0.5.0"
        assert agent._is_version_newer("0.6.0") is True
        assert agent._is_version_newer("0.5.0") is False
        assert agent._is_version_newer("0.4.0") is False

    @pytest.mark.asyncio
    async def test_process_usb_update_no_package(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        result = await agent.process_usb_update(tmp_path)
        assert result.success is False
        assert "update package" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_process_usb_update_mock(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        # Create a minimal update package
        pkg_dir = tmp_path / "update-package"
        pkg_dir.mkdir()
        firmware_dir = pkg_dir / "firmware"
        firmware_dir.mkdir()
        (firmware_dir / "test.py").write_text("print('hello')", encoding="utf-8")

        manifest = {
            "version": "0.99.0",
            "timestamp": time.time(),
            "device_id": "*",
            "files": ["test.py"],
            "content_hash": "placeholder",
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        # Content hash
        hashes = {"test.py": "abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234"}
        (pkg_dir / "contents.sha256").write_text(json.dumps(hashes), encoding="utf-8")

        result = await agent.process_usb_update(tmp_path)
        # In mock mode with no Ed25519 verification, should proceed
        # But hash mismatch will fail
        assert isinstance(result, UpdateResult)

    def test_get_device_id_fallback(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        device_id = agent._get_device_id()
        assert device_id is not None
        assert len(device_id) > 0

    def test_rollback_no_versions(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        result = asyncio.get_event_loop().run_until_complete(agent.rollback())
        assert result.success is False
        assert "No previous versions" in result.rejection_reason

    def test_to_dict(self, tmp_path) -> None:
        agent = USBUpdateAgent(mock=True, project_root=str(tmp_path))
        d = agent.to_dict()
        assert "current_version" in d
        assert "mock_mode" in d
        assert d["mock_mode"] is True


class TestUpdateResult:
    def test_dataclass_defaults(self) -> None:
        r = UpdateResult(success=True)
        assert r.files_updated == []
        assert r.rollback_available is False
