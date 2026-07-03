"""Regulatory compliance self-check engine.

# ADD-020 — Regulatory Compliance Self-Check

Checks sensor spacing, suppression coverage, battery backup duration,
and other configurable rules against NFPA/local codes.
Reports compliance gaps before inspection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ComplianceLevel(Enum):
    PASS = "pass"
    WARN = "warning"
    FAIL = "fail"
    INFO = "info"


@dataclass
class ComplianceCheck:
    rule_id: str
    description: str
    level: ComplianceLevel
    message: str
    recommendation: str


# NFPA 72 spacing rules (simplified)
NFPA72_SMOKE_SPACING_M = 9.1  # 30 feet
NFPA72_HEAT_SPACING_M = 15.2  # 50 feet
MIN_BATTERY_HOURS = 24


class ComplianceChecker:
    """Checks system configuration against regulatory requirements.

    Usage::

        checker = ComplianceChecker()
        results = checker.check_all(
            room_size_m2=100,
            sensor_positions={"smoke1": (0, 0), "smoke2": (5, 5)},
            battery_hours=18,
            suppression_zones=["zone_a", "zone_b"],
        )
        for r in results:
            print(f"{r.level.value}: {r.message}")
    """

    def __init__(self, standard: str = "NFPA72") -> None:
        self.standard = standard
        self._rules: list[callable] = [
            self._check_sensor_spacing,
            self._check_battery_backup,
            self._check_suppression_coverage,
            self._check_manual_pull_station,
            self._check_notification_devices,
        ]

    def check_all(self, config: dict) -> list[ComplianceCheck]:
        """Run all compliance checks against the provided configuration."""
        results = []
        for rule in self._rules:
            try:
                check = rule(config)
                if check:
                    results.append(check)
            except Exception as exc:
                logger.warning("Compliance rule %s failed: %s", rule.__name__, exc)
        return results

    def _check_sensor_spacing(self, config: dict) -> ComplianceCheck | None:
        positions = config.get("sensor_positions", {})
        if len(positions) < 2:
            return ComplianceCheck(
                "SENSOR-001", "Smoke detector spacing",
                ComplianceLevel.FAIL,
                f"Only {len(positions)} smoke detectors configured (need >=2 for redundancy)",
                "Add at least one more smoke detector per {NFPA72_SMOKE_SPACING_M}m spacing",
            )

        # Check max distance between any two detectors
        max_dist = 0.0
        pos_list = list(positions.values())
        for i, p1 in enumerate(pos_list):
            for p2 in pos_list[i + 1:]:
                import math
                dist = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
                max_dist = max(max_dist, dist)

        if max_dist > NFPA72_SMOKE_SPACING_M:
            return ComplianceCheck(
                "SENSOR-002", "Smoke detector spacing",
                ComplianceLevel.WARN,
                f"Maximum detector spacing {max_dist:.1f}m exceeds NFPA 72 limit of {NFPA72_SMOKE_SPACING_M}m",
                "Add intermediate detectors or reposition existing ones",
            )
        return ComplianceCheck(
            "SENSOR-002", "Smoke detector spacing",
            ComplianceLevel.PASS,
            f"Detector spacing {max_dist:.1f}m within {NFPA72_SMOKE_SPACING_M}m limit",
            "",
        )

    def _check_battery_backup(self, config: dict) -> ComplianceCheck | None:
        hours = config.get("battery_backup_hours", 0)
        if hours < MIN_BATTERY_HOURS:
            return ComplianceCheck(
                "POWER-001", "Battery backup duration",
                ComplianceLevel.FAIL,
                f"Battery backup {hours}h is below NFPA 72 minimum of {MIN_BATTERY_HOURS}h",
                f"Upgrade to UPS with at least {MIN_BATTERY_HOURS}h capacity",
            )
        return ComplianceCheck(
            "POWER-001", "Battery backup duration",
            ComplianceLevel.PASS,
            f"Battery backup {hours}h meets {MIN_BATTERY_HOURS}h requirement",
            "",
        )

    def _check_suppression_coverage(self, config: dict) -> ComplianceCheck | None:
        zones = config.get("suppression_zones", [])
        room_size = config.get("room_size_m2", 0)
        if room_size > 0 and len(zones) == 0:
            return ComplianceCheck(
                "SUPP-001", "Suppression system coverage",
                ComplianceLevel.FAIL,
                "No suppression zones configured for monitored area",
                "Add at least one suppression zone with sprinkler or mist system",
            )
        if room_size > 500 and len(zones) < 2:
            return ComplianceCheck(
                "SUPP-002", "Suppression system coverage",
                ComplianceLevel.WARN,
                f"Large area ({room_size}m²) may need >1 suppression zone",
                "Consider dividing into multiple suppression zones",
            )
        return ComplianceCheck(
            "SUPP-002", "Suppression system coverage",
            ComplianceLevel.PASS,
            f"{len(zones)} suppression zones configured",
            "",
        )

    def _check_manual_pull_station(self, config: dict) -> ComplianceCheck | None:
        has_pull = config.get("has_manual_pull_station", False)
        if not has_pull:
            return ComplianceCheck(
                "SAFETY-001", "Manual pull station",
                ComplianceLevel.WARN,
                "No manual pull station detected in configuration",
                "Install manual pull station near exits per NFPA 72",
            )
        return ComplianceCheck(
            "SAFETY-001", "Manual pull station",
            ComplianceLevel.PASS,
            "Manual pull station configured",
            "",
        )

    def _check_notification_devices(self, config: dict) -> ComplianceCheck | None:
        devices = config.get("notification_devices", [])
        required = ["audible", "visual"]
        missing = [d for d in required if d not in devices]
        if missing:
            return ComplianceCheck(
                "ALERT-001", "Notification appliances",
                ComplianceLevel.WARN,
                f"Missing notification devices: {', '.join(missing)}",
                f"Add {', '.join(missing)} notification devices per NFPA 72",
            )
        return ComplianceCheck(
            "ALERT-001", "Notification appliances",
            ComplianceLevel.PASS,
            f"All required notification devices present: {', '.join(devices)}",
            "",
        )

    def generate_compliance_report(self, checks: list[ComplianceCheck]) -> dict:
        """Generate a summary compliance report."""
        passed = len([c for c in checks if c.level == ComplianceLevel.PASS])
        warnings = len([c for c in checks if c.level == ComplianceLevel.WARN])
        failed = len([c for c in checks if c.level == ComplianceLevel.FAIL])
        return {
            "standard": self.standard,
            "total_checks": len(checks),
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "compliant": failed == 0,
            "checks": [
                {
                    "rule_id": c.rule_id,
                    "description": c.description,
                    "level": c.level.value,
                    "message": c.message,
                    "recommendation": c.recommendation,
                }
                for c in checks
            ],
        }
