"""Intrusion Detection System (IDS) for the fire suppression platform.

# SEC-003 — Intrusion Detection System

Continuously monitors USB insertions, process anomalies, network behaviour,
file-system changes, and configuration tampering.  Generates severity-ranked
alerts with bilingual (English / Swahili) messages and logs every event to an
SQLite-backed store with an optional blockchain audit hook.

Designed for Raspberry Pi 5 (ARM64) with Python 3.10+.

Usage::

    from fire_suppression.diagnostics.intrusion_detection import IntrusionDetectionSystem
    ids = IntrusionDetectionSystem(db_path="/var/lib/fire-suppression/ids.db")
    alerts = await ids.sweep()
    for alert in alerts:
        print(alert.severity, alert.message_en)
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = "/var/lib/fire-suppression/ids.db"
SENSITIVE_DIRS = ["/etc/fire-suppression", "/opt/fire-suppression", "/var/lib/fire-suppression", "config", "src/fire_suppression"]
PROCESS_WHITELIST = {"python", "python3", "systemd", "sshd", "dbus-daemon", "cron", "rsyslogd", "journald", "wpa_supplicant", "dhcpcd", "nginx", "uvicorn", "fastapi", "pytest", "bash", "sh"}
TRUSTED_USB_VIDS: set[str] = set()
NETWORK_WHITELIST_HOSTS: set[str] = set()


# ── Severity ─────────────────────────────────────────────────────────────

class Severity(Enum):
    """Severity classification for IDS alerts."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class IDSAlert:
    """A single IDS alert with bilingual messaging."""
    alert_id: str
    timestamp: float
    severity: Severity
    category: str
    message_en: str
    message_sw: str
    details: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id, "timestamp": self.timestamp,
            "severity": self.severity.value, "category": self.category,
            "message_en": self.message_en, "message_sw": self.message_sw,
            "details": self.details, "acknowledged": self.acknowledged,
        }


# ── Main IDS class ───────────────────────────────────────────────────────

