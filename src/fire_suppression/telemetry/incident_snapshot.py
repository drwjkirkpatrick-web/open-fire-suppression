"""V9-006 — Incident Snapshot Export

One-click ZIP export of recent sensor readings, events, and audit hashes for
fire-marshal, insurance, or legal handoff. The package is small, hashed, and
chain-of-custody ready.

Personality: *Phosphorus* — the charismatic communicator. Warm, clear,
organized handoff documentation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from fire_suppression.telemetry.logger import TelemetryLogger

logger = logging.getLogger(__name__)


@dataclass
class SnapshotPackage:
    package_id: str
    created_at: float
    minutes: int
    zip_bytes: bytes
    file_count: int
    sha256: str
    formats: list[str]


class IncidentSnapshotExporter:
    """Build a tamper-evident ZIP snapshot of the last N minutes of data."""

    PERSONALITY = "Phosphorus"

    def __init__(
        self,
        telemetry_logger: TelemetryLogger | None = None,
        data_dir: str = "/opt/fire-suppression/data",
    ) -> None:
        self.telemetry_logger = telemetry_logger
        self.data_dir = Path(data_dir)

    async def export(self, minutes: int = 15) -> SnapshotPackage:
        """Create a ZIP snapshot covering the last ``minutes``."""
        now = time.time()
        start = now - minutes * 60
        package_id = f"SNAPSHOT-{time.strftime('%Y%m%d-%H%M%S')}"
        buffer = BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            file_count = 0
            formats_used: set[str] = set()

            # 1. Recent sensor telemetry
            sensor_data = self._recent_sensor_data(start)
            if sensor_data:
                payload = json.dumps(sensor_data, indent=2, default=str).encode("utf-8")
                zf.writestr("sensor_data.json", payload)
                file_count += 1
                formats_used.add("json")

            # 2. Recent events
            events = self._recent_events(start)
            if events:
                payload = json.dumps(events, indent=2, default=str).encode("utf-8")
                zf.writestr("events.json", payload)
                file_count += 1
                formats_used.add("json")

            # 3. Audit hashes if an audit file exists
            audit = self._audit_hashes(start)
            if audit:
                payload = json.dumps(audit, indent=2, default=str).encode("utf-8")
                zf.writestr("audit_hashes.json", payload)
                file_count += 1
                formats_used.add("json")

            # 4. Readme note inside the package
            readme = self._package_readme(package_id, minutes, file_count)
            zf.writestr("README.txt", readme)
            file_count += 1

        zip_bytes = buffer.getvalue()
        sha = hashlib.sha256(zip_bytes).hexdigest()
        logger.info("Incident snapshot %s created: %d files, %d bytes", package_id, file_count, len(zip_bytes))

        return SnapshotPackage(
            package_id=package_id,
            created_at=now,
            minutes=minutes,
            zip_bytes=zip_bytes,
            file_count=file_count,
            sha256=sha,
            formats=sorted(formats_used),
        )

    def _recent_sensor_data(self, start: float) -> dict[str, Any]:
        """Return recent sensor history from telemetry logger."""
        if self.telemetry_logger is None:
            return {}
        history = getattr(self.telemetry_logger, "sensor_history", {})
        recent: dict[str, list[dict[str, Any]]] = {}
        for name, readings in history.items():
            filtered = [
                r for r in readings
                if isinstance(r, dict) and r.get("ts", 0) >= start
            ]
            if filtered:
                recent[name] = filtered
        return {"exported_at": time.time(), "sensor_count": len(recent), "readings": recent}

    def _recent_events(self, start: float) -> dict[str, Any]:
        """Return recent events from telemetry logger."""
        if self.telemetry_logger is None:
            return {}
        events = getattr(self.telemetry_logger, "events", [])
        recent = [e for e in events if isinstance(e, dict) and e.get("ts", 0) >= start]
        return {"exported_at": time.time(), "event_count": len(recent), "events": recent}

    def _audit_hashes(self, start: float) -> dict[str, Any]:
        """Return recent audit hash entries if an audit file exists."""
        audit_file = self.data_dir / "audit_hashes.json"
        if not audit_file.exists():
            return {}
        try:
            data = json.loads(audit_file.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
            recent = [e for e in entries if isinstance(e, dict) and e.get("ts", 0) >= start]
            return {"exported_at": time.time(), "audit_count": len(recent), "entries": recent}
        except Exception as exc:
            logger.warning("Audit snapshot failed: %s", exc)
            return {}

    def _package_readme(self, package_id: str, minutes: int, file_count: int) -> str:
        return (
            f"Incident Snapshot Package: {package_id}\n"
            f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Covers last {minutes} minutes of operation\n"
            f"Files: {file_count}\n"
            f"Hash: SHA-256 of this ZIP\n"
            f"\nThis package is for fire marshal, insurance, or legal handoff.\n"
            f"Do not alter contents after extraction.\n"
        )

    def to_dict(self, minutes: int = 15) -> dict[str, Any]:
        return {
            "personality": self.PERSONALITY,
            "ready": True,
            "default_minutes": minutes,
        }
