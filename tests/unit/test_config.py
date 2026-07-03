"""Tests for configuration module.

# C001 — YAML Configuration Loading
# C002 — Configuration Validation
"""
import os
from pathlib import Path

import pytest

from fire_suppression.config import Config, ConfigError, DEFAULT_CONFIG


class TestConfigLoading:
    """# C001 — YAML Configuration Loading"""

    def setup_method(self) -> None:
        # Reset singleton so each test gets a fresh Config
        Config._instance = None

    def teardown_method(self) -> None:
        Config._instance = None
        for key in list(os.environ.keys()):
            if key.startswith("FIRE_"):
                del os.environ[key]

    def test_default_config(self) -> None:
        """Config loads with sensible defaults when no file exists."""
        cfg = Config()
        assert cfg.get("system", "name") == "open-fire-suppression"
        assert cfg.get("sensors", "i2c_bus") == 1
        assert cfg.get("detection", "fusion_min_sensors") == 2
        assert cfg.get("actuation", "relay_count") == 4

    def test_config_from_file(self, tmp_path: Path) -> None:
        """Config loads and merges values from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
system:
  mock_hardware: true
sensors:
  i2c_bus: 3
detection:
  fusion_min_sensors: 3
""")
        os.environ["FIRE_CONFIG"] = str(config_file)
        cfg = Config()
        assert cfg.get("system", "mock_hardware") is True
        assert cfg.get("sensors", "i2c_bus") == 3
        assert cfg.get("detection", "fusion_min_sensors") == 3
        # Defaults still present for unspecified keys
        assert cfg.get("actuation", "relay_count") == 4
        del os.environ["FIRE_CONFIG"]

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variables override config values."""
        monkeypatch.setenv("FIRE_SENSORS__I2C_BUS", "5")
        monkeypatch.setenv("FIRE_ACTUATION__RELAY_COUNT", "2")
        cfg = Config()
        assert cfg.get("sensors", "i2c_bus") == 5
        assert cfg.get("actuation", "relay_count") == 2
        monkeypatch.delenv("FIRE_SENSORS__I2C_BUS")
        monkeypatch.delenv("FIRE_ACTUATION__RELAY_COUNT")

    def test_env_boolean_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment booleans are coerced correctly."""
        monkeypatch.setenv("FIRE_SYSTEM__MOCK_HARDWARE", "true")
        cfg = Config()
        assert cfg.get("system", "mock_hardware") is True
        monkeypatch.delenv("FIRE_SYSTEM__MOCK_HARDWARE")

    def test_section_accessor(self) -> None:
        """section() returns a shallow copy of a config section."""
        cfg = Config()
        sensors = cfg.section("sensors")
        assert sensors["i2c_bus"] == 1
        # Modifying returned dict should not affect config
        sensors["i2c_bus"] = 99
        assert cfg.get("sensors", "i2c_bus") == 1


class TestConfigValidation:
    """# C002 — Configuration Validation"""

    def setup_method(self) -> None:
        Config._instance = None

    def teardown_method(self) -> None:
        Config._instance = None
        for key in list(os.environ.keys()):
            if key.startswith("FIRE_"):
                del os.environ[key]

    def test_invalid_i2c_bus(self, tmp_path: Path) -> None:
        """Invalid I2C bus raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sensors:\n  i2c_bus: 99\n")
        os.environ["FIRE_CONFIG"] = str(config_file)
        with pytest.raises(ConfigError, match="i2c_bus"):
            Config()
        del os.environ["FIRE_CONFIG"]

    def test_empty_relay_pins(self, tmp_path: Path) -> None:
        """Empty relay pins raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("actuation:\n  relay_pins: []\n")
        os.environ["FIRE_CONFIG"] = str(config_file)
        with pytest.raises(ConfigError, match="relay_pins"):
            Config()
        del os.environ["FIRE_CONFIG"]

    def test_battery_threshold_order(self, tmp_path: Path) -> None:
        """Low battery must be greater than critical battery."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
power:
  low_battery_percent: 5
  critical_battery_percent: 20
""")
        os.environ["FIRE_CONFIG"] = str(config_file)
        with pytest.raises(ConfigError, match="low_battery_percent"):
            Config()
        del os.environ["FIRE_CONFIG"]

    def test_negative_fusion_window(self, tmp_path: Path) -> None:
        """Negative fusion window raises ConfigError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("detection:\n  fusion_time_window_seconds: -1\n")
        os.environ["FIRE_CONFIG"] = str(config_file)
        with pytest.raises(ConfigError, match="fusion_time_window_seconds"):
            Config()
        del os.environ["FIRE_CONFIG"]
