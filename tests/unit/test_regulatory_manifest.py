"""Tests for V7-010 Regulatory Firmware Manifest."""
import pytest

from fire_suppression.config import Config
from fire_suppression.diagnostics.regulatory_manifest import RegulatoryFirmwareManifest


@pytest.fixture
def manifest(monkeypatch):
    Config._instance = None
    return RegulatoryFirmwareManifest(Config())


def test_build_manifest(manifest):
    m = manifest.build_manifest()
    assert m["feature_id"] == "V7-010"
    assert m["version"] == "0.7.0"
    assert 0 <= m["coverage"] <= 1
    assert m["manifest_hash"]


def test_manifest_entries_verified(manifest):
    m = manifest.build_manifest()
    for entry in m["entries"]:
        assert "rule_id" in entry
        assert "feature" in entry
        assert "paths" in entry
        assert "file_hashes" in entry
        assert "verified" in entry


def test_delta_detects_changes(manifest):
    old = manifest.build_manifest()
    delta = manifest.delta(old)
    assert "current_hash" in delta
    assert delta["changes"] == []


def test_to_dict_before_build(manifest):
    assert manifest.to_dict()["feature_id"] == "V7-010"
    assert manifest.to_dict()["coverage"] is None


def test_to_dict_after_build(manifest):
    manifest.build_manifest()
    d = manifest.to_dict()
    assert d["coverage"] is not None
    assert d["manifest_hash"] is not None
