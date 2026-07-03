"""Tests for startup diagnostics.

# IMP-005 — Self-Diagnostic Health Check Suite
"""
import pytest

from fire_suppression.config import Config
from fire_suppression.diagnostics.startup_check import (
    CheckResult,
    DiagnosticCheck,
    DiagnosticReport,
    StartupDiagnostics,
)


class TestStartupDiagnostics:
    """# IMP-005 — Self-Diagnostic Health Check Suite"""

    def setup_method(self) -> None:
        Config._instance = None

    @pytest.mark.asyncio
    async def test_run_all_returns_report(self) -> None:
        diag = StartupDiagnostics()
        report = await diag.run_all()
        assert isinstance(report, DiagnosticReport)
        assert report.summary["total"] > 0

    @pytest.mark.asyncio
    async def test_critical_checks_present(self) -> None:
        diag = StartupDiagnostics()
        await diag.run_all()
        names = [c.name for c in diag._checks]
        assert "i2c_bus" in names
        assert "sensors_communication" in names
        assert "safety_inputs" in names

    @pytest.mark.asyncio
    async def test_report_has_summary(self) -> None:
        diag = StartupDiagnostics()
        report = await diag.run_all()
        summary = report.summary
        assert "total" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "all_critical_passed" in summary

    def test_report_to_dict(self) -> None:
        checks = [
            DiagnosticCheck("test1", CheckResult.PASS, "ok", 10.0),
            DiagnosticCheck("i2c_bus", CheckResult.FAIL, "scan failed", 5.0),
        ]
        report = DiagnosticReport(checks)
        d = report.to_dict()
        assert d["summary"]["total"] == 2
        assert d["summary"]["passed"] == 1
        assert d["summary"]["failed"] == 1
        assert d["summary"]["all_critical_passed"] is False
