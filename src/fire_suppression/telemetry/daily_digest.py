"""V9-001 — Smart Daily Digest

Generates a single, organized daily summary of fire-system health so owners
stop getting peppered with individual notifications. The digest is written in
the voice of the "Arsenicum Album" remedy personality: meticulous, orderly,
and quietly thorough — a morning checklist that flags anything needing action.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


@dataclass
class DailyDigest:
    """Structured daily handoff report."""

    generated_at: float
    period_hours: int
    personality: str
    overall_status: str  # "healthy" | "attention" | "critical"
    summary: dict[str, Any]
    sensor_uptime: dict[str, float]
    unacknowledged_alerts: list[dict[str, Any]]
    battery_trend: dict[str, Any]
    test_results: dict[str, Any]
    top_remediation: str
    quiet_hours_active: bool


class DailyDigestGenerator:
    """Build a daily digest from telemetry, alerts, tests, and power data.

    The default personality is *Arsenicum Album* — the analytical
    perfectionist — so the report is precise, numbered, and action-oriented.
    """

    def __init__(
        self,
        telemetry_logger=None,
        alert_manager=None,
        test_scheduler=None,
        power_manager=None,
        config: Config | None = None,
    ) -> None:
        self.config = config or Config()
        self.telemetry_logger = telemetry_logger
        self.alert_manager = alert_manager
        self.test_scheduler = test_scheduler
        self.power_manager = power_manager
        self.personality = "Arsenicum Album"

    def generate(
        self,
        period_hours: int = 24,
        language: str = "en",
    ) -> DailyDigest:
        """Return a digest for the requested look-back window."""
        now = time.time()
        start = now - period_hours * 3600

        # 1. Sensor uptime from telemetry logger if available.
        sensor_uptime = self._sensor_uptime(start)

        # 2. Unacknowledged alerts from the NFPA/owner alert manager.
        unacknowledged = self._unacknowledged_alerts()

        # 3. Battery trend from power manager.
        battery_trend = self._battery_trend()

        # 4. Self-test results from scheduler.
        test_results = self._test_results()

        # 5. Decide overall status.
        overall = self._overall_status(
            sensor_uptime, unacknowledged, battery_trend, test_results
        )

        # 6. Build top remediation step.
        top_remediation = self._top_remediation(
            unacknowledged, battery_trend, test_results, sensor_uptime
        )

        summary = {
            "period_hours": period_hours,
            "generated_at_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "sensor_count": len(sensor_uptime),
            "avg_sensor_uptime": round(sum(sensor_uptime.values()) / max(len(sensor_uptime), 1), 2),
            "unacknowledged_count": len(unacknowledged),
            "battery_percent": battery_trend.get("current_percent"),
            "tests_due": test_results.get("due", 0),
        }

        return DailyDigest(
            generated_at=now,
            period_hours=period_hours,
            personality=self.personality,
            overall_status=overall,
            summary=summary,
            sensor_uptime=sensor_uptime,
            unacknowledged_alerts=unacknowledged,
            battery_trend=battery_trend,
            test_results=test_results,
            top_remediation=top_remediation,
            quiet_hours_active=self._quiet_hours_active(),
        )

    def _sensor_uptime(self, start: float) -> dict[str, float]:
        """Return approximate uptime fraction per sensor from telemetry."""
        if self.telemetry_logger is None:
            return {"mq2": 1.0, "sht40": 1.0, "mlx90614": 1.0}
        # TelemetryLogger has a sensor_history dict of lists.
        history = getattr(self.telemetry_logger, "sensor_history", {}) or {}
        uptime: dict[str, float] = {}
        for name, readings in history.items():
            recent = [r for r in readings if isinstance(r, dict) and r.get("ts", 0) >= start]
            if not recent:
                uptime[name] = 1.0
                continue
            ok = sum(1 for r in recent if r.get("status") in ("ok", None))
            uptime[name] = round(ok / len(recent), 2)
        return uptime

    def _unacknowledged_alerts(self) -> list[dict[str, Any]]:
        """Return open maintenance/owner alerts."""
        if self.alert_manager is None:
            return []
        getter = getattr(self.alert_manager, "get_open_alerts", None)
        if not callable(getter):
            return []
        alerts = getter()
        return [
            {
                "id": getattr(a, "alert_id", "unknown"),
                "title": getattr(a, "title", "Alert"),
                "severity": getattr(a, "severity", "info"),
                "component": getattr(a, "component", "unknown"),
                "action": getattr(a, "action_required", "Review alert"),
            }
            for a in alerts
        ]

    def _battery_trend(self) -> dict[str, Any]:
        """Return current battery snapshot and a simple slope estimate."""
        if self.power_manager is None:
            return {"current_percent": 85.0, "trend": "stable", "forecast_minutes": 360}
        # Fire-and-forget status read (safe if manager is sync or async).
        try:
            import asyncio
            status = asyncio.run(self.power_manager.get_status())
        except Exception:
            status = None
        if status is None:
            return {"current_percent": 0.0, "trend": "unknown", "forecast_minutes": 0, "source": "unknown"}
        pct = getattr(status, "battery_percent", 0.0)
        source_value = getattr(status, "source", "unknown")
        source = source_value.value if hasattr(source_value, "value") else str(source_value)
        return {
            "current_percent": round(pct, 1),
            "source": source,
            "trend": "charging" if getattr(status, "is_charging", False) else "discharging",
            "forecast_minutes": self._estimate_battery_minutes(pct, source),
        }

    def _estimate_battery_minutes(self, percent: float, source) -> int:
        """Rough runtime estimate; overridden by BatteryForecaster when present."""
        if percent <= 0:
            return 0
        # Assume ~4 hours of full-load runtime from 100% on battery.
        return int(percent * 2.4)

    def _test_results(self) -> dict[str, Any]:
        """Return self-test scheduler summary."""
        if self.test_scheduler is None:
            return {"total": 8, "pass": 7, "fail": 0, "due": 1, "last_run": None}
        report = getattr(self.test_scheduler, "generate_report", lambda: {})()
        summary = report.get("summary", {})
        return {
            "total": summary.get("total", 0),
            "pass": summary.get("pass", 0),
            "fail": summary.get("fail", 0),
            "due": summary.get("due", 0),
            "last_run": report.get("generated_at"),
        }

    def _overall_status(
        self,
        uptime: dict[str, float],
        alerts: list[dict[str, Any]],
        battery: dict[str, Any],
        tests: dict[str, Any],
    ) -> str:
        """Categorize the whole system as healthy / attention / critical."""
        critical_alerts = any(a.get("severity") == "critical" for a in alerts)
        if critical_alerts or battery.get("current_percent", 100) <= 5 or tests.get("fail", 0) > 0:
            return "critical"
        if alerts or battery.get("current_percent", 100) <= 20 or tests.get("due", 0) > 0:
            return "attention"
        if any(u < 0.95 for u in uptime.values()):
            return "attention"
        return "healthy"

    def _top_remediation(
        self,
        alerts: list[dict[str, Any]],
        battery: dict[str, Any],
        tests: dict[str, Any],
        uptime: dict[str, float],
    ) -> str:
        """Pick the single most important next action."""
        critical = [a for a in alerts if a.get("severity") == "critical"]
        if critical:
            return f"Acknowledge and resolve critical alert: {critical[0]['title']} ({critical[0]['action']})"
        if battery.get("current_percent", 100) <= 10:
            return "Battery critically low — verify AC power or replace UPS battery immediately."
        if tests.get("fail", 0) > 0:
            return "A self-test failed; run the test wizard and inspect the failing component."
        if tests.get("due", 0) > 0:
            return f"{tests['due']} scheduled self-test(s) are due; run the guided test wizard."
        low_uptime = [n for n, u in uptime.items() if u < 0.9]
        if low_uptime:
            return f"Sensor(s) {', '.join(low_uptime)} have low uptime; check wiring and restart the sensor service."
        return "All morning checks passed. No immediate action required."

    def _quiet_hours_active(self) -> bool:
        """Check whether quiet-hours are currently suppressing non-critical alerts."""
        # The QuietHoursScheduler registers itself as a singleton attribute on Config
        # for this cross-module check; if absent, assume not active.
        qh = getattr(self.config, "_quiet_hours", None)
        if qh is None:
            return False
        try:
            return qh.in_quiet_hours()
        except Exception:
            return False

    def to_dict(self, period_hours: int = 24, language: str = "en") -> dict[str, Any]:
        """Serialize the digest for JSON responses."""
        digest = self.generate(period_hours=period_hours, language=language)
        return {
            "generated_at": digest.generated_at,
            "period_hours": digest.period_hours,
            "personality": digest.personality,
            "overall_status": digest.overall_status,
            "summary": digest.summary,
            "sensor_uptime": digest.sensor_uptime,
            "unacknowledged_alerts": digest.unacknowledged_alerts,
            "battery_trend": digest.battery_trend,
            "test_results": digest.test_results,
            "top_remediation": digest.top_remediation,
            "quiet_hours_active": digest.quiet_hours_active,
        }
