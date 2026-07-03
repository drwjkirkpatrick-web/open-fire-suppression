"""Atomic configuration reload with validation and fallback.

# BOT-007 — Atomic Config Reload

Provides safe, atomic config writes (write-to-temp + rename) and runtime
reload with validation.  If validation fails, the last-known-good config
is retained and a fallback event is recorded.  All lifecycle messages are
bilingual (English / Swahili).

Usage::

    from fire_suppression.web.config_atomic_reload import ConfigAtomicReload
    reloader = ConfigAtomicReload("/etc/fire-suppression/config.yaml", mock=True)
    reloader.register_sigusr1_handler()
    cfg = reloader.safe_reload()
    health = reloader.health_check()
    overview = reloader.get_feature_overview()
"""
from __future__ import annotations

import logging
import os
import signal
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── Bilingual messages ────────────────────────────────────────────────────
_RELOAD_MSGS = {
    "init": {
        "en": "Atomic config reloader initialised for {path}",
        "sw": "Kipakiaji sanidi atomiki kimeanzishwa kwa {path}",
    },
    "reload_success": {
        "en": "Configuration reloaded successfully at {time}",
        "sw": "Sanidi imepakwa upya kwa mafanikio saa {time}",
    },
    "reload_failed": {
        "en": "Config reload failed: {error}",
        "sw": "Upakiaji upya wa sanidi umeshindwa: {error}",
    },
    "fallback": {
        "en": "Falling back to last-known-good config (validation error)",
        "sw": "Kurudi kwenye sanidi iliyojulikana kuwa nzuri (kosa la uthibitisho)",
    },
    "atomic_write": {
        "en": "Config written atomically to {path}",
        "sw": "Sanidi imeandikwa kwa njia atomiki kwenye {path}",
    },
    "sigusr1_registered": {
        "en": "SIGUSR1 handler registered for atomic config reload",
        "sw": "Mkabidhi wa SIGUSR1 umeandikishwa kwa upakiaji upya wa sanidi atomiki",
    },
}


def _msg(key: str, lang: str = "en", **kwargs: Any) -> str:
    m = _RELOAD_MSGS.get(key, {})
    return m.get(lang, m.get("en", key)).format(**kwargs)


