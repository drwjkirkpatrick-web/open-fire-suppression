"""V7-010 — Regulatory Firmware Manifest

Maps every implemented feature to the source code paths that satisfy it,
producing an AHJ-ready manifest showing which NFPA / regulatory requirements
are implemented by which modules. Supports export and compliance deltas.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class RegulatoryFirmwareManifest:
    """Generates a feature-to-code regulatory manifest for AHJ audits."""

    _REGULATORY_RULES: list[dict[str, Any]] = [
        {"id": "NFPA72-17.5.3", "feature": "Smoke detection spacing", "paths": ["src/fire_suppression/detection/engine.py", "src/fire_suppression/detection/zones.py"]},
        {"id": "NFPA72-18.4", "feature": "Voice evacuation intelligibility", "paths": ["src/fire_suppression/alerts/directional_voice_evac.py", "src/fire_suppression/alerts/voice_alert.py"]},
        {"id": "NFPA72-21.3", "feature": "Elevator recall", "paths": ["src/fire_suppression/actuation/elevator_recall.py"]},
        {"id": "NFPA72-23.8.2", "feature": "Battery monitoring / 24h standby", "paths": ["src/fire_suppression/power/manager.py", "src/fire_suppression/power/battery_balancer.py"]},
        {"id": "NFPA10-4.2", "feature": "Extinguisher accessibility", "paths": ["src/fire_suppression/diagnostics/nfpa_compliance.py"]},
        {"id": "NFPA72-10.4", "feature": "System test records", "paths": ["src/fire_suppression/diagnostics/self_test_scheduler.py", "src/fire_suppression/telemetry/audit.py"]},
        {"id": "NFPA72-12.6", "feature": "Alarm priority and annunciation", "paths": ["src/fire_suppression/alerts/alert_prioritizer.py", "src/fire_suppression/alerts/voice_alert.py"]},
        {"id": "NFPA72-14.4", "feature": "Monitoring for integrity", "paths": ["src/fire_suppression/sensors/base.py", "src/fire_suppression/resilience/stay_alive.py"]},
        {"id": "NFPA72-26.2", "feature": "Mass notification", "paths": ["src/fire_suppression/alerts/mass_notification_gateway.py"]},
        {"id": "UL-864", "feature": "Control unit reliability", "paths": ["src/fire_suppression/diagnostics/watchdog.py", "src/fire_suppression/diagnostics/startup_check.py"]},
    ]

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        self._manifest: dict[str, Any] | None = None

    def build_manifest(self) -> dict[str, Any]:
        project_root = Path(__file__).resolve().parents[4]
        entries = []
        for rule in self._REGULATORY_RULES:
            file_hashes = {}
            for rel in rule["paths"]:
                p = project_root / rel
                if p.exists():
                    file_hashes[rel] = self._hash_file(p)
                else:
                    file_hashes[rel] = None
            entries.append({
                "rule_id": rule["id"],
                "feature": rule["feature"],
                "paths": rule["paths"],
                "file_hashes": file_hashes,
                "verified": all(v is not None for v in file_hashes.values()),
            })
        manifest = {
            "feature_id": "V7-010",
            "generated_at": time.time(),
            "version": "0.8.0",
            "entries": entries,
            "coverage": sum(1 for e in entries if e["verified"]) / len(entries),
        }
        manifest["manifest_hash"] = self._hash_manifest(manifest)
        self._manifest = manifest
        return manifest

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def _hash_manifest(self, manifest: dict[str, Any]) -> str:
        payload = json.dumps(manifest, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def delta(self, previous_manifest: dict[str, Any]) -> dict[str, Any]:
        current = self.build_manifest()
        prev_entries = {e["rule_id"]: e for e in previous_manifest.get("entries", [])}
        changes = []
        for e in current["entries"]:
            prev = prev_entries.get(e["rule_id"])
            if not prev:
                changes.append({"rule_id": e["rule_id"], "change": "added"})
            elif e["file_hashes"] != prev.get("file_hashes"):
                changes.append({"rule_id": e["rule_id"], "change": "modified"})
        for rid in set(prev_entries) - {e["rule_id"] for e in current["entries"]}:
            changes.append({"rule_id": rid, "change": "removed"})
        return {"current_hash": current["manifest_hash"], "changes": changes}

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-010",
            "healthy": True,
            "coverage": self._manifest["coverage"] if self._manifest else None,
            "manifest_hash": self._manifest["manifest_hash"] if self._manifest else None,
            "mock": self.mock,
        }
