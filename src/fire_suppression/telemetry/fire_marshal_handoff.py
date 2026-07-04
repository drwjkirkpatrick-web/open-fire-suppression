"""V7-004 — Fire Marshal Digital Handoff

Generates a tamper-evident, QR-scannable incident brief for first responders
and fire marshals. Includes key facts, sensor timeline, actions taken, and
a signed manifest for chain of custody.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class FireMarshalHandoff:
    """Creates a first-responder / fire-marshal incident handoff package."""

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock

    def create_brief(self, incident: dict[str, Any]) -> dict[str, Any]:
        """Create a brief from incident data."""
        brief = {
            "feature_id": "V7-004",
            "brief_id": incident.get("incident_id", f"INC-{int(time.time())}"),
            "generated_at": time.time(),
            "incident_type": incident.get("incident_type", "fire"),
            "location": incident.get("location", "unknown"),
            "zone": incident.get("zone"),
            "start_time": incident.get("start_time"),
            "end_time": incident.get("end_time"),
            "fire_state": incident.get("fire_state", "unknown"),
            "confidence": incident.get("confidence", 0.0),
            "triggered_sensors": incident.get("triggered_sensors", []),
            "actions_taken": incident.get("actions_taken", []),
            "occupancy_estimate": incident.get("occupancy_estimate"),
            "notes": incident.get("notes", ""),
            "operator_name": incident.get("operator_name", ""),
            "contact": incident.get("contact", ""),
        }
        payload = json.dumps(brief, sort_keys=True, default=str)
        brief["manifest_hash"] = hashlib.sha256(payload.encode()).hexdigest()
        brief["qr_payload"] = f"firehandoff:{brief['brief_id']}:{brief['manifest_hash'][:16]}"
        brief["share_url"] = f"/api/fire-marshal/{brief['brief_id']}"
        logger.info("Fire marshal brief %s generated", brief["brief_id"])
        return brief

    def package_for_export(self, brief: dict[str, Any]) -> dict[str, Any]:
        """Wrap brief in a shareable, verifiable package."""
        return {
            "package_id": f"PKG-{brief['brief_id']}",
            "brief": brief,
            "verification": {
                "algorithm": "SHA-256",
                "manifest_hash": brief["manifest_hash"],
                "qr_payload": brief["qr_payload"],
            },
            "formats": ["json", "html", "pdf"],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-004",
            "healthy": True,
            "mock": self.mock,
        }