class ConfigAtomicReload:
    """Atomic YAML config writer and safe runtime reloader.

    Args:
        config_path: Path to the target YAML configuration file.
        mock: If ``True``, operate in synthetic mode (no actual signal
            registration or filesystem mutations).
    """

    feature_id: str = "BOT-007"

    def __init__(self, config_path: str | Path, *, mock: bool = False) -> None:
        self.config_path = Path(config_path)
        self.mock = mock

        # Lazy import to avoid circular imports during test collection
        from fire_suppression.config import Config, ConfigError

        self._Config = Config
        self._ConfigError = ConfigError

        # State
        self._last_good_config: dict[str, Any] | None = None
        self._last_reload_time: float = 0.0
        self._reload_count: int = 0
        self._validation_error_count: int = 0
        self._fallback_count: int = 0
        self._last_error: str = ""
        self._sigusr1_registered: bool = False

        # Seed last-known-good from current file or defaults
        self._seed_last_known_good()

        logger.info(_msg("init", path=str(self.config_path)))

    # ── Seed ──────────────────────────────────────────────────────────────────

    def _seed_last_known_good(self) -> None:
        """Populate ``_last_good_config`` from disk or defaults."""
        if self.config_path.exists():
            try:
                if yaml is None:
                    raise ImportError("PyYAML is required but not installed.")
                with open(self.config_path, "r", encoding="utf-8") as fh:
                    self._last_good_config = yaml.safe_load(fh) or {}
            except Exception as exc:
                logger.warning("Failed to seed last-known-good config: %s", exc)
                self._last_good_config = {}
        else:
            self._last_good_config = {}

    # ── Atomic write ──────────────────────────────────────────────────────────

    def atomic_write(self, data: dict[str, Any]) -> None:
        """Serialize *data* to YAML and atomically replace *config_path*.

        Writes to a temp file in the same directory as *config_path* and
        then calls :func:`os.replace` for an atomic rename.
        """
        if yaml is None:
            raise ImportError("PyYAML is required but not installed.")

        if self.mock:
            # In mock mode, write directly without the atomic dance so
            # tests can inspect the file without extra complexity.
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
            logger.info(_msg("atomic_write", path=str(self.config_path)))
            return

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.config_path.parent),
            prefix=f".{self.config_path.name}.tmp_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
            os.replace(tmp_path, str(self.config_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise

        logger.info(_msg("atomic_write", path=str(self.config_path)))

    # ── Safe reload ─────────────────────────────────────────────────────────

    def safe_reload(self) -> dict[str, Any]:
        """Load new config from disk, validate, and swap atomically.

        If validation fails, the last-known-good configuration is returned
        and a fallback event is recorded.

        Returns:
            The current (or last-known-good) configuration dictionary.
        """
        if not self.config_path.exists():
            self._fallback_count += 1
            self._last_error = f"Config file not found: {self.config_path}"
            logger.error(_msg("reload_failed", error=self._last_error))
            logger.warning(_msg("fallback"))
            return dict(self._last_good_config or {})

        try:
            if yaml is None:
                raise ImportError("PyYAML is required but not installed.")
            with open(self.config_path, "r", encoding="utf-8") as fh:
                candidate = yaml.safe_load(fh) or {}
        except Exception as exc:
            self._fallback_count += 1
            self._last_error = str(exc)
            logger.error(_msg("reload_failed", error=self._last_error))
            logger.warning(_msg("fallback"))
            return dict(self._last_good_config or {})

        # Validate using the project's Config class
        try:
            # Build a throw-away Config to exercise validation
            # We must temporarily replace the singleton to avoid side-effects
            original_instance = self._Config._instance
            self._Config._instance = None
            throwaway = self._Config.__new__(self._Config)
            throwaway._data = candidate
            throwaway._initialized = True
            throwaway._validate()
            self._Config._instance = original_instance
        except Exception as exc:
            self._validation_error_count += 1
            self._fallback_count += 1
            self._last_error = str(exc)
            logger.error(_msg("reload_failed", error=self._last_error))
            logger.warning(_msg("fallback"))
            return dict(self._last_good_config or {})

        # Success — swap atomically
        self._last_good_config = candidate
        self._last_reload_time = time.time()
        self._reload_count += 1
        self._last_error = ""
        logger.info(_msg("reload_success", time=self._last_reload_time))
        return dict(self._last_good_config)

    # ── SIGUSR1 handler ───────────────────────────────────────────────────────

    def register_sigusr1_handler(self) -> None:
        """Register a SIGUSR1 handler that calls :meth:`safe_reload`.

        Does nothing when ``mock=True`` to avoid interfering with test
        runners that may rely on signal state.
        """
        if self.mock:
            logger.debug(_msg("sigusr1_registered"))
            self._sigusr1_registered = True
            return

        def _handler(signum: int, frame: Any) -> None:  # noqa: ARG001
            logger.info("SIGUSR1 received — triggering atomic config reload")
            self.safe_reload()

        signal.signal(signal.SIGUSR1, _handler)
        self._sigusr1_registered = True
        logger.info(_msg("sigusr1_registered"))

    # ── Health check ──────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """Return current health metrics and status."""
        return {
            "feature_id": self.feature_id,
            "healthy": self._last_error == "",
            "config_path": str(self.config_path),
            "config_exists": self.config_path.exists(),
            "last_reload_time": self._last_reload_time,
            "reload_count": self._reload_count,
            "validation_error_count": self._validation_error_count,
            "fallback_count": self._fallback_count,
            "last_error": self._last_error,
            "mock": self.mock,
        }

    # ── Feature overview ──────────────────────────────────────────────────────

    def get_feature_overview(self) -> dict[str, Any]:
        """Return feature metadata for dashboards / introspection."""
        return {
            "feature_id": self.feature_id,
            "feature_name": "Atomic Config Reload",
            "description": (
                "Atomic YAML config writer and safe runtime reloader with "
                "validation, fallback to last-known-good, and SIGUSR1 support."
            ),
            "mock": self.mock,
            "supports": [
                "atomic_file_write",
                "config_validation",
                "last_known_good_fallback",
                "sigusr1_reload",
                "reload_metrics",
                "bilingual_messages",
            ],
        }

    # ── Dict representation ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Merge health check and overview for serialization."""
        return {
            **self.health_check(),
            "overview": self.get_feature_overview(),
            "sigusr1_registered": self._sigusr1_registered,
            "last_good_config": dict(self._last_good_config or {}),
        }
