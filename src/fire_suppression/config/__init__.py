import importlib.util
from pathlib import Path

# The original ``config.py`` module (at ``src/fire_suppression/config.py``) is
# shadowed by this ``config/`` package directory.  To keep all existing imports
# ``from fire_suppression.config import Config`` working, we load the legacy
# module directly and re-export its public API.

_config_path = Path(__file__).resolve().parent.parent / "config.py"
_spec = importlib.util.spec_from_file_location("_legacy_config", _config_path)
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)  # type: ignore[attr-defined]

Config = _legacy.Config
ConfigError = _legacy.ConfigError
DEFAULT_CONFIG = _legacy.DEFAULT_CONFIG

# New v0.5.0+ secure vault
from fire_suppression.config.secure_vault import SecureConfigVault  # noqa: E402

__all__ = ["Config", "ConfigError", "DEFAULT_CONFIG", "SecureConfigVault"]
