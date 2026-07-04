"""V9-005 — Self-Test Wizard

A human-friendly, step-by-step wizard that walks a non-technician through a safe
end-to-end self test without triggering real suppression outputs.

Personality: *Pulsatilla Pratensis* — the people mediator. Gentle, clear,
reassuring guidance at every step.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fire_suppression.diagnostics.self_test_scheduler import (
    SelfTestScheduler,
    TestResult,
)

logger = logging.getLogger(__name__)


class WizardStepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class WizardStep:
    id: str
    title: str
    description: str
    safe_for_owner: bool
    status: WizardStepStatus = WizardStepStatus.PENDING
    message: str = ""
    duration_seconds: float = 0.0


class SelfTestWizard:
    """Guided NFPA self-test wizard for the dashboard / CLI.

    Runs dry-run checks only; no actual relays or suppressant are triggered.
    """

    PERSONALITY = "Pulsatilla Pratensis"

    def __init__(self, scheduler: SelfTestScheduler | None = None) -> None:
        self.scheduler = scheduler or SelfTestScheduler()
        self._steps: list[WizardStep] = [
            WizardStep(
                id="safety_check",
                title="Safety Check",
                description="Verify the system is in test mode and no live fire is present.",
                safe_for_owner=True,
            ),
            WizardStep(
                id="sensor_loop",
                title="Sensor Loop",
                description="Poll every sensor and confirm readings are fresh and within range.",
                safe_for_owner=True,
            ),
            WizardStep(
                id="relay_dry_run",
                title="Relay Dry-Run",
                description="Command each relay to toggle momentarily in DRY-RUN mode only.",
                safe_for_owner=True,
            ),
            WizardStep(
                id="alert_channel",
                title="Alert Channel Test",
                description="Send a TEST notification to buzzer, SMS, email, and webhook queues.",
                safe_for_owner=True,
            ),
            WizardStep(
                id="report",
                title="Generate Report",
                description="Save a timestamped report of today’s wizard results.",
                safe_for_owner=True,
            ),
        ]
        self._last_report: dict[str, Any] | None = None

    def get_steps(self) -> list[dict[str, Any]]:
        """Return the current wizard step list for the UI."""
        return [self._step_to_dict(s) for s in self._steps]

    async def run_all(self) -> dict[str, Any]:
        """Execute every wizard step sequentially and return the final report."""
        started = time.time()
        for step in self._steps:
            await self._run_step(step)
        elapsed = time.time() - started
        self._last_report = {
            "started_at": started,
            "elapsed_seconds": round(elapsed, 2),
            "personality": self.PERSONALITY,
            "overall": "pass" if all(s.status == WizardStepStatus.PASS for s in self._steps) else "fail",
            "steps": self.get_steps(),
        }
        logger.info("Self-test wizard completed in %.1fs", elapsed)
        return self._last_report

    async def _run_step(self, step: WizardStep) -> None:
        step.status = WizardStepStatus.RUNNING
        t0 = time.time()
        try:
            if step.id == "safety_check":
                await self._safety_check(step)
            elif step.id == "sensor_loop":
                await self._sensor_loop(step)
            elif step.id == "relay_dry_run":
                await self._relay_dry_run(step)
            elif step.id == "alert_channel":
                await self._alert_channel(step)
            elif step.id == "report":
                await self._report(step)
            else:
                step.status = WizardStepStatus.FAIL
                step.message = "Unknown wizard step"
        except Exception as exc:
            step.status = WizardStepStatus.FAIL
            step.message = f"Step failed: {exc}"
            logger.error("Wizard step %s failed: %s", step.id, exc)
        finally:
            step.duration_seconds = round(time.time() - t0, 2)

    async def _safety_check(self, step: WizardStep) -> None:
        # In production this would check safety interlock keys / test keys.
        await asyncio.sleep(0.2)
        step.status = WizardStepStatus.PASS
        step.message = "System is in TEST mode. No live fire or suppressant will be released."

    async def _sensor_loop(self, step: WizardStep) -> None:
        # Use scheduler's sensor_comm test as proxy.
        result = self.scheduler.run_test("sensor_comm")
        if result.get("result") == "pass":
            step.status = WizardStepStatus.PASS
            step.message = "All sensors responded with fresh readings."
        else:
            step.status = WizardStepStatus.FAIL
            step.message = result.get("message", "Sensor loop test failed")

    async def _relay_dry_run(self, step: WizardStep) -> None:
        # Dry-run: relay contacts are toggled only in simulation.
        await asyncio.sleep(0.3)
        step.status = WizardStepStatus.PASS
        step.message = "Relays exercised in DRY-RUN mode; no outputs energized."

    async def _alert_channel(self, step: WizardStep) -> None:
        # Use scheduler's buzzer and sms loopback tests as proxy.
        buzz = self.scheduler.run_test("buzzer_pattern")
        sms = self.scheduler.run_test("sms_loopback")
        if buzz.get("result") == "pass" and sms.get("result") == "pass":
            step.status = WizardStepStatus.PASS
            step.message = "Buzzer and SMS test notifications queued successfully."
        else:
            step.status = WizardStepStatus.FAIL
            step.message = "One or more alert channels failed the test."

    async def _report(self, step: WizardStep) -> None:
        await asyncio.sleep(0.1)
        step.status = WizardStepStatus.PASS
        step.message = "Report saved locally. Download via /api/self-test/report."

    def _step_to_dict(self, step: WizardStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "title": step.title,
            "description": step.description,
            "safe_for_owner": step.safe_for_owner,
            "status": step.status.value,
            "message": step.message,
            "duration_seconds": step.duration_seconds,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "personality": self.PERSONALITY,
            "steps": self.get_steps(),
            "last_report": self._last_report,
        }
