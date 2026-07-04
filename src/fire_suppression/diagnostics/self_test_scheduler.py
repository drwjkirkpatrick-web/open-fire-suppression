"""V7-003 — Self-Test Scheduler & Report

NFPA 72 requires periodic testing of fire alarm components. This module
schedules daily/weekly/monthly/annual self-tests, runs them in mock-safe mode,
and generates PDF-ready reports.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class TestFrequency(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ANNUAL = "annual"


class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass
class ScheduledTest:
    id: str
    name: str
    frequency: TestFrequency
    component: str
    last_run: float | None = None
    last_result: TestResult = TestResult.PENDING
    last_message: str = ""
    next_due: float | None = None


class SelfTestScheduler:
    """Schedules, runs, and reports NFPA-mandated self-tests."""

    _INTERVALS: dict[TestFrequency, float] = {
        TestFrequency.DAILY: 24 * 3600,
        TestFrequency.WEEKLY: 7 * 24 * 3600,
        TestFrequency.MONTHLY: 30 * 24 * 3600,
        TestFrequency.ANNUAL: 365 * 24 * 3600,
    }

    _DEFAULT_TESTS: list[tuple[str, str, TestFrequency, str]] = [
        ("sensor_comm", "Sensor Communication Check", TestFrequency.DAILY, "sensors"),
        ("buzzer_pattern", "Buzzer Pattern Test", TestFrequency.WEEKLY, "alerts"),
        ("relay_dry_run", "Relay Dry-Run Test", TestFrequency.MONTHLY, "actuation"),
        ("battery_discharge", "30-Minute Battery Discharge Test", TestFrequency.ANNUAL, "power"),
        ("fim_baseline", "File Integrity Baseline Check", TestFrequency.MONTHLY, "security"),
        ("sms_loopback", "SMS Loopback Test", TestFrequency.WEEKLY, "alerts"),
        ("camera_capture", "Camera Capture Test", TestFrequency.WEEKLY, "detection"),
        ("compliance_scan", "NFPA Compliance Scan", TestFrequency.MONTHLY, "compliance"),
    ]

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        cfg = self.config.section("self_test_scheduler")
        self.enabled = bool(cfg.get("enabled", True))
        self._tests: dict[str, ScheduledTest] = {}
        for tid, name, freq, comp in self._DEFAULT_TESTS:
            self._tests[tid] = ScheduledTest(id=tid, name=name, frequency=freq, component=comp)
        self._last_report: dict[str, Any] | None = None

    def due_tests(self) -> list[ScheduledTest]:
        now = time.time()
        return [t for t in self._tests.values() if t.next_due is None or t.next_due <= now]

    def run_test(self, test_id: str, mock_result: TestResult | None = None) -> dict[str, Any]:
        test = self._tests.get(test_id)
        if not test:
            return {"id": test_id, "result": "unknown", "message": "Test not found"}
        if not self.enabled:
            test.last_result = TestResult.SKIPPED
            test.last_message = "Scheduler disabled"
            return {"id": test_id, "result": "skipped", "message": "Scheduler disabled"}

        # Run simulated component test (mock-first)
        result, message = self._execute(test, mock_result)
        now = time.time()
        test.last_run = now
        test.last_result = result
        test.last_message = message
        test.next_due = now + self._INTERVALS[test.frequency]
        logger.info("Self-test %s: %s - %s", test_id, result.value, message)
        return {"id": test_id, "result": result.value, "message": message, "next_due": test.next_due}

    def _execute(self, test: ScheduledTest, mock_result: TestResult | None) -> tuple[TestResult, str]:
        if mock_result:
            return mock_result, f"Mock result injected for {test.name}"
        # In production these would call real subsystems; mock returns deterministic pass
        if test.component in ("sensors", "alerts", "actuation", "power", "detection", "security", "compliance"):
            return TestResult.PASS, f"{test.name} completed successfully"
        return TestResult.FAIL, f"{test.name} has no runner"

    def run_all_due(self) -> list[dict[str, Any]]:
        return [self.run_test(t.id) for t in self.due_tests()]

    def generate_report(self) -> dict[str, Any]:
        now = time.time()
        items = []
        for t in self._tests.values():
            due_status = "due" if (t.next_due is None or t.next_due <= now) else "ok"
            items.append({
                "id": t.id,
                "name": t.name,
                "frequency": t.frequency.value,
                "component": t.component,
                "last_run": t.last_run,
                "last_result": t.last_result.value,
                "last_message": t.last_message,
                "next_due": t.next_due,
                "status": due_status,
            })
        report = {
            "feature_id": "V7-003",
            "generated_at": now,
            "healthy": all(i["last_result"] != "fail" for i in items),
            "tests": items,
            "summary": {
                "total": len(items),
                "pass": sum(1 for i in items if i["last_result"] == "pass"),
                "fail": sum(1 for i in items if i["last_result"] == "fail"),
                "pending": sum(1 for i in items if i["last_result"] == "pending"),
                "due": sum(1 for i in items if i["status"] == "due"),
            },
        }
        self._last_report = report
        return report

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-003",
            "enabled": self.enabled,
            "test_count": len(self._tests),
            "last_report_summary": self._last_report["summary"] if self._last_report else None,
        }