class IntrusionDetectionSystem:
    """Multi-layer intrusion detection for fire-suppression systems.

    Layers:
    1. USB insertion monitoring
    2. Process anomaly detection
    3. Network anomaly detection
    4. File-system anomaly detection
    5. Config tampering detection

    All events are written to an SQLite database and optionally anchored to
    the blockchain audit log.
    """

    def __init__(
        self,
        db_path: str | None = None,
        project_root: str | Path | None = None,
        *,
        mock: bool = False,
    ) -> None:
        """Initialize the IDS.

        Args:
            db_path: Path to the SQLite event database.
            project_root: Root of the project (used to resolve relative dirs).
            mock: If True, skip system-level probes and return synthetic data.
        """
        self.mock = mock
        self.db_path = Path(db_path) if db_path else Path(DEFAULT_DB_PATH)
        self.project_root = Path(project_root) if project_root else (Path.home() / "projects" / "open-fire-suppression")
        self._last_usb: set[str] = set()
        self._last_pids: set[int] = set()
        self._last_net: set[str] = set()
        self._fs_baseline: dict[str, str] | None = None
        self._cfg_mtime: float | None = None
        self._cfg_hash: str | None = None
        if not mock:
            self._init_db()
        logger.info("IDS initialized: db=%s mock=%s", self.db_path, mock)

    # ── Database layer ─────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create the SQLite schema if it does not already exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS ids_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id TEXT NOT NULL UNIQUE,
                    timestamp REAL NOT NULL,
                    severity TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message_en TEXT NOT NULL,
                    message_sw TEXT NOT NULL,
                    details TEXT,
                    acknowledged INTEGER DEFAULT 0)"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_time ON ids_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cat ON ids_events(category)")
            conn.commit()
        finally:
            conn.close()

    def _log_event(self, alert: IDSAlert) -> None:
        """Persist an alert to SQLite."""
        if self.mock:
            return
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """INSERT OR REPLACE INTO ids_events
                (alert_id, timestamp, severity, category, message_en, message_sw, details, acknowledged)
                VALUES (?,?,?,?,?,?,?,?)""",
                (alert.alert_id, alert.timestamp, alert.severity.value, alert.category,
                 alert.message_en, alert.message_sw, json.dumps(alert.details, separators=(",", ":")),
                 int(alert.acknowledged)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_events(
        self, category: str | None = None, severity: Severity | None = None, limit: int = 100
    ) -> list[IDSAlert]:
        """Query the event log ordered newest-first."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            query, params = "SELECT * FROM ids_events WHERE 1=1", []
            if category:
                query += " AND category = ?"
                params.append(category)
            if severity:
                query += " AND severity = ?"
                params.append(severity.value)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
        return [
            IDSAlert(
                alert_id=r[1], timestamp=r[2], severity=Severity(r[3]), category=r[4],
                message_en=r[5], message_sw=r[6], details=json.loads(r[7]) if r[7] else {},
                acknowledged=bool(r[8]),
            ) for r in rows
        ]

    # ── Blockchain hook ────────────────────────────────────────────────────

    def _anchor_to_blockchain(self, alert: IDSAlert) -> None:
        """Push a tamper-evident record to the blockchain audit log."""
        if self.mock:
            return
        try:
            from fire_suppression.telemetry.blockchain_audit import BlockchainAudit
            audit = BlockchainAudit(mock=False)
            audit.add_event(
                "IDS_ALERT",
                {"alert_id": alert.alert_id, "severity": alert.severity.value,
                 "category": alert.category, "message_en": alert.message_en,
                 "timestamp": alert.timestamp},
            )
        except Exception:
            logger.exception("Failed to anchor IDS alert to blockchain")

    # ── Sweep orchestrator ─────────────────────────────────────────────────

    async def sweep(self) -> list[IDSAlert]:
        """Run all detection layers and return generated alerts."""
        alerts: list[IDSAlert] = []
        alerts.extend(await self._check_usb())
        alerts.extend(await self._check_processes())
        alerts.extend(await self._check_network())
        alerts.extend(await self._check_filesystem())
        alerts.extend(await self._check_config_tampering())
        for alert in alerts:
            self._log_event(alert)
            self._anchor_to_blockchain(alert)
        logger.warning("IDS sweep: %d alert(s) raised", len(alerts)) if alerts else logger.debug("IDS sweep: clean")
        return alerts

    # ── Layer 1: USB insertion monitoring ──────────────────────────────────

    async def _check_usb(self) -> list[IDSAlert]:
        """Detect untrusted USB devices plugged in since the last sweep."""
        alerts: list[IDSAlert] = []
        current = self._get_usb_devices()
        new_devs = current - self._last_usb
        self._last_usb = current
        for dev in new_devs:
            vid = self._extract_usb_vid(dev)
            sev = Severity.HIGH if (TRUSTED_USB_VIDS and vid not in TRUSTED_USB_VIDS) else Severity.MEDIUM
            alerts.append(IDSAlert(
                alert_id=self._hash("usb", dev), timestamp=time.time(), severity=sev, category="usb",
                message_en=f"USB device inserted: {dev}",
                message_sw=f"Kifaa cha USB kimeingizwa: {dev}",
                details={"device": dev, "vendor_id": vid},
            ))
        return alerts

    def _get_usb_devices(self) -> set[str]:
        """Return a set of currently attached USB device paths."""
        if self.mock:
            return {"/dev/bus/usb/001/001", "/dev/bus/usb/001/002"}
        devices: set[str] = set()
        usb_base = Path("/dev/bus/usb")
        if usb_base.exists():
            for bus in usb_base.iterdir():
                if bus.is_dir():
                    for dev in bus.iterdir():
                        if dev.is_char_device():
                            devices.add(str(dev))
        return devices

    def _extract_usb_vid(self, device_path: str) -> str:
        """Best-effort extraction of USB vendor ID from sysfs."""
        try:
            parts = Path(device_path).parts
            bus, dev = parts[-2], parts[-1]
            vid_path = Path(f"/sys/bus/usb/devices/{bus}-{dev}/idVendor")
            if vid_path.exists():
                return vid_path.read_text().strip()
        except Exception:
            pass
        return "unknown"

    # ── Layer 2: Process anomaly detection ─────────────────────────────────

    async def _check_processes(self) -> list[IDSAlert]:
        """Flag unexpected new processes and CPU / memory spikes."""
        alerts: list[IDSAlert] = []
        procs = self._get_processes()
        current_pids = {p["pid"] for p in procs}
        new_pids = current_pids - self._last_pids
        self._last_pids = current_pids
        for pid in new_pids:
            proc = next((p for p in procs if p["pid"] == pid), None)
            if proc and proc["name"] not in PROCESS_WHITELIST:
                alerts.append(IDSAlert(
                    alert_id=self._hash("proc", str(pid)), timestamp=time.time(),
                    severity=Severity.HIGH, category="process",
                    message_en=f"Unexpected process started: {proc['name']} (PID {pid})",
                    message_sw=f"Mchakato usiotarajiwa umeanza: {proc['name']} (PID {pid})",
                    details={"pid": pid, "name": proc["name"], "cmdline": proc.get("cmdline", "")},
                ))
        for proc in procs:
            cpu, mem = proc.get("cpu_percent", 0.0), proc.get("memory_percent", 0.0)
            if cpu > 95.0:
                alerts.append(IDSAlert(
                    alert_id=self._hash("cpu", str(proc["pid"])), timestamp=time.time(),
                    severity=Severity.CRITICAL, category="process",
                    message_en=f"Critical CPU spike: {proc['name']} ({cpu:.1f}%)",
                    message_sw=f"Kiwango kikubwa cha CPU: {proc['name']} ({cpu:.1f}%)",
                    details={"pid": proc["pid"], "name": proc["name"], "cpu_percent": cpu},
                ))
            if mem > 80.0:
                alerts.append(IDSAlert(
                    alert_id=self._hash("mem", str(proc["pid"])), timestamp=time.time(),
                    severity=Severity.HIGH, category="process",
                    message_en=f"High memory usage: {proc['name']} ({mem:.1f}%)",
                    message_sw=f"Matumizi makubwa ya kumbukumbu: {proc['name']} ({mem:.1f}%)",
                    details={"pid": proc["pid"], "name": proc["name"], "memory_percent": mem},
                ))
        return alerts

    def _get_processes(self) -> list[dict[str, Any]]:
        """Return process dicts with pid, name, cpu_percent, memory_percent."""
        if self.mock:
            return [
                {"pid": 1, "name": "systemd", "cpu_percent": 2.5, "memory_percent": 1.2, "cmdline": "/sbin/init"},
                {"pid": 999, "name": "suspicious_agent", "cpu_percent": 97.0, "memory_percent": 85.0, "cmdline": "/tmp/suspicious_agent"},
            ]
        procs: list[dict[str, Any]] = []
        try:
            import psutil  # type: ignore[import-untyped]
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "cmdline"]):
                info = p.info
                procs.append({
                    "pid": info["pid"], "name": info["name"] or "unknown",
                    "cpu_percent": info.get("cpu_percent", 0.0) or 0.0,
                    "memory_percent": info.get("memory_percent", 0.0) or 0.0,
                    "cmdline": " ".join(info.get("cmdline") or []),
                })
        except Exception:
            logger.debug("psutil not available — skipping live process scan")
        return procs

    # ── Layer 3: Network anomaly detection ─────────────────────────────────

    async def _check_network(self) -> list[IDSAlert]:
        """Flag unexpected outbound connections and traffic spikes."""
        alerts: list[IDSAlert] = []
        conns = self._get_network_connections()
        current = {c["key"] for c in conns}
        new_keys = current - self._last_net
        self._last_net = current
        for c in conns:
            key = c["key"]
            if key in new_keys and c.get("remote", "unknown") not in NETWORK_WHITELIST_HOSTS:
                alerts.append(IDSAlert(
                    alert_id=self._hash("net", key), timestamp=time.time(),
                    severity=Severity.MEDIUM, category="network",
                    message_en=f"Unexpected outbound connection to {c['remote']}",
                    message_sw=f"Muunganiko wa nje usiotarajiwa kwa {c['remote']}",
                    details={"remote": c.get("remote"), "local": c.get("local"), "status": c.get("status")},
                ))
            if c.get("bytes_sent", 0) > 100_000_000:
                alerts.append(IDSAlert(
                    alert_id=self._hash("traffic", key), timestamp=time.time(),
                    severity=Severity.HIGH, category="network",
                    message_en=f"Traffic spike on connection to {c.get('remote', 'unknown')}",
                    message_sw=f"Mtiririko mkubwa wa data kwa muunganiko wa {c.get('remote', 'unknown')}",
                    details={"remote": c.get("remote"), "bytes_sent": c["bytes_sent"]},
                ))
        return alerts

    def _get_network_connections(self) -> list[dict[str, Any]]:
        """Return connection dicts with key, remote, local, status, bytes_sent."""
        if self.mock:
            return [{
                "key": "tcp-192.168.1.100-443", "remote": "192.168.1.100:443",
                "local": "10.0.0.5:54321", "status": "ESTABLISHED", "bytes_sent": 150_000_000,
            }]
        conns: list[dict[str, Any]] = []
        try:
            import psutil  # type: ignore[import-untyped]
            for c in psutil.net_connections(kind="inet"):
                if c.status != "ESTABLISHED" or not c.raddr:
                    continue
                key = f"{c.type.name}-{c.raddr.ip}-{c.raddr.port}"
                conns.append({
                    "key": key, "remote": f"{c.raddr.ip}:{c.raddr.port}",
                    "local": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "",
                    "status": c.status, "bytes_sent": 0,
                })
        except Exception:
            logger.debug("psutil not available — skipping live network scan")
        return conns

    # ── Layer 4: File-system anomaly detection ───────────────────────────

    async def _check_filesystem(self) -> list[IDSAlert]:
        """Detect unexpected file creations / modifications / deletions."""
        alerts: list[IDSAlert] = []
        current = self._scan_sensitive_dirs()
        if self._fs_baseline is None:
            self._fs_baseline = current
            return alerts
        for rel, h in current.items():
            if rel not in self._fs_baseline:
                alerts.append(IDSAlert(
                    alert_id=self._hash("fs-new", rel), timestamp=time.time(),
                    severity=Severity.HIGH, category="filesystem",
                    message_en=f"New file in sensitive directory: {rel}",
                    message_sw=f"Faili mpya katika saraka nyeti: {rel}",
                    details={"path": rel, "hash": h},
                ))
            elif self._fs_baseline[rel] != h:
                alerts.append(IDSAlert(
                    alert_id=self._hash("fs-mod", rel), timestamp=time.time(),
                    severity=Severity.MEDIUM, category="filesystem",
                    message_en=f"File modified in sensitive directory: {rel}",
                    message_sw=f"Faili limebadilishwa katika saraka nyeti: {rel}",
                    details={"path": rel, "old_hash": self._fs_baseline[rel], "new_hash": h},
                ))
        for rel in self._fs_baseline:
            if rel not in current:
                alerts.append(IDSAlert(
                    alert_id=self._hash("fs-del", rel), timestamp=time.time(),
                    severity=Severity.HIGH, category="filesystem",
                    message_en=f"File deleted from sensitive directory: {rel}",
                    message_sw=f"Faili limefutwa kutoka saraka nyeti: {rel}",
                    details={"path": rel},
                ))
        self._fs_baseline = current
        return alerts

    def _scan_sensitive_dirs(self) -> dict[str, str]:
        """Walk sensitive directories and return rel_path -> sha256 mapping."""
        files: dict[str, str] = {}
        if self.mock:
            files["config/config.yaml"] = hashlib.sha256(b"mock-config").hexdigest()
            return files
        for d in SENSITIVE_DIRS:
            path = Path(d) if Path(d).is_absolute() else self.project_root / d
            if not path.exists():
                continue
            for item in path.rglob("*"):
                if not item.is_file():
                    continue
                try:
                    rel = str(item.relative_to(self.project_root)) if str(item).startswith(str(self.project_root)) else str(item)
                    files[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
                except Exception:
                    pass
        return files

    # ── Layer 5: Config tampering detection ──────────────────────────────

    async def _check_config_tampering(self) -> list[IDSAlert]:
        """Detect config.yaml modified outside the authorised 02:00-04:00 window."""
        alerts: list[IDSAlert] = []
        cfg = self.project_root / "config" / "config.yaml"
        if not cfg.exists():
            return alerts
        mtime = cfg.stat().st_mtime
        chash = hashlib.sha256(cfg.read_bytes()).hexdigest()
        if self._cfg_mtime is None:
            self._cfg_mtime, self._cfg_hash = mtime, chash
            return alerts
        if chash != self._cfg_hash:
            hour = time.localtime(mtime).tm_hour
            authorised = 2 <= hour < 4
            sev = Severity.LOW if authorised else Severity.CRITICAL
            msg_en = (
                "config.yaml modified during authorised maintenance window"
                if authorised else
                "config.yaml modified OUTSIDE authorised maintenance window"
            )
            msg_sw = (
                "config.yaml limebadilishwa wakati wa matengenezo yaliyoidhinishwa"
                if authorised else
                "config.yaml limebadilishwa NJE ya dirisha la kuidhinishwa la matengenezo"
            )
            alerts.append(IDSAlert(
                alert_id=self._hash("cfg", str(cfg)), timestamp=time.time(),
                severity=sev, category="config", message_en=msg_en, message_sw=msg_sw,
                details={"path": str(cfg), "previous_hash": self._cfg_hash, "current_hash": chash,
                         "authorised_window": authorised, "hour": hour},
            ))
            self._cfg_hash = chash
        self._cfg_mtime = mtime
        return alerts

    # ── Utilities ────────────────────────────────────────────────────────

    @staticmethod
    def _hash(category: str, identifier: str) -> str:
        """Deterministic alert ID from category + identifier."""
        return hashlib.sha256(f"{category}:{identifier}".encode()).hexdigest()[:16]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged in the database."""
        if self.mock:
            return True
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.execute("UPDATE ids_events SET acknowledged = 1 WHERE alert_id = ?", (alert_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def to_dict(self) -> dict[str, Any]:
        """Serialize IDS status for dashboard / telemetry."""
        return {
            "mock": self.mock, "db_path": str(self.db_path),
            "project_root": str(self.project_root),
            "usb_devices_tracked": len(self._last_usb),
            "processes_tracked": len(self._last_pids),
            "net_connections_tracked": len(self._last_net),
            "file_baseline_entries": len(self._fs_baseline) if self._fs_baseline else 0,
            "config_baseline_hash": self._cfg_hash,
        }
