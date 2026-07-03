"""Configuration loader with validation for open-fire-suppression.

Supports YAML configuration files and environment variable overrides.
Handles SIGUSR1 for runtime reload.

# S001 — I2C Bus Discovery
# C001 — YAML Configuration Loading
# C002 — Configuration Validation
# C003 — Runtime Config Reload
"""
from __future__ import annotations

import copy
import logging
import os
import signal
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    # ── System ──
    "system": {
        "name": "open-fire-suppression",
        "mock_hardware": False,
        "log_level": "INFO",
        "data_dir": "/var/lib/fire-suppression",
    },
    # ── Sensors ──
    "sensors": {
        "i2c_bus": 1,
        "scan_on_startup": True,
        "health_window_seconds": 10,
        "health_min_success_rate": 0.5,
        "poll_interval_seconds": 1.0,
        "ads1115": {
            "enabled": True,
            "address": 0x48,
            "gain": 1,  # ±4.096V
            "channels": [0, 1, 2, 3],
        },
        "mq2": {
            "enabled": True,
            "adc_channel": 0,
            "r0": 10000.0,  # Calibration resistance in clean air (ohms)
            "warmup_seconds": 60,
        },
        "sht40": {
            "enabled": True,
            "address": 0x44,
        },
        "mlx90614": {
            "enabled": True,
            "address": 0x5A,
        },
        "bme680": {
            "enabled": True,
            "address": 0x77,
        },
        "ens160": {
            "enabled": True,
            "address": 0x53,
            "warmup_seconds": 30,
        },
        "amg8833": {
            "enabled": True,
            "address": 0x69,
        },
        "mlx90640": {
            "enabled": False,  # Premium; disabled by default
            "address": 0x33,
        },
        "ds18b20": {
            "enabled": True,
            "base_path": "/sys/bus/w1/devices",
        },
        "picamera": {
            "enabled": True,
            "resolution": [1920, 1080],
            "fps": 10,
        },
    },
    # ── Detection ──
    "detection": {
        "enabled": True,
        "single_sensor_threshold": {
            "mq2_smoke_ppm": 300,        # S003
            "mlx90614_temp_c": 80.0,     # S005
            "sht40_temp_c": 60.0,        # S004
            "bme680_gas_resistance": 5000, # S006 (lower = more VOCs)
            "ens160_tvoc_ppb": 500,      # S007
            "ds18b20_temp_c": 70.0,      # S011
        },
        "fusion_min_sensors": 2,         # D002
        "fusion_time_window_seconds": 5.0,
        "confidence_smoke_weight": 0.3,
        "confidence_temp_weight": 0.3,
        "confidence_gas_weight": 0.2,
        "confidence_video_weight": 0.2,
        "thermal_hotspot_min_c": 60.0,   # D004
        "thermal_hotspot_min_pixels": 4,   # 2×2 region
        "flicker_min_hz": 1.0,           # D005
        "flicker_max_hz": 12.0,
    },
    # ── Actuation ──
    "actuation": {
        "enabled": True,
        "relay_count": 4,
        "relay_pins": [5, 6, 13, 19],   # GPIO pin numbers
        "relay_active_high": False,      # Active-low relay modules common
        "pre_activation_seconds": 10,    # A002
        "suppression_duration_seconds": 60,  # A003
        "flow_sensor_pin": 26,           # A004
        "manual_button_pin": 21,         # A005
        "buzzer_pin": 20,                # P002
    },
    # ── Safety ──
    "safety": {
        "arming_required": True,           # F001
        "disarm_inhibits_all": True,     # F002
        "maintenance_pin": 16,           # F003
        "tamper_pin": 12,                # F004
        "watchdog_timeout_seconds": 30,  # F005
        "emergency_stop_pin": 7,         # F006
    },
    # ── Power ──
    "power": {
        "ups_type": "pisugar",           # "pisugar", "pijuice", "diy", "none"
        "battery_adc_channel": 3,        # P001
        "voltage_divider_ratio": 2.0,    # P001 (resistor divider)
        "low_battery_percent": 20,       # P002
        "critical_battery_percent": 5,   # P003
        "ac_detect_pin": 25,             # P004
        "poll_interval_seconds": 5.0,
    },
    # ── Telemetry ──
    "telemetry": {
        "enabled": True,
        "db_path": "/var/lib/fire-suppression/events.db",
        "max_db_size_mb": 100,           # T006
        "db_archives_keep": 10,
        "api_host": "0.0.0.0",
        "api_port": 8080,
        "websocket_interval_seconds": 1.0,  # T003
        "alert_channels": ["buzzer"],    # T005: "buzzer", "sms", "webhook"
    },
}


class ConfigError(Exception):
    """Raised when configuration is invalid or missing required keys."""
    pass


