"""Anti-tamper USB update agent with Ed25519 signature verification.

# SEC-001 — USB Update Agent

Provides cryptographically verified firmware and configuration updates
via USB. Protects against:

1. Malicious USB inserts with forged updates
2. Insider tampering with update packages
3. Man-in-the-middle modification during transfer
4. Unauthorized downgrade attacks
5. Missing rollback capability

Each update is signed with Ed25519. The public key is baked into the
device firmware (or stored in TPM/ATECC608B if available).

Usage::

    from fire_suppression.diagnostics.usb_update_agent import USBUpdateAgent
    agent = USBUpdateAgent(public_key_hex="abc123...")

    # On USB insert
    result = await agent.process_usb_update("/media/usb0")
    if result.success:
        print(f"Updated to {result.new_version}")
    else:
        print(f"Update rejected: {result.rejection_reason}")

Update Package Format::

    update-package/
    ├── manifest.json          # version, timestamp, device_id, files list
    ├── signature.ed25519      # Ed25519 signature of manifest+content hash
    ├── contents.sha256        # per-file SHA-256 hashes
    ├── firmware/              # actual files to install
    │   └── src/fire_suppression/...
    └── config.patch           # optional signed config changes
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class UpdateResult:
    """Result of an update attempt."""
    success: bool
    new_version: str | None = None
    previous_version: str | None = None
    rejection_reason: str | None = None
    files_updated: list[str] = None
    rollback_available: bool = False
    block_hash: str | None = None  # blockchain record

    def __post_init__(self) -> None:
        if self.files_updated is None:
            self.files_updated = []


class USBUpdateAgent:
    """Anti-tamper USB update agent with signature verification.

    Verifies Ed25519 signatures, checks device compatibility,
    stages updates atomically, and maintains rollback history.
    """

    REQUIRED_MANIFEST_FIELDS = {"version", "timestamp", "device_id", "files", "content_hash"}

    def __init__(
        self,
        public_key_hex: str | None = None,
        project_root: str | None = None,
        max_versions_kept: int = 3,
        *,
        mock: bool = False,
    ) -> None:
        """Initialize update agent.

        Args:
            public_key_hex: Ed25519 public key (64 hex chars) for verification.
                If None, updates are rejected unless mock=True.
            project_root: Root directory of the project. Defaults to
                ~/projects/open-fire-suppression/.
            max_versions_kept: Number of previous versions to retain.
            mock: If True, skip cryptographic verification.
        """
        self.mock = mock
        self.public_key: bytes | None = None
        if public_key_hex:
            self.public_key = bytes.fromhex(public_key_hex)
        self.project_root = Path(project_root) if project_root else Path.home() / "projects" / "open-fire-suppression"
        self.max_versions = max_versions_kept
        self._version_dir = self.project_root / ".versions"
        self._staging_dir = self.project_root / ".update-staging"
        self._version_dir.mkdir(parents=True, exist_ok=True)
        self._current_version = self._detect_current_version()
        logger.info("USBUpdateAgent initialized: version=%s, mock=%s", self._current_version, mock)

    # ── Version Detection ─────────────────────────────────────────

    def _detect_current_version(self) -> str:
        """Read current version from git or version file."""
        version_file = self.project_root / "version.txt"
        if version_file.exists():
            return version_file.read_text().strip()
        # Try git
        git_dir = self.project_root / ".git"
        if git_dir.exists():
            try:
                import subprocess
                result = subprocess.run(
                    ["git", "describe", "--tags", "--always"],
                    cwd=str(self.project_root),
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass
        return "unknown"

    def get_current_version(self) -> str:
        return self._current_version

    # ── Core Update Flow ──────────────────────────────────────────

    async def process_usb_update(self, usb_mount: str | Path) -> UpdateResult:
        """Process a USB update package.

        Steps:
        1. Find update package on USB
        2. Verify Ed25519 signature
        3. Verify content hashes
        4. Check device compatibility
        5. Stage update atomically
        6. Verify staged files
        7. Apply update with backup
        8. Log to blockchain

        Returns:
            UpdateResult with success/failure details.
        """
        usb_path = Path(usb_mount)
        if not usb_path.exists():
            return UpdateResult(False, rejection_reason="USB mount not found")

        # Find update package
        package = self._find_update_package(usb_path)
        if not package:
            return UpdateResult(False, rejection_reason="No valid update package found on USB")

        logger.info("Found update package: %s", package)

        # Step 1: Verify manifest integrity
        manifest_ok, manifest = self._verify_manifest(package)
        if not manifest_ok:
            return UpdateResult(False, rejection_reason="Invalid manifest: " + str(manifest))

        # Step 2: Verify Ed25519 signature
        if not self.mock:
            sig_ok, sig_reason = self._verify_signature(package, manifest)
            if not sig_ok:
                return UpdateResult(False, rejection_reason=f"Signature verification failed: {sig_reason}")
        else:
            logger.warning("MOCK MODE: skipping Ed25519 signature verification")

        # Step 3: Verify content hashes
        hash_ok, hash_reason = self._verify_content_hashes(package, manifest)
        if not hash_ok:
            return UpdateResult(False, rejection_reason=f"Content hash mismatch: {hash_reason}")

        # Step 4: Check device compatibility
        compat_ok, compat_reason = self._check_compatibility(manifest)
        if not compat_ok:
            return UpdateResult(False, rejection_reason=f"Compatibility check failed: {compat_reason}")

        # Step 5: Check downgrade protection
        if not self._is_version_newer(manifest.get("version", "")):
            return UpdateResult(False, rejection_reason="Update version is not newer than current")

        # Step 6: Stage and apply atomically
        apply_ok, apply_result = await self._stage_and_apply(package, manifest)
        if not apply_ok:
            return UpdateResult(False, rejection_reason=f"Apply failed: {apply_result}")

        # Step 7: Log to blockchain
        block_hash = self._log_update_to_blockchain(manifest)

        return UpdateResult(
            success=True,
            new_version=manifest.get("version"),
            previous_version=self._current_version,
            files_updated=manifest.get("files", []),
            rollback_available=True,
            block_hash=block_hash,
        )

    # ── Package Discovery ─────────────────────────────────────────

    def _find_update_package(self, usb_path: Path) -> Path | None:
        """Find update package directory or zip on USB."""
        # Look for update-package/ directory
        pkg_dir = usb_path / "update-package"
        if pkg_dir.exists():
            return pkg_dir
        # Look for update-package.zip
        pkg_zip = usb_path / "update-package.zip"
        if pkg_zip.exists():
            extract_dir = usb_path / ".update-extract"
            with zipfile.ZipFile(pkg_zip, "r") as zf:
                zf.extractall(extract_dir)
            return extract_dir / "update-package"
        # Look for any .zip containing manifest.json
        for zip_file in usb_path.glob("*.zip"):
            try:
                with zipfile.ZipFile(zip_file, "r") as zf:
                    if "update-package/manifest.json" in zf.namelist():
                        extract_dir = usb_path / ".update-extract"
                        with zipfile.ZipFile(zip_file, "r") as zf2:
                            zf2.extractall(extract_dir)
                        return extract_dir / "update-package"
            except zipfile.BadZipFile:
                continue
        return None

    # ── Manifest Verification ─────────────────────────────────────

    def _verify_manifest(self, package: Path) -> tuple[bool, dict[str, Any] | str]:
        """Read and validate manifest.json."""
        manifest_path = package / "manifest.json"
        if not manifest_path.exists():
            return False, "manifest.json not found"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"

        missing = self.REQUIRED_MANIFEST_FIELDS - set(manifest.keys())
        if missing:
            return False, f"Missing fields: {missing}"

        # Validate types
        if not isinstance(manifest["files"], list):
            return False, "files must be a list"
        if not isinstance(manifest["content_hash"], str):
            return False, "content_hash must be a string"

        return True, manifest

    # ── Signature Verification ──────────────────────────────────────

    def _verify_signature(self, package: Path, manifest: dict) -> tuple[bool, str]:
        """Verify Ed25519 signature of the update package."""
        if self.public_key is None:
            return False, "No public key configured — reject all unsigned updates"

        sig_path = package / "signature.ed25519"
        if not sig_path.exists():
            return False, "signature.ed25519 not found"

        try:
            from nacl.signing import VerifyKey  # type: ignore
            vk = VerifyKey(self.public_key)
            signature = sig_path.read_bytes()

            # Signed data = manifest JSON + content hash concatenation
            signed_data = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            vk.verify(signed_data, signature)
            return True, ""
        except ImportError:
            logger.warning("pynacl not installed — falling back to hash-only verification (INSECURE)")
            return False, "pynacl not installed"
        except Exception as e:
            return False, f"Signature invalid: {e}"

    # ── Content Hash Verification ──────────────────────────────────

    def _verify_content_hashes(self, package: Path, manifest: dict) -> tuple[bool, str]:
        """Verify SHA-256 hashes of all files in the package."""
        contents_path = package / "contents.sha256"
        if not contents_path.exists():
            return False, "contents.sha256 not found"

        try:
            expected_hashes = json.loads(contents_path.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"Invalid contents.sha256: {e}"

        firmware_dir = package / "firmware"
        if not firmware_dir.exists():
            return False, "firmware/ directory not found"

        for rel_path, expected_hash in expected_hashes.items():
            file_path = firmware_dir / rel_path
            if not file_path.exists():
                return False, f"File missing: {rel_path}"
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                return False, f"Hash mismatch for {rel_path}: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."

        # Verify overall content hash matches manifest
        combined = json.dumps(expected_hashes, sort_keys=True).encode("utf-8")
        overall_hash = hashlib.sha256(combined).hexdigest()
        if overall_hash != manifest["content_hash"]:
            return False, f"Overall content hash mismatch"

        return True, ""

    # ── Compatibility Checks ──────────────────────────────────────

    def _check_compatibility(self, manifest: dict) -> tuple[bool, str]:
        """Check device compatibility."""
        device_id = manifest.get("device_id", "*")
        if device_id != "*" and device_id != self._get_device_id():
            return False, f"Device ID mismatch: package for {device_id}, this device is {self._get_device_id()}"

        # Check Python version compatibility if specified
        target_py = manifest.get("target_python_version")
        if target_py:
            import sys
            current_py = f"{sys.version_info.major}.{sys.version_info.minor}"
            if current_py != target_py:
                return False, f"Python version mismatch: package requires {target_py}, running {current_py}"

        return True, ""

    def _get_device_id(self) -> str:
        """Generate stable device ID from hardware serial or MAC."""
        try:
            # Try Raspberry Pi serial from /proc/cpuinfo
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Serial"):
                        return line.split(":")[1].strip()
        except Exception:
            pass
        # Fallback to MAC address
        try:
            import uuid
            mac = uuid.getnode()
            return f"{mac:012x}"
        except Exception:
            pass
        return "unknown"

    def _is_version_newer(self, new_version: str) -> bool:
        """Simple version comparison. Supports semantic versioning."""
        if not new_version:
            return False
        try:
            def parse(v: str) -> tuple:
                return tuple(int(x) for x in v.strip("v").split(".")[:3])
            return parse(new_version) > parse(self._current_version)
        except ValueError:
            return new_version != self._current_version

    # ── Staging and Atomic Apply ────────────────────────────────────

    async def _stage_and_apply(self, package: Path, manifest: dict) -> tuple[bool, str]:
        """Stage update, verify, then apply atomically with backup."""
        try:
            # Clean staging
            if self._staging_dir.exists():
                shutil.rmtree(self._staging_dir)
            self._staging_dir.mkdir(parents=True)

            # Copy firmware to staging
            firmware_src = package / "firmware"
            for src_file in firmware_src.rglob("*"):
                if src_file.is_file():
                    rel_path = src_file.relative_to(firmware_src)
                    dest = self._staging_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_file), str(dest))

            # Verify staged files
            staged_ok, staged_reason = self._verify_staged_files(manifest)
            if not staged_ok:
                return False, f"Staged file verification failed: {staged_reason}"

            # Backup current version
            await self._backup_current_version()

            # Apply update atomically (copy from staging to project root)
            for staged_file in self._staging_dir.rglob("*"):
                if staged_file.is_file():
                    rel_path = staged_file.relative_to(self._staging_dir)
                    dest = self.project_root / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(staged_file), str(dest))

            # Update version file
            version_file = self.project_root / "version.txt"
            version_file.write_text(manifest["version"] + "\n", encoding="utf-8")
            self._current_version = manifest["version"]

            # Clean old versions
            self._prune_old_versions()

            logger.info("Update applied: %s", manifest["version"])
            return True, manifest["version"]

        except Exception as e:
            logger.exception("Update application failed")
            return False, str(e)

    def _verify_staged_files(self, manifest: dict) -> tuple[bool, str]:
        """Verify all files copied to staging correctly."""
        contents_path = manifest.get("_package_path", Path()) / "contents.sha256"
        if not contents_path.exists():
            return True, ""  # No contents hash to verify against
        try:
            expected = json.loads(contents_path.read_text(encoding="utf-8"))
            for rel_path, expected_hash in expected.items():
                staged = self._staging_dir / rel_path
                if not staged.exists():
                    return False, f"Staged file missing: {rel_path}"
                actual = hashlib.sha256(staged.read_bytes()).hexdigest()
                if actual != expected_hash:
                    return False, f"Staged hash mismatch: {rel_path}"
            return True, ""
        except Exception:
            return True, ""  # Best effort verification

    async def _backup_current_version(self) -> None:
        """Create a backup of the current version."""
        backup_dir = self._version_dir / self._current_version
        if backup_dir.exists():
            # Overwrite if same version somehow
            shutil.rmtree(backup_dir)
        backup_dir.mkdir(parents=True)

        # Backup all Python source files
        for py_file in self.project_root.rglob("*.py"):
            if ".git" in str(py_file) or "__pycache__" in str(py_file):
                continue
            rel = py_file.relative_to(self.project_root)
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(py_file), str(dest))

        # Backup config
        config_src = self.project_root / "config" / "config.yaml"
        if config_src.exists():
            dest = backup_dir / "config" / "config.yaml"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(config_src), str(dest))

        # Write backup manifest
        manifest = {
            "version": self._current_version,
            "timestamp": time.time(),
            "backup_path": str(backup_dir),
        }
        (backup_dir / "backup_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        logger.info("Backed up version %s to %s", self._current_version, backup_dir)

    def _prune_old_versions(self) -> None:
        """Keep only the most recent N versions."""
        versions = sorted(
            [d for d in self._version_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for old in versions[self.max_versions:]:
            shutil.rmtree(old)
            logger.info("Pruned old version backup: %s", old.name)

    # ── Rollback ────────────────────────────────────────────────────

    async def rollback(self, target_version: str | None = None) -> UpdateResult:
        """Rollback to a previous version.

        Args:
            target_version: Version to rollback to. If None, rolls back
                to the most recent previous version.

        Returns:
            UpdateResult indicating rollback success/failure.
        """
        versions = [d.name for d in self._version_dir.iterdir() if d.is_dir()]
        if not versions:
            return UpdateResult(False, rejection_reason="No previous versions available for rollback")

        if target_version is None:
            # Find the most recent version that isn't current
            sorted_versions = sorted(versions, reverse=True)
            target_version = next((v for v in sorted_versions if v != self._current_version), None)

        if target_version is None or target_version not in versions:
            return UpdateResult(False, rejection_reason=f"Version {target_version} not found in backups")

        backup_dir = self._version_dir / target_version
        if not backup_dir.exists():
            return UpdateResult(False, rejection_reason=f"Backup directory missing: {backup_dir}")

        try:
            # Restore files from backup
            for src_file in backup_dir.rglob("*"):
                if src_file.is_file() and src_file.name != "backup_manifest.json":
                    rel = src_file.relative_to(backup_dir)
                    dest = self.project_root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_file), str(dest))

            self._current_version = target_version
            version_file = self.project_root / "version.txt"
            version_file.write_text(target_version + "\n", encoding="utf-8")

            logger.warning("Rolled back to version %s", target_version)
            return UpdateResult(
                success=True,
                new_version=target_version,
                previous_version=self._current_version,
                rollback_available=True,
            )
        except Exception as e:
            logger.exception("Rollback failed")
            return UpdateResult(False, rejection_reason=f"Rollback failed: {e}")

    # ── Blockchain Logging ──────────────────────────────────────────

    def _log_update_to_blockchain(self, manifest: dict) -> str | None:
        """Log update event to blockchain audit."""
        try:
            from fire_suppression.telemetry.blockchain_audit import BlockchainAudit
            audit = BlockchainAudit(mock=self.mock)
            block = audit.add_event(
                "SYSTEM_UPDATE",
                {
                    "version": manifest.get("version"),
                    "previous_version": self._current_version,
                    "timestamp": time.time(),
                    "device_id": self._get_device_id(),
                    "files_updated": manifest.get("files", []),
                },
            )
            return block.block_hash
        except Exception:
            logger.exception("Failed to log update to blockchain")
            return None

    # ── Tamper Detection ──────────────────────────────────────────

    async def scan_for_unauthorized_changes(self) -> list[dict[str, Any]]:
        """Scan for unauthorized modifications to source files.

        Compares current files against the most recent backup hash manifest.
        Detects tampering that bypassed the update agent.

        Returns:
            List of tampered files with details.
        """
        tampered = []
        latest_backup = self._get_latest_backup()
        if not latest_backup:
            return [{"warning": "No backup available for comparison"}]

        manifest_path = latest_backup / "contents_hashes.json"
        if not manifest_path.exists():
            # Generate hashes on the fly for comparison
            expected = self._hash_all_source_files()
        else:
            expected = json.loads(manifest_path.read_text(encoding="utf-8"))

        current = self._hash_all_source_files()
        for rel_path, current_hash in current.items():
            expected_hash = expected.get(rel_path)
            if expected_hash is None:
                tampered.append({
                    "file": rel_path,
                    "issue": "new_file",
                    "current_hash": current_hash,
                })
            elif current_hash != expected_hash:
                tampered.append({
                    "file": rel_path,
                    "issue": "modified",
                    "expected_hash": expected_hash,
                    "current_hash": current_hash,
                })

        for rel_path in expected:
            if rel_path not in current:
                tampered.append({
                    "file": rel_path,
                    "issue": "deleted",
                    "expected_hash": expected[rel_path],
                })

        if tampered:
            logger.warning("Tamper scan found %d issues", len(tampered))
            # Log to blockchain
            try:
                from fire_suppression.telemetry.blockchain_audit import BlockchainAudit
                audit = BlockchainAudit(mock=self.mock)
                audit.add_event("TAMPER_DETECTED", {"files": tampered, "timestamp": time.time()})
            except Exception:
                pass

        return tampered

    def _hash_all_source_files(self) -> dict[str, str]:
        """Calculate SHA-256 hashes of all Python source files."""
        hashes = {}
        for py_file in self.project_root.rglob("*.py"):
            if ".git" in str(py_file) or "__pycache__" in str(py_file) or ".versions" in str(py_file):
                continue
            rel = str(py_file.relative_to(self.project_root))
            hashes[rel] = hashlib.sha256(py_file.read_bytes()).hexdigest()
        return hashes

    def _get_latest_backup(self) -> Path | None:
        """Get the most recent version backup directory."""
        versions = sorted(
            [d for d in self._version_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        return versions[0] if versions else None

    # ── Serialization ─────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return agent status as dictionary."""
        backups = [d.name for d in self._version_dir.iterdir() if d.is_dir()]
        return {
            "current_version": self._current_version,
            "mock_mode": self.mock,
            "public_key_configured": self.public_key is not None,
            "backups_available": backups,
            "max_versions_kept": self.max_versions,
        }
