"""Tamper-evident audit log with compliance reporting.

# IMP-010 — Comprehensive Audit Log & Compliance Reporting

Each log entry is hashed and linked to the previous entry, creating a
blockchain-like chain that detects tampering. Supports export to
HTML/PDF reports.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# SQLite schema for audit log
AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    details_json TEXT,
    previous_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_entries(event_type);
"""


@dataclass
class AuditEntry:
    """A single tamper-evident audit log entry."""
    id: int
    timestamp: float
    event_type: str
    actor: str
    details: dict
    previous_hash: str
    entry_hash: str


class AuditLogger:
    """Tamper-evident audit logger with hash chaining.

    Usage::

        audit = AuditLogger("/var/lib/fire-suppression/audit.db")
        audit.log("system_start", actor="admin", details={"reason": "maintenance_complete"})
        audit.log("fire_alert", actor="system", details={"confidence": 0.92})

        # Verify chain integrity
        if not audit.verify_chain():
            logger.critical("AUDIT LOG TAMPERING DETECTED")
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(AUDIT_SCHEMA)
        self._conn.commit()

    def _get_last_hash(self) -> str:
        """Get the hash of the most recent entry, or a genesis hash."""
        row = self._conn.execute(
            "SELECT entry_hash FROM audit_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return row["entry_hash"]
        # Genesis hash
        return hashlib.sha256(b"GENESIS").hexdigest()

    def _compute_hash(self, timestamp: float, event_type: str, actor: str,
                     details: str, previous_hash: str) -> str:
        """Compute SHA-256 hash of an entry."""
        data = f"{timestamp}|{event_type}|{actor}|{details}|{previous_hash}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def log(self, event_type: str, actor: str = "system", details: dict | None = None) -> str:
        """Add a new tamper-evident audit entry.

        Returns the entry hash.
        """
        timestamp = time.time()
        details_json = json.dumps(details) if details else "{}"
        previous_hash = self._get_last_hash()
        entry_hash = self._compute_hash(timestamp, event_type, actor, details_json, previous_hash)

        self._conn.execute(
            """INSERT INTO audit_entries
               (timestamp, event_type, actor, details_json, previous_hash, entry_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timestamp, event_type, actor, details_json, previous_hash, entry_hash),
        )
        self._conn.commit()
        logger.debug("Audit logged: %s (hash: %s...)", event_type, entry_hash[:16])
        return entry_hash

    def verify_chain(self) -> bool:
        """Verify the entire audit chain for tampering.

        Returns True if chain is intact, False if tampering detected.
        """
        entries = self._conn.execute(
            "SELECT * FROM audit_entries ORDER BY id ASC"
        ).fetchall()

        if not entries:
            return True

        expected_previous = hashlib.sha256(b"GENESIS").hexdigest()
        for row in entries:
            computed = self._compute_hash(
                row["timestamp"], row["event_type"], row["actor"],
                row["details_json"], row["previous_hash"],
            )
            if computed != row["entry_hash"]:
                logger.critical("Audit chain broken at entry %d: hash mismatch", row["id"])
                return False
            if row["previous_hash"] != expected_previous:
                logger.critical("Audit chain broken at entry %d: previous hash mismatch", row["id"])
                return False
            expected_previous = row["entry_hash"]

        logger.info("Audit chain verified: %d entries intact", len(entries))
        return True

    def get_entries(
        self,
        event_type: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 1000,
    ) -> list[AuditEntry]:
        """Query audit entries with filters."""
        query = "SELECT * FROM audit_entries WHERE 1=1"
        params: list = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            AuditEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                event_type=row["event_type"],
                actor=row["actor"],
                details=json.loads(row["details_json"]),
                previous_hash=row["previous_hash"],
                entry_hash=row["entry_hash"],
            )
            for row in rows
        ]

    def generate_html_report(
        self,
        output_path: str | Path,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> Path:
        """Generate an HTML audit report.

        Returns the path to the generated file.
        """
        entries = self.get_entries(start_time=start_time, end_time=end_time, limit=10000)
        chain_valid = self.verify_chain()

        integrity_html = (
            '<span class="valid">✓ VERIFIED</span>' if chain_valid
            else '<span class="invalid">✗ TAMPERING DETECTED</span>'
        )

        lines = [
            "<!DOCTYPE html>",
            "<html><head><meta charset='UTF-8'>",
            "<title>Fire Suppression Audit Report</title>",
            "<style>",
            "body{font-family:monospace;margin:20px;background:#f5f5f5;}",
            ".header{background:#333;color:#fff;padding:15px;border-radius:8px;}",
            ".valid{color:green;font-weight:bold;}",
            ".invalid{color:red;font-weight:bold;}",
            "table{width:100%;border-collapse:collapse;background:#fff;}",
            "th{background:#444;color:#fff;padding:10px;text-align:left;}",
            "td{padding:8px;border-bottom:1px solid #ddd;}",
            "tr:nth-child(even){background:#f9f9f9;}",
            ".hash{font-size:0.8em;color:#666;word-break:break-all;}",
            "</style></head><body>",
            "<div class='header'>",
            "<h1>Fire Suppression Audit Report</h1>",
            f"<p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>",
            f"<p>Chain Integrity: {integrity_html}</p>",
            f"<p>Total Entries: {len(entries)}</p>",
            "</div>",
            "<table>",
            "<tr><th>ID</th><th>Time</th><th>Event</th><th>Actor</th><th>Details</th><th>Hash</th></tr>",
        ]

        for entry in entries:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            details_str = json.dumps(entry.details, indent=None)[:100]
            lines.append(
                f"<tr>"
                f"<td>{entry.id}</td>"
                f"<td>{ts}</td>"
                f"<td>{entry.event_type}</td>"
                f"<td>{entry.actor}</td>"
                f"<td><pre>{details_str}</pre></td>"
                f"<td class='hash'>{entry.entry_hash[:32]}...</td>"
                f"</tr>"
            )

        lines.extend(["</table>", "</body></html>"])

        output = Path(output_path)
        output.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Audit report generated: %s (%d entries)", output, len(entries))
        return output

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