class Config:
    """Thread-safe configuration container with validation and reload support.

    Loads from YAML file and allows environment variable overrides
    (``FIRE_MQ2_ENABLED=false`` overrides ``sensors.mq2.enabled``).
    """

    _instance: Config | None = None

    def __new__(cls, *args: Any, **kwargs: Any) -> Config:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, path: str | None = None) -> None:
        if self._initialized:
            return
        self._path = path or self._find_config_file()
        self._data: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self._load()
        self._apply_env_overrides()
        self._validate()
        self._initialized = True

    # ── Discovery ──

    @staticmethod
    def _find_config_file() -> str | None:
        """Look for config.yaml in standard locations."""
        candidates = [
            os.environ.get("FIRE_CONFIG"),
            "./config.yaml",
            "./config/config.yaml",
            "/etc/fire-suppression/config.yaml",
        ]
        for p in candidates:
            if p and Path(p).exists():
                return str(Path(p).resolve())
        return None

    # ── Loading ──

    def _load(self) -> None:
        """Load YAML from disk if a file was found."""
        if self._path and Path(self._path).exists():
            if yaml is None:
                raise ConfigError("PyYAML is required but not installed.")
            with open(self._path, "r", encoding="utf-8") as fh:
                user = yaml.safe_load(fh) or {}
            self._deep_merge(self._data, user)
            logger.info("Loaded config from %s", self._path)
        else:
            logger.warning("No config file found; using defaults.")

    @staticmethod
    def _deep_merge(base: dict[Any, Any], override: dict[Any, Any]) -> None:
        """Recursively merge *override* into *base* (in-place)."""
        for key, val in override.items():
            if isinstance(val, dict) and key in base and isinstance(base[key], dict):
                Config._deep_merge(base[key], val)
            else:
                base[key] = val

    # ── Environment overrides ──

    def _apply_env_overrides(self) -> None:
        """Support ``FIRE_<SECTION>_<KEY>=value`` overrides."""
        prefix = "FIRE_"
        for key, raw in os.environ.items():
            if not key.startswith(prefix):
                continue
            parts = key[len(prefix):].lower().split("__")
            if len(parts) < 2:
                continue
            section = parts[0]
            subkeys = parts[1:]
            if section not in self._data:
                logger.warning("Unknown config section from env: %s", section)
                continue
            target = self._data[section]
            for sub in subkeys[:-1]:
                if not isinstance(target, dict) or sub not in target:
                    logger.warning("Unknown config key from env: %s", key)
                    break
                target = target[sub]
            else:
                if isinstance(target, dict):
                    target[subkeys[-1]] = _coerce(raw)
                    logger.debug("Env override: %s = %r", key, target[subkeys[-1]])

    # ── Validation ──

    def _validate(self) -> None:
        """Ensure required keys and sane values."""
        errors: list[str] = []

        # System
        if not isinstance(self._data.get("system", {}).get("mock_hardware"), bool):
            errors.append("system.mock_hardware must be a boolean")

        # Sensors
        sensors = self._data.get("sensors", {})
        if sensors.get("i2c_bus") not in (0, 1, 3, 4, 5, 6):
            errors.append("sensors.i2c_bus must be a valid Raspberry Pi I2C bus (0-6)")

        # Actuation
        act = self._data.get("actuation", {})
        pins = act.get("relay_pins", [])
        if not isinstance(pins, list) or len(pins) == 0:
            errors.append("actuation.relay_pins must be a non-empty list")

        # Detection
        det = self._data.get("detection", {})
        if det.get("fusion_min_sensors", 2) < 1:
            errors.append("detection.fusion_min_sensors must be >= 1")
        if det.get("fusion_time_window_seconds", 5) <= 0:
            errors.append("detection.fusion_time_window_seconds must be > 0")

        # Power
        power = self._data.get("power", {})
        if power.get("low_battery_percent", 20) <= power.get("critical_battery_percent", 5):
            errors.append("power.low_battery_percent must be > critical_battery_percent")

        if errors:
            raise ConfigError("; ".join(errors))

    # ── Reload ──

    def enable_hot_reload(self) -> None:
        """Register SIGUSR1 handler to reload config from disk at runtime."""
        def _handler(signum: int, frame: Any) -> None:  # noqa: ARG001
            logger.info("SIGUSR1 received — reloading configuration")
            try:
                self._load()
                self._apply_env_overrides()
                self._validate()
                logger.info("Configuration reloaded successfully")
            except ConfigError as exc:
                logger.error("Config reload failed: %s", exc)

        signal.signal(signal.SIGUSR1, _handler)

    # ── Accessors ──

    def get(self, *keys: str, default: Any = None) -> Any:
        """Dot-path getter: ``config.get("sensors", "mq2", "enabled")``."""
        target: Any = self._data
        for k in keys:
            if not isinstance(target, dict):
                return default
            target = target.get(k, default)
            if target is default:
                return default
        return target

    def section(self, name: str) -> dict[str, Any]:
        """Return a top-level section as a dict (shallow copy)."""
        return dict(self._data.get(name, {}))

    @property
    def raw(self) -> dict[str, Any]:
        """Return a deep copy of the full configuration (for JSON serialization)."""
        return copy.deepcopy(self._data)

    @property
    def mock_hardware(self) -> bool:
        return bool(self._data.get("system", {}).get("mock_hardware", False))

    @property
    def data_dir(self) -> Path:
        return Path(self._data.get("system", {}).get("data_dir", "/var/lib/fire-suppression"))


def _coerce(value: str) -> bool | int | float | str:
    """Convert an environment string to its best Python type."""
    lowered = value.lower()
    if lowered in ("true", "yes", "1"):
        return True
    if lowered in ("false", "no", "0"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
