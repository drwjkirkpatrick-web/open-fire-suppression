"""Tests for BOT-007 — Atomic Config Reload."""
from pathlib import Path

import pytest

from fire_suppression.web.config_atomic_reload import ConfigAtomicReload


class TestConfigAtomicReload:
    def test_init_mock(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("system:\n  name: test\n", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg_file), mock=True)
        health = reloader.health_check()
        assert health["mock"] is True
        assert health["reload_count"] == 0

    def test_safe_reload_valid(self, tmp_path: Path) -> None:
        cfg = tmp_path / "valid.yaml"
        cfg.write_text("""
system:
  name: open-fire-suppression
  mock_hardware: false
  log_level: INFO
sensors:
  i2c_bus: 1
detection:
  smoke_threshold: 100
  temp_threshold: 60
  fusion_min_sensors: 2
actuation:
  relay_count: 4
alerts:
  channels: [buzzer]
telemetry:
  enabled: true
""", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg), mock=True)
        result = reloader.safe_reload()
        assert isinstance(result, dict)
        assert "system" in result

    def test_safe_reload_invalid_yaml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("system: [", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg), mock=True)
        result = reloader.safe_reload()
        assert isinstance(result, dict)
        assert reloader.health_check()["last_error"] != ""

    def test_safe_reload_missing_keys(self, tmp_path: Path) -> None:
        cfg = tmp_path / "incomplete.yaml"
        cfg.write_text("system:\n  name: test\n", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg), mock=True)
        result = reloader.safe_reload()
        assert isinstance(result, dict)
        assert reloader.health_check()["last_error"] != ""

    def test_health_after_failures(self, tmp_path: Path) -> None:
        cfg = tmp_path / "bad.yaml"
        cfg.write_text("system: [", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg), mock=True)
        for _ in range(5):
            reloader.safe_reload()
        health = reloader.health_check()
        assert health["last_error"] != ""

    def test_register_sigusr1(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("system:\n  name: test\n", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg), mock=True)
        reloader.register_sigusr1_handler()
        # sigusr1_installed is in to_dict, not health_check
        assert reloader.to_dict().get("sigusr1_registered") is True

    def test_feature_overview(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("system:\n  name: test\n", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg), mock=True)
        ov = reloader.get_feature_overview()
        assert ov["feature_id"] == "BOT-007"
        assert "atomic_file_write" in ov["supports"]

    def test_to_dict(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.yaml"
        cfg.write_text("system:\n  name: test\n", encoding="utf-8")
        reloader = ConfigAtomicReload(str(cfg), mock=True)
        d = reloader.to_dict()
        assert "healthy" in d
        assert "overview" in d
