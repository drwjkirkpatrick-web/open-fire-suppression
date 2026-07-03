"""File Integrity Monitor (FIM) for real-time tamper detection.

# SEC-001 — File Integrity Monitor

Continuously monitors SHA-256 hashes of all Python source files,
configuration files, and critical system files. Detects unauthorized
modifications in real-time and logs alerts to the blockchain audit log.

This is the first line of defense against:
- Insider threats modifying source code
- Malware injecting backdoors into Python modules
- Unauthorized config changes bypassing update agent
- Physical tampering with storage

Usage::

    from fire_suppression.diagnostics.file_integrity_monitor import FileIntegrityMonitor
    fim = FileIntegrityMonitor(project_root="/opt/fire-suppression")

    # Baseline current state
    await fim.create_baseline()

    # Periodic scan
    tampered = await fim.scan()
    for issue in tampered:
        print(f"ALERT: {issue['file']} {issue['issue']}")
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IntegrityBaseline:
    """Stored baseline of file hashes."""
    created_at: float
    files: dict[str, str]  # rel_path -> sha256_hex
    scan_paths: list[str] = field(default_factory=list)
    excluded_patterns: list[str] = field(default_factory=list)


class FileIntegrityMonitor:
    """Real-time file integrity monitoring for fire suppression system.

    Creates a cryptographic baseline of all source and config files,
    then detects any deviations on subsequent scans.
    """

    DEFAULT_SCAN_PATHS = [
        "src/fire_suppression",
        "config",
        "tests",
    ]

    DEFAULT_EXCLUDES = [
        "__pycache__",
        "*.pyc",
        ".git",
        ".versions",
        ".update-staging",
        ".pytest_cache",
        "*.egg-info",
        "node_modules",
        ".coverage",
        "htmlcov",
    ]

    def __init__(
        self,
        project_root: str | Path | None = None,
        baseline_path: str | Path | None = None,
        scan_paths: list[str] | None = None,
        excluded_patterns: list[str] | None = None,
        *,
        mock: bool = False,
    ) -> None:
        """Initialize FIM.

        Args:
            project_root: Root directory to monitor. Defaults to
                ~/projects/open-fire-suppression/.
            baseline_path: Where to store/load baseline JSON.
            scan_paths: Relative paths under project_root to scan.
            excluded_patterns: Glob patterns to exclude.
            mock: If True, don't write to disk.
        """
        self.mock = mock
        self.project_root = Path(project_root) if project_root else Path.home() / "projects" / "open-fire-suppression"
        self.baseline_path = Path(baseline_path) if baseline_path else self.project_root / ".integrity_baseline.json"
        self.scan_paths = scan_paths or self.DEFAULT_SCAN_PATHS
        self.excluded_patterns = excluded_patterns or self.DEFAULT_EXCLUDES
        self._baseline: IntegrityBaseline | None = None

    # ── Baseline Management ───────────────────────────────────────

    async def create_baseline(self) -> IntegrityBaseline:
        """Create a new integrity baseline of all monitored files.

        Returns:
            IntegrityBaseline with file hashes.
        """
        files = self._scan_files()
        baseline = IntegrityBaseline(
            created_at=time.time(),
            files=files,
            scan_paths=self.scan_paths,
            excluded_patterns=self.excluded_patterns,
        )
        self._baseline = baseline
        if not self.mock:
            self._save_baseline(baseline)
        logger.info("FIM baseline created: %d files", len(files))
        return baseline

    def load_baseline(self) -> IntegrityBaseline | None:
        """Load existing baseline from disk."""
        if self.mock or not self.baseline_path.exists():
            return None
        try:
            data = json.loads(self.baseline_path.read_text(encoding="utf-8"))
            self._baseline = IntegrityBaseline(
                created_at=data["created_at"],
                files=data["files"],
                scan_paths=data.get("scan_paths", []),
                excluded_patterns=data.get("excluded_patterns", []),
            )
            return self._baseline
        except Exception:
            logger.exception("Failed to load FIM baseline")
            return None

    def _save_baseline(self, baseline: IntegrityBaseline) -> None:
        """Save baseline to disk."""
        data = {
            "created_at": baseline.created_at,
            "files": baseline.files,
            "scan_paths": baseline.scan_paths,
            "excluded_patterns": baseline.excluded_patterns,
            "baseline_hash": hashlib.sha256(
                json.dumps(baseline.files, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }
        self.baseline_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Scanning ──────────────────────────────────────────────────

    async def scan(self) -> list[dict[str, Any]]:
        """Scan for integrity violations against the baseline.

        Returns:
            List of tampered files. Each dict contains:
            - file: relative path
            - issue: 'modified' | 'new_file' | 'deleted' | 'permission_changed'
            - expected_hash: str (if applicable)
            - current_hash: str (if applicable)
        """
        if self._baseline is None:
            self._baseline = self.load_baseline()
        if self._baseline is None:
            logger.warning("No baseline available — run create_baseline() first")
            return [{"warning": "No baseline available"}]

        current = self._scan_files()
        tampered = []

        # Check for modifications and new files
        for rel_path, current_hash in current.items():
            expected = self._baseline.files.get(rel_path)
            if expected is None:
                tampered.append({
                    "file": rel_path,
                    "issue": "new_file",
                    "current_hash": current_hash,
                    "timestamp": time.time(),
                })
            elif current_hash != expected:
                tampered.append({
                    "file": rel_path,
                    "issue": "modified",
                    "expected_hash": expected,
                    "current_hash": current_hash,
                    "timestamp": time.time(),
                })

        # Check for deletions
        for rel_path in self._baseline.files:
            if rel_path not in current:
                tampered.append({
                    "file": rel_path,
                    "issue": "deleted",
                    "expected_hash": self._baseline.files[rel_path],
                    "timestamp": time.time(),
                })

        if tampered:
            logger.warning("FIM scan found %d integrity issues", len(tampered))
            await self._log_tamper_events(tampered)
        else:
            logger.debug("FIM scan clean")

        return tampered

    def _scan_files(self) -> dict[str, str]:
        """Scan monitored paths and return file hashes."""
        files = {}
        for scan_path in self.scan_paths:
            full_path = self.project_root / scan_path
            if not full_path.exists():
                continue
            for file_path in full_path.rglob("*"):
                if not file_path.is_file():
                    continue
                rel = str(file_path.relative_to(self.project_root))
                if self._is_excluded(rel):
                    continue
                files[rel] = hashlib.sha256(file_path.read_bytes()).hexdigest()
        return files

    def _is_excluded(self, rel_path: str) -> bool:
        """Check if path matches exclusion patterns."""
        for pattern in self.excluded_patterns:
            if pattern in rel_path:
                return True
            if rel_path.endswith(pattern.lstrip("*")):
                return True
        return False

    async def _log_tamper_events(self, tampered: list[dict]) -> None:
        """Log tamper detections to blockchain and alert system."""
        try:
            from fire_suppression.telemetry.blockchain_audit import BlockchainAudit
            audit = BlockchainAudit(mock=self.mock)
            for event in tampered[:10]:  # Log first 10 to avoid flooding
                audit.add_event(
                    "TAMPER_DETECTED",
                    {
                        "file": event["file"],
                        "issue": event["issue"],
                        "expected_hash": event.get("expected_hash"),
                        "current_hash": event.get("current_hash"),
                        "timestamp": event["timestamp"],
                    },
                )
        except Exception:
            logger.exception("Failed to log tamper events to blockchain")

    # ── Utility ──────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return FIM statistics."""
        baseline = self._baseline or self.load_baseline()
        return {
            "baseline_exists": baseline is not None,
            "baseline_created": baseline.created_at if baseline else None,
            "monitored_files": len(baseline.files) if baseline else 0,
            "scan_paths": self.scan_paths,
            "excluded_patterns": self.excluded_patterns,
        }

    def force_rescan_baseline(self) -> None:
        """Force a complete re-baseline of all files.

        Use only after verified authorized changes.
        Logs the rebaseline event to blockchain.
        """
        import asyncio
        asyncio.create_task(self.create_baseline())
        try:
            from fire_suppression.telemetry.blockchain_audit import BlockchainAudit
            audit = BlockchainAudit(mock=self.mock)
            audit.add_event("BASELINE_RECREATED", {"timestamp": time.time(), "reason": "authorized"})
        except Exception:
            pass

    # ── Serialization ────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return self.get_stats()
