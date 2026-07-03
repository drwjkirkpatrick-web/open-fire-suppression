"""Remote configuration and OTA update endpoints.

# IMP-006 — Remote Configuration & OTA Updates

Provides API endpoints for live configuration changes and git-based
over-the-air updates.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fire_suppression.config import Config, ConfigError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigUpdate(BaseModel):
    """Request body for config updates."""
    section: str
    key: str
    value: Any


class ConfigResponse(BaseModel):
    """Response for config operations."""
    success: bool
    message: str
    config: dict | None = None


@router.get("/")
async def get_config() -> dict:
    """Get current system configuration."""
    cfg = Config()
    return cfg.raw


@router.post("/update")
async def update_config(update: ConfigUpdate) -> ConfigResponse:
    """Update a single configuration value at runtime.

    The change is applied in-memory and persisted to the config file.
    Use with caution — invalid values may require restart to fix.
    """
    cfg = Config()
    try:
        # Navigate to the section and update
        section = cfg._data.get(update.section)
        if section is None:
            raise HTTPException(status_code=404, detail=f"Section '{update.section}' not found")

        # Handle nested keys (dot notation: "detection.confidence_smoke_weight")
        keys = update.key.split(".")
        target = section
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                raise HTTPException(status_code=404, detail=f"Key '{update.key}' not found")
            target = target[k]

        # Coerce value type
        current = target.get(keys[-1])
        if isinstance(current, bool):
            new_value = update.value in (True, "true", "True", "1", "yes", "on")
        elif isinstance(current, int):
            new_value = int(update.value)
        elif isinstance(current, float):
            new_value = float(update.value)
        else:
            new_value = update.value

        target[keys[-1]] = new_value

        # Validate
        cfg._validate()

        # Persist to file if possible
        if cfg._path:
            try:
                import yaml
                with open(cfg._path, "w", encoding="utf-8") as fh:
                    yaml.dump(cfg._data, fh, default_flow_style=False, sort_keys=False)
            except Exception as exc:
                logger.warning("Failed to persist config: %s", exc)

        return ConfigResponse(success=True, message="Config updated", config=cfg.raw)

    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Config update error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/reload")
async def reload_config() -> ConfigResponse:
    """Trigger a hot reload of configuration from disk."""
    cfg = Config()
    try:
        cfg._load()
        cfg._apply_env_overrides()
        cfg._validate()
        return ConfigResponse(success=True, message="Config reloaded from disk", config=cfg.raw)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ota-update")
async def ota_update(branch: str = "main") -> ConfigResponse:
    """Trigger a git-based over-the-air update.

    Pulls latest code from origin and restarts the service via systemd.
    Requires the application to be running from a git repository.
    """
    project_dir = os.environ.get("PROJECT_DIR", "/opt/open-fire-suppression")

    try:
        # Fetch latest
        subprocess.run(
            ["git", "-C", project_dir, "fetch", "origin"],
            check=True, capture_output=True, text=True,
        )
        # Pull
        result = subprocess.run(
            ["git", "-C", project_dir, "pull", "origin", branch],
            check=True, capture_output=True, text=True,
        )
        output = result.stdout.strip()
        logger.info("OTA update output: %s", output)

        # Restart service
        subprocess.run(
            ["sudo", "systemctl", "restart", "open-fire-suppression"],
            check=False, capture_output=True,
        )

        return ConfigResponse(
            success=True,
            message=f"OTA update completed: {output}",
        )
    except subprocess.CalledProcessError as exc:
        logger.error("OTA update failed: %s", exc.stderr)
        raise HTTPException(status_code=500, detail=f"Git operation failed: {exc.stderr}")
    except Exception as exc:
        logger.error("OTA update error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
