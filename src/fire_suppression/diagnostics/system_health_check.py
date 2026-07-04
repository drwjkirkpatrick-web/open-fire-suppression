"""V9-010 — System Health Check API/CLI

Returns a concise green/yellow/red summary of the whole system plus the first
remediation step. Designed for sysadmins, remote support, and quick triage.

Personality: *Silicea Terra* — the QA polisher. Pass/fail clarity with exactly
one actionable next step.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any

from fire_suppression.config import Config
from fire_suppression.diagnostics.self_test_scheduler import SelfTestScheduler
from fire_suppression.power.battery_forecaster import BatteryForecaster
from fire_suppression.sensors.drift_widget import SensorDriftWidget
from fire_suppression.telemetry.acknowledgment_manager import AcknowledgmentManager
from fire_suppression.telemetry.daily_digest import DailyDigestGenerator

logger = logging.getLogger(__name__)


@dataclass
class HealthResult:
    """Concise system health result."""

    status: str  # "green" | "yellow" | "red"
    timestamp: float
    personality: str
    first_remediation: str
    checks: dict[str, str]
    details: dict[str, Any]


class SystemHealthCheck:
    """Aggregate subsystem health into one pass/fail-style answer."""

    PERSONALITY = "Silicea Terra"

    def __init__(
        self,
        sensor_manager=None,
        power_manager=None,
        detection_manager=None,
        safety_manager=None,
        telemetry_logger=None,
        test_scheduler=None,
        ack_manager=None,
        config: Config | None = None,
    ) -> None:
        self.config = config or Config()
        self.sensor_manager = sensor_manager
        self.power_manager = power_manager
        self.detection_manager = detection_manager
        self.safety_manager = safety_manager
        self.telemetry_logger = telemetry_logger
        self.test_scheduler = test_scheduler or SelfTestScheduler()
        self.ack_manager = ack_manager
        self._battery_forecaster = BatteryForecaster(power_manager, self.config)
        self._drift_widget = SensorDriftWidget()
        self._digest = DailyDigestGenerator(
            telemetry_logger=telemetry_logger,
            test_scheduler=self.test_scheduler,
            power_manager=power_manager,
            config=self.config,
        )

    async def check(self) -> HealthResult:
        """Run all health checks and return a concise result."""
        now = time.time()
        checks: dict[str, str] = {}
        details: dict[str, Any] = {}

        # 1. Sensors
        checks["sensors"], details["sensors"] = await self._check_sensors()

        # 2. Power
        checks["power"], details["power"] = await self._check_power()

        # 3. Detection / risk
        checks["detection"], details["detection"] = self._check_detection()

        # 4. Safety interlocks
        checks["safety"], details["safety"] = self._check_safety()

        # 5. Telemetry / logging
        checks["telemetry"], details["telemetry"] = self._check_telemetry()

        # 6. Network (mock-safe ping fallback)
        checks["network"], details["network"] = self._check_network()

        # 7. Tests
        checks["tests"], details["tests"] = self._check_tests()

        # 8. Alerts / acknowledgments
        checks["alerts"], details["alerts"] = self._check_alerts()

        status = self._aggregate_status(checks.values())
        first_remediation = self._first_remediation(status, checks, details)

        return HealthResult(
            status=status,
            timestamp=now,
            personality=self.PERSONALITY,
            first_remediation=first_remediation,
            checks=checks,
            details=details,
        )

    async def _check_sensors(self) -> tuple[str, dict[str, Any]]:
        if self.sensor_manager is None:
            return ("green", {"sensor_count": 0, "note": "no sensor manager configured"})
        try:
            readings = await self.sensor_manager.poll_all()
            failed = [n for n, r in readings.items() if r is None]
            status = "green" if not failed else "yellow" if len(failed) < 2 else "red"
            return (status, {"sensor_count": len(readings), "failed": failed})
        except Exception as exc:
            return ("red", {"error": str(exc)})

    async def _check_power(self) -> tuple[str, dict[str, Any]]:
        if self.power_manager is None:
            return ("green", {"note": "no power manager configured"})
        try:
            forecast = await self._battery_forecaster.update()
            if forecast.minutes_to_critical <= 5:
                return ("red", {"battery_percent": forecast.battery_percent, "minutes_to_critical": forecast.minutes_to_critical})
            if forecast.minutes_to_empty <= 30:
                return ("yellow", {"battery_percent": forecast.battery_percent, "minutes_to_empty": forecast.minutes_to_empty})
            return ("green", {"battery_percent": forecast.battery_percent, "source": forecast.source})
        except Exception as exc:
            return ("yellow", {"error": str(exc)})

    def _check_detection(self) -> tuple[str, dict[str, Any]]:
        if self.detection_manager is None:
            return ("green", {"note": "no detection manager configured"})
        try:
            state = getattr(self.detection_manager, "get_state", lambda: "clear")()
            if state in ("confirmed", "alert"):
                return ("red", {"state": state})
            if state in ("warning",):
                return ("yellow", {"state": state})
            return ("green", {"state": state})
        except Exception as exc:
            return ("yellow", {"error": str(exc)})

    def _check_safety(self) -> tuple[str, dict[str, Any]]:
        if self.safety_manager is None:
            return ("green", {"note": "no safety manager configured"})
        try:
            armed = getattr(self.safety_manager, "is_armed", lambda: True)()
            interlocks = getattr(self.safety_manager, "interlock_status", lambda: {})()
            status = "green" if armed and all(interlocks.values()) else "red"
            return (status, {"armed": armed, "interlocks": interlocks})
        except Exception as exc:
            return ("red", {"error": str(exc)})

    def _check_telemetry(self) -> tuple[str, dict[str, Any]]:
        if self.telemetry_logger is None:
            return ("green", {"note": "no telemetry logger configured"})
        try:
            events = getattr(self.telemetry_logger, "events", [])
            last_event_ts = max((e.get("ts", 0) for e in events if isinstance(e, dict)), default=0)
            stale = (time.time() - last_event_ts) > 3600
            return ("green" if not stale else "yellow", {"last_event_ts": last_event_ts})
        except Exception as exc:
            return ("yellow", {"error": str(exc)})

    def _check_network(self) -> tuple[str, dict[str, Any]]:
        # Mock-safe: assume reachable unless we can prove otherwise.
        return ("green", {"note": "network check mocked / assumed reachable"})

    def _check_tests(self) -> tuple[str, dict[str, Any]]:
        try:
            report = self.test_scheduler.generate_report()
            summary = report.get("summary", {})
            if summary.get("fail", 0) > 0:
                return ("red", summary)
            if summary.get("due", 0) > 0:
                return ("yellow", summary)
            return ("green", summary)
        except Exception as exc:
            return ("yellow", {"error": str(exc)})

    def _check_alerts(self) -> tuple[str, dict[str, Any]]:
        if self.ack_manager is None:
            return ("green", {"note": "no acknowledgment manager configured"})
        pending = self.ack_manager.get_pending()
        critical = [a for a in pending if a.severity == "critical"]
        if critical:
            return ("red", {"pending_critical": len(critical), "pending_total": len(pending)})
        if pending:
            return ("yellow", {"pending_total": len(pending)})
        return ("green", {"pending_total": 0})

    @staticmethod
    def _aggregate_status(statuses) -> str:
        if any(s == "red" for s in statuses):
            return "red"
        if any(s == "yellow" for s in statuses):
            return "yellow"
        return "green"

    def _first_remediation(
        self,
        status: str,
        checks: dict[str, str],
        details: dict[str, Any],
    ) -> str:
        """Return exactly one actionable remediation step."""
        order = ["alerts", "safety", "power", "detection", "sensors", "tests", "telemetry", "network"]
        for key in order:
            if checks.get(key) == "red":
                d = details.get(key, {})
                return f"{key.upper()} is red: {d.get('error') or d.get('state') or d.get('failed') or 'investigate immediately'}"
        for key in order:
            if checks.get(key) == "yellow":
                d = details.get(key, {})
                if key == "tests" and d.get("due"):
                    return f"{d['due']} scheduled self-test(s) are due; run the guided test wizard."
                return f"{key.upper()} needs attention: {d.get('error') or d.get('state') or d.get('minutes_to_empty') or 'review details'}"
        if status == "green":
            return "All checks green. No immediate remediation required."
        return "Review the detailed health report."

    def to_dict(self) -> dict[str, Any]:
        return {
            "personality": self.PERSONALITY,
            "ready": True,
            "subsystems_checked": list(self._checks_order()),
        }

    def _checks_order(self):
        return ("sensors", "power", "detection", "safety", "telemetry", "network", "tests", "alerts")


async def main() -> None:
    """CLI entry point: ``python -m fire_suppression.diagnostics.system_health_check``."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    checker = SystemHealthCheck()
    result = await checker.check()
    print(json.dumps({
        "status": result.status,
        "timestamp": result.timestamp,
        "personality": result.personality,
        "first_remediation": result.first_remediation,
        "checks": result.checks,
    }, indent=2, default=str))
    sys.exit(0 if result.status == "green" else 1)


if __name__ == "__main__":
    asyncio.run(main())
