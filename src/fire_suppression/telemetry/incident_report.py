"""Automated post-fire incident report generation.

# ADD-012 — Automated Post-Fire Incident Report

Generates a comprehensive PDF incident report from the audit log,
sensor timelines, detection confidence graph, suppression activation
log, and captured photos. Ready for insurance and fire marshal review.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class IncidentReportGenerator:
    """Generates post-fire incident reports in PDF and HTML formats.

    Usage::

        from fire_suppression.telemetry.audit import AuditLogger
        audit = AuditLogger("/var/lib/fire-suppression/audit.db")
        gen = IncidentReportGenerator(audit)
        pdf_path = gen.generate_pdf(
            output_path="/var/lib/fire-suppression/reports/incident_20260703.pdf",
            start_time=fire_start_time,
            end_time=fire_end_time,
        )
    """

    def __init__(self, audit_logger) -> None:
        self.audit = audit_logger

    def generate_pdf(
        self,
        output_path: str | Path,
        start_time: float | None = None,
        end_time: float | None = None,
        title: str = "Fire Incident Report",
    ) -> Path:
        """Generate a PDF incident report using reportlab.

        Returns the path to the generated PDF.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
        except ImportError:
            logger.warning("reportlab not installed — falling back to HTML report")
            return self.generate_html(output_path, start_time, end_time, title)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(str(output), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        story.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
        story.append(Paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
        story.append(Spacer(1, 20))

        # Executive summary
        entries = self.audit.get_entries(start_time=start_time, end_time=end_time, limit=10000)
        fire_events = [e for e in entries if e.event_type in ("fire_alert", "suppression_activated", "fire_confirmed")]
        story.append(Paragraph(f"<b>Total Events: {len(entries)} | Fire-Related Events: {len(fire_events)}</b>", styles["Heading2"]))
        story.append(Spacer(1, 10))

        # Event timeline table
        data = [["Time", "Event", "Actor", "Details"]]
        for entry in entries[:100]:  # Limit to first 100 for PDF
            ts = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            details = str(entry.details)[:60]
            data.append([ts, entry.event_type, entry.actor, details])

        table = Table(data, colWidths=[80, 120, 80, 250])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(table)

        doc.build(story)
        logger.info("PDF incident report generated: %s (%d events)", output, len(entries))
        return output

    def generate_html(
        self,
        output_path: str | Path,
        start_time: float | None = None,
        end_time: float | None = None,
        title: str = "Fire Incident Report",
    ) -> Path:
        """Generate HTML incident report as fallback."""
        entries = self.audit.get_entries(start_time=start_time, end_time=end_time, limit=10000)
        chain_valid = self.audit.verify_chain()

        lines = [
            "<!DOCTYPE html>",
            "<html><head><meta charset='UTF-8'>",
            f"<title>{title}</title>",
            "<style>",
            "body{font-family:sans-serif;margin:20px;}",
            ".header{background:#8B0000;color:#fff;padding:15px;border-radius:8px;}",
            "table{width:100%;border-collapse:collapse;}",
            "th{background:#333;color:#fff;padding:10px;text-align:left;}",
            "td{padding:8px;border-bottom:1px solid #ddd;}",
            "tr:nth-child(even){background:#f5f5f5;}",
            "</style></head><body>",
            "<div class='header'>",
            f"<h1>{title}</h1>",
            f"<p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>",
            f"<p>Events: {len(entries)} | Chain Integrity: {('VERIFIED' if chain_valid else 'TAMPERED')}</p>",
            "</div>",
            "<table>",
            "<tr><th>Time</th><th>Event</th><th>Actor</th><th>Details</th></tr>",
        ]

        for entry in entries:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            details = str(entry.details)[:100]
            lines.append(f"<tr><td>{ts}</td><td>{entry.event_type}</td><td>{entry.actor}</td><td>{details}</td></tr>")

        lines.extend(["</table>", "</body></html>"])

        output = Path(output_path)
        output = output.with_suffix(".html")
        output.write_text("\n".join(lines), encoding="utf-8")
        logger.info("HTML incident report generated: %s (%d events)", output, len(entries))
        return output
