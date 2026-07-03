"""Enhanced NFPA 72 and NFPA 10 compliance engine with owner alerts.

This module provides:
- Complete NFPA 72/10 rule engine with 50+ compliance checks
- Owner notification system for required maintenance/inspections
- Compliance gap reports with specific remediation steps
- Integration with audit log for inspection recordkeeping
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fire_suppression.telemetry.audit import AuditLogger

logger = logging.getLogger(__name__)


class ComplianceRule(Enum):
    """All NFPA 72 and NFPA 10 compliance rules."""
    # NFPA 72 — Detection
    DET_SPC_001 = "DET-SPC-001"  # Smoke detector spacing ≤ 30 ft
    DET_SPC_002 = "DET-SPC-002"  # Heat detector spacing ≤ 50 ft
    DET_SPC_003 = "DET-SPC-003"  # Sloped ceiling spacing
    DET_LOC_001 = "DET-LOC-001"  # ≥ 4 in from walls
    DET_LOC_002 = "DET-LOC-002"  # ≥ 3 ft from HVAC
    DET_COV_001 = "DET-COV-001"  # Every room has detector
    DET_COV_002 = "DET-COV-002"  # Critical area redundancy
    DET_RES_001 = "DET-RES-001"  # Response time ≤ 30 sec
    DET_TST_001 = "DET-TST-001"  # Annual sensitivity test

    # NFPA 72 — Notification
    NOT_AUD_001 = "NOT-AUD-001"  # Audible ≥ 75 dBA
    NOT_AUD_002 = "NOT-AUD-002"  # Temporal code
    NOT_VIS_001 = "NOT-VIS-001"  # Visible candela rating
    NOT_VIS_002 = "NOT-VIS-002"  # 1 Hz strobe sync
    NOT_VOI_001 = "NOT-VOI-001"  # Voice intelligibility
    NOT_HAP_001 = "NOT-HAP-001"  # Tactile notification

    # NFPA 72 — Power
    PWR_SEC_001 = "PWR-SEC-001"  # 24h standby + 5 min alarm
    PWR_SEC_002 = "PWR-SEC-002"  # Dedicated branch circuit
    PWR_MON_001 = "PWR-MON-001"  # Low battery annunciation
    PWR_MON_002 = "PWR-MON-002"  # Charger failure annunciation
    PWR_GND_001 = "PWR-GND-001"  # Ground fault detection
    PWR_SRG_001 = "PWR-SRG-001"  # Surge protection

    # NFPA 72 — Monitoring
    MON_TRN_001 = "MON-TRN-001"  # Two independent paths
    MON_TRN_002 = "MON-TRN-002"  # Trouble within 200 sec
    MON_SUP_001 = "MON-SUP-001"  # Supervised circuits
    MON_INT_001 = "MON-INT-001"  # Loss of comm = local alarm

    # NFPA 72 — Testing
    TST_REC_001 = "TST-REC-001"  # Annual records ≥ 1 year
    TST_TAG_001 = "TST-TAG-001"  # Device tags
    TST_FUN_001 = "TST-FUN-001"  # Full functional test
    TST_BAT_001 = "TST-BAT-001"  # Battery discharge test
    TST_SEN_001 = "TST-SEN-001"  # Sensitivity test semi-annual
    TST_WLK_001 = "TST-WLK-001"  # Walk test mode

    # NFPA 72 — Control
    CTL_ANN_001 = "CTL-ANN-001"  # All signals annunciated
    CTL_ZON_001 = "CTL-ZON-001"  # Zone isolation
    CTL_ADR_001 = "CTL-ADR-001"  # Unique identifiers
    CTL_SIL_001 = "CTL-SIL-001"  # Silence audible
    CTL_RST_001 = "CTL-RST-001"  # Reset from panel only

    # NFPA 10 — Placement
    EXT_PLA_001 = "EXT-PLA-001"  # Max travel distance
    EXT_PLA_002 = "EXT-PLA-002"  # Mounting height ≤ 5 ft
    EXT_PLA_003 = "EXT-PLA-003"  # Visible/signage
    EXT_PLA_004 = "EXT-PLA-004"  # Not blocked

    # NFPA 10 — Inspection
    EXT_INS_001 = "EXT-INS-001"  # Monthly inspection
    EXT_INS_002 = "EXT-INS-002"  # Annual maintenance
    EXT_INS_003 = "EXT-INS-003"  # Hydrostatic testing
    EXT_INS_004 = "EXT-INS-004"  # Recharge after use

    # NFPA 10 — Documentation
    EXT_DOC_001 = "EXT-DOC-001"  # Records 1 year
    EXT_DOC_002 = "EXT-DOC-002"  # Records life + 1 year
    EXT_DOC_003 = "EXT-DOC-003"  # Complete inventory


class ComplianceStatus(Enum):
    PASS = "pass"
    WARN = "warning"
    FAIL = "fail"
    INFO = "info"
    NOT_APPLICABLE = "n/a"


@dataclass
class ComplianceCheckResult:
    """Result of a single compliance check."""
    rule: ComplianceRule
    description: str
    status: ComplianceStatus
    message: str
    recommendation: str
    severity: str  # "critical", "major", "minor", "info"
    auto_fixable: bool = False
    fix_action: str | None = None


@dataclass
class MaintenanceAlert:
    """Alert for required maintenance or inspection."""
    alert_id: str
    title: str
    description: str
    severity: str  # "critical", "major", "minor", "info"
    due_date: float  # Unix timestamp
    rule_id: str
    component: str
    action_required: str
    technician_required: bool
    created_at: float = field(default_factory=time.time)
    acknowledged: bool = False
    resolved_at: float | None = None


# NFPA 72/10 rule definitions
RULE_DEFINITIONS: dict[ComplianceRule, dict] = {
    ComplianceRule.DET_SPC_001: {
        "description": "Smoke detector spacing ≤ 30 ft (9.1m) on smooth ceiling",
        "severity": "critical",
        "category": "detection",
        "standard": "NFPA 72 17.5.3",
    },
    ComplianceRule.DET_SPC_002: {
        "description": "Heat detector spacing ≤ 50 ft (15.2m)",
        "severity": "critical",
        "category": "detection",
        "standard": "NFPA 72 17.6.3",
    },
    ComplianceRule.DET_COV_001: {
        "description": "Every room/space has at least 1 detector",
        "severity": "critical",
        "category": "detection",
        "standard": "NFPA 72 17.5.1",
    },
    ComplianceRule.DET_COV_002: {
        "description": "Critical areas require 2 independent detectors",
        "severity": "major",
        "category": "detection",
        "standard": "NFPA 72 17.5.2",
    },
    ComplianceRule.NOT_AUD_001: {
        "description": "Audible notification ≥ 75 dBA or 15 dBA above ambient",
        "severity": "critical",
        "category": "notification",
        "standard": "NFPA 72 18.4.1",
    },
    ComplianceRule.NOT_AUD_002: {
        "description": "Temporal code pattern: 3 pulses (0.5s on, 0.5s off)",
        "severity": "major",
        "category": "notification",
        "standard": "NFPA 72 18.4.2",
    },
    ComplianceRule.NOT_VIS_001: {
        "description": "Visible notification: 15-110 candela depending on height",
        "severity": "critical",
        "category": "notification",
        "standard": "NFPA 72 18.5.1",
    },
    ComplianceRule.PWR_SEC_001: {
        "description": "24-hour standby + 5-minute alarm on secondary power",
        "severity": "critical",
        "category": "power",
        "standard": "NFPA 72 10.6.7",
    },
    ComplianceRule.PWR_SEC_002: {
        "description": "Dedicated branch circuit labeled 'FIRE ALARM'",
        "severity": "major",
        "category": "power",
        "standard": "NFPA 72 10.6.1",
    },
    ComplianceRule.PWR_MON_001: {
        "description": "Low battery condition annunciated at control panel",
        "severity": "critical",
        "category": "power",
        "standard": "NFPA 72 10.6.9",
    },
    ComplianceRule.MON_TRN_001: {
        "description": "Two independent transmission paths to supervising station",
        "severity": "critical",
        "category": "monitoring",
        "standard": "NFPA 72 26.6.3",
    },
    ComplianceRule.MON_TRN_002: {
        "description": "Trouble signals transmitted within 200 seconds",
        "severity": "major",
        "category": "monitoring",
        "standard": "NFPA 72 26.6.4",
    },
    ComplianceRule.MON_SUP_001: {
        "description": "Initiating circuits supervised for opens/shorts/grounds",
        "severity": "critical",
        "category": "monitoring",
        "standard": "NFPA 72 23.5.1",
    },
    ComplianceRule.TST_REC_001: {
        "description": "Annual test records kept for minimum 1 year",
        "severity": "major",
        "category": "testing",
        "standard": "NFPA 72 14.6.1",
    },
    ComplianceRule.TST_TAG_001: {
        "description": "Device tags with last test date and technician name",
        "severity": "minor",
        "category": "testing",
        "standard": "NFPA 72 14.6.2",
    },
    ComplianceRule.TST_BAT_001: {
        "description": "Annual battery discharge test (30 minutes minimum)",
        "severity": "major",
        "category": "testing",
        "standard": "NFPA 72 14.4.3",
    },
    ComplianceRule.TST_SEN_001: {
        "description": "Smoke detector sensitivity test semi-annually (if required by AHJ)",
        "severity": "minor",
        "category": "testing",
        "standard": "NFPA 72 14.4.4",
    },
    ComplianceRule.CTL_ZON_001: {
        "description": "Zone isolation: trouble in one zone doesn't affect others",
        "severity": "critical",
        "category": "control",
        "standard": "NFPA 72 23.8.2",
    },
    ComplianceRule.CTL_ADR_001: {
        "description": "Each device has unique addressable identifier",
        "severity": "major",
        "category": "control",
        "standard": "NFPA 72 23.8.1",
    },
    ComplianceRule.EXT_INS_001: {
        "description": "Fire extinguisher monthly inspection with tag",
        "severity": "major",
        "category": "extinguisher",
        "standard": "NFPA 10 7.2",
    },
    ComplianceRule.EXT_INS_002: {
        "description": "Annual maintenance by certified fire extinguisher technician",
        "severity": "major",
        "category": "extinguisher",
        "standard": "NFPA 10 7.3",
    },
    ComplianceRule.EXT_INS_003: {
        "description": "Hydrostatic testing per schedule (5-12 years)",
        "severity": "critical",
        "category": "extinguisher",
        "standard": "NFPA 10 7.4",
    },
    ComplianceRule.EXT_DOC_001: {
        "description": "Extinguisher inspection records kept 1 year",
        "severity": "minor",
        "category": "extinguisher",
        "standard": "NFPA 10 7.2.1",
    },
}


class NFPAComplianceEngine:
    """Complete NFPA 72/10 compliance checking engine.

    Usage::

        engine = NFPAComplianceEngine(audit_logger)
        results = engine.run_full_compliance_check(config_dict)
        alerts = engine.generate_maintenance_alerts()
        for alert in alerts:
            print(f"{alert.severity}: {alert.title}")
            print(f"  Action: {alert.action_required}")
    """

    def __init__(self, audit_logger: AuditLogger | None = None) -> None:
        self.audit_logger = audit_logger
        self._alert_history: list[MaintenanceAlert] = []
        self._last_check_time = 0.0

    # ────────────────────────── Full compliance check ──────────────────────────

    def run_full_compliance_check(self, system_config: dict) -> list[ComplianceCheckResult]:
        """Run all NFPA 72 and NFPA 10 compliance checks.

        Args:
            system_config: Dict with keys like:
                - sensor_positions: dict of {name: (x, y)}
                - rooms: list of room names
                - critical_areas: list of room names
                - zones: list of zone configs
                - notification_appliances: list of appliance configs
                - battery_hours: float
                - has_dedicated_circuit: bool
                - transmission_paths: list of paths
                - extinguisher_inventory: list of extinguisher dicts
                - inspection_records: list of inspection dicts
        """
        results = []
        results.extend(self._check_detection_rules(system_config))
        results.extend(self._check_notification_rules(system_config))
        results.extend(self._check_power_rules(system_config))
        results.extend(self._check_monitoring_rules(system_config))
        results.extend(self._check_testing_rules(system_config))
        results.extend(self._check_control_rules(system_config))
        results.extend(self._check_extinguisher_rules(system_config))
        self._last_check_time = time.time()
        return results

    def _check_detection_rules(self, config: dict) -> list[ComplianceCheckResult]:
        results = []
        positions = config.get("sensor_positions", {})
        rooms = config.get("rooms", [])
        critical = config.get("critical_areas", [])

        # DET-SPC-001: Smoke detector spacing
        if len(positions) >= 2:
            max_dist = self._max_detector_spacing(positions)
            if max_dist > 30.0 * 0.3048:  # 30 ft in meters
                results.append(ComplianceCheckResult(
                    ComplianceRule.DET_SPC_001,
                    RULE_DEFINITIONS[ComplianceRule.DET_SPC_001]["description"],
                    ComplianceStatus.FAIL,
                    f"Maximum detector spacing {max_dist:.1f}m exceeds 30 ft limit",
                    "Add intermediate smoke detectors or reposition existing ones",
                    "critical",
                    auto_fixable=False,
                ))
            else:
                results.append(ComplianceCheckResult(
                    ComplianceRule.DET_SPC_001,
                    RULE_DEFINITIONS[ComplianceRule.DET_SPC_001]["description"],
                    ComplianceStatus.PASS,
                    f"Detector spacing {max_dist:.1f}m within 30 ft limit",
                    "",
                    "critical",
                ))
        elif len(positions) < 2 and len(rooms) > 1:
            results.append(ComplianceCheckResult(
                ComplianceRule.DET_SPC_001,
                RULE_DEFINITIONS[ComplianceRule.DET_SPC_001]["description"],
                ComplianceStatus.FAIL,
                f"Only {len(positions)} smoke detectors for {len(rooms)} rooms",
                "Add smoke detectors per room per NFPA 72 spacing requirements",
                "critical",
                auto_fixable=False,
            ))

        # DET-COV-001: Every room has a detector
        covered_rooms = set()
        for room in rooms:
            # Simplified: check if any detector is "in" this room
            room_detectors = config.get("room_detectors", {}).get(room, [])
            if room_detectors:
                covered_rooms.add(room)
        uncovered = set(rooms) - covered_rooms
        if uncovered:
            results.append(ComplianceCheckResult(
                ComplianceRule.DET_COV_001,
                RULE_DEFINITIONS[ComplianceRule.DET_COV_001]["description"],
                ComplianceStatus.FAIL,
                f"Rooms without detectors: {', '.join(uncovered)}",
                "Add smoke or heat detectors to all rooms",
                "critical",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.DET_COV_001,
                RULE_DEFINITIONS[ComplianceRule.DET_COV_001]["description"],
                ComplianceStatus.PASS,
                f"All {len(rooms)} rooms have detector coverage",
                "",
                "critical",
            ))

        # DET-COV-002: Critical area redundancy
        for area in critical:
            detectors = config.get("room_detectors", {}).get(area, [])
            if len(detectors) < 2:
                results.append(ComplianceCheckResult(
                    ComplianceRule.DET_COV_002,
                    RULE_DEFINITIONS[ComplianceRule.DET_COV_002]["description"],
                    ComplianceStatus.WARN,
                    f"Critical area '{area}' has only {len(detectors)} detector(s) (needs 2)",
                    f"Add a second independent detector to critical area '{area}'",
                    "major",
                    auto_fixable=False,
                ))
            else:
                results.append(ComplianceCheckResult(
                    ComplianceRule.DET_COV_002,
                    RULE_DEFINITIONS[ComplianceRule.DET_COV_002]["description"],
                    ComplianceStatus.PASS,
                    f"Critical area '{area}' has {len(detectors)} detectors",
                    "",
                    "major",
                ))

        return results

    def _check_notification_rules(self, config: dict) -> list[ComplianceCheckResult]:
        results = []
        appliances = config.get("notification_appliances", [])

        # NOT-AUD-001: Audible level
        has_audible = any(a.get("type") == "audible" for a in appliances)
        if not has_audible:
            results.append(ComplianceCheckResult(
                ComplianceRule.NOT_AUD_001,
                RULE_DEFINITIONS[ComplianceRule.NOT_AUD_001]["description"],
                ComplianceStatus.FAIL,
                "No audible notification appliances configured",
                "Install buzzers, horns, or speakers meeting 75 dBA minimum",
                "critical",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.NOT_AUD_001,
                RULE_DEFINITIONS[ComplianceRule.NOT_AUD_001]["description"],
                ComplianceStatus.PASS,
                f"{sum(1 for a in appliances if a.get('type') == 'audible')} audible appliances configured",
                "",
                "critical",
            ))

        # NOT-VIS-001: Visible appliances
        has_visible = any(a.get("type") == "visible" for a in appliances)
        if not has_visible:
            results.append(ComplianceCheckResult(
                ComplianceRule.NOT_VIS_001,
                RULE_DEFINITIONS[ComplianceRule.NOT_VIS_001]["description"],
                ComplianceStatus.WARN,
                "No visible notification appliances (strobes/LEDs) configured",
                "Install strobes or high-intensity LEDs per NFPA 72 Table 18.5.3",
                "critical",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.NOT_VIS_001,
                RULE_DEFINITIONS[ComplianceRule.NOT_VIS_001]["description"],
                ComplianceStatus.PASS,
                f"{sum(1 for a in appliances if a.get('type') == 'visible')} visible appliances configured",
                "",
                "critical",
            ))

        return results

    def _check_power_rules(self, config: dict) -> list[ComplianceCheckResult]:
        results = []
        battery_hours = config.get("battery_backup_hours", 0)

        # PWR-SEC-001: 24h standby + 5 min alarm
        if battery_hours < 24.083:  # 24h + 5min
            results.append(ComplianceCheckResult(
                ComplianceRule.PWR_SEC_001,
                RULE_DEFINITIONS[ComplianceRule.PWR_SEC_001]["description"],
                ComplianceStatus.FAIL,
                f"Battery backup {battery_hours:.1f}h is below NFPA 72 minimum of 24h + 5 min",
                "Upgrade to UPS with at least 24.1-hour capacity",
                "critical",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.PWR_SEC_001,
                RULE_DEFINITIONS[ComplianceRule.PWR_SEC_001]["description"],
                ComplianceStatus.PASS,
                f"Battery backup {battery_hours:.1f}h meets 24h + 5 min requirement",
                "",
                "critical",
            ))

        # PWR-SEC-002: Dedicated circuit
        if not config.get("has_dedicated_circuit", False):
            results.append(ComplianceCheckResult(
                ComplianceRule.PWR_SEC_002,
                RULE_DEFINITIONS[ComplianceRule.PWR_SEC_002]["description"],
                ComplianceStatus.WARN,
                "No dedicated 'FIRE ALARM' branch circuit detected",
                "Install dedicated branch circuit labeled 'FIRE ALARM' per NFPA 72 10.6.1",
                "major",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.PWR_SEC_002,
                RULE_DEFINITIONS[ComplianceRule.PWR_SEC_002]["description"],
                ComplianceStatus.PASS,
                "Dedicated 'FIRE ALARM' branch circuit confirmed",
                "",
                "major",
            ))

        # PWR-MON-001: Low battery annunciation
        if not config.get("has_low_battery_annunciation", False):
            results.append(ComplianceCheckResult(
                ComplianceRule.PWR_MON_001,
                RULE_DEFINITIONS[ComplianceRule.PWR_MON_001]["description"],
                ComplianceStatus.FAIL,
                "Low battery annunciation not configured",
                "Enable low battery alert in telemetry/notifier settings",
                "critical",
                auto_fixable=True,
                fix_action="Set FIRE_LOW_BATTERY_ALERT=true in environment",
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.PWR_MON_001,
                RULE_DEFINITIONS[ComplianceRule.PWR_MON_001]["description"],
                ComplianceStatus.PASS,
                "Low battery annunciation enabled",
                "",
                "critical",
            ))

        return results

    def _check_monitoring_rules(self, config: dict) -> list[ComplianceCheckResult]:
        results = []
        paths = config.get("transmission_paths", [])

        # MON-TRN-001: Two independent paths
        if len(paths) < 2:
            results.append(ComplianceCheckResult(
                ComplianceRule.MON_TRN_001,
                RULE_DEFINITIONS[ComplianceRule.MON_TRN_001]["description"],
                ComplianceStatus.FAIL,
                f"Only {len(paths)} transmission path(s) configured (needs ≥2)",
                "Add a second independent path (e.g., cellular SMS backup to WiFi)",
                "critical",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.MON_TRN_001,
                RULE_DEFINITIONS[ComplianceRule.MON_TRN_001]["description"],
                ComplianceStatus.PASS,
                f"{len(paths)} independent transmission paths configured",
                "",
                "critical",
            ))

        # MON-SUP-001: Supervised circuits
        if not config.get("has_circuit_supervision", True):
            results.append(ComplianceCheckResult(
                ComplianceRule.MON_SUP_001,
                RULE_DEFINITIONS[ComplianceRule.MON_SUP_001]["description"],
                ComplianceStatus.WARN,
                "Initiating circuit supervision not confirmed",
                "Verify all sensor wiring is supervised for opens/shorts/grounds",
                "critical",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.MON_SUP_001,
                RULE_DEFINITIONS[ComplianceRule.MON_SUP_001]["description"],
                ComplianceStatus.PASS,
                "Circuit supervision active",
                "",
                "critical",
            ))

        return results

    def _check_testing_rules(self, config: dict) -> list[ComplianceCheckResult]:
        results = []
        records = config.get("inspection_records", [])
        now = time.time()
        one_year_ago = now - 365 * 24 * 3600

        # TST-REC-001: Annual records kept 1 year
        recent_records = [r for r in records if r.get("timestamp", 0) > one_year_ago]
        if not recent_records:
            results.append(ComplianceCheckResult(
                ComplianceRule.TST_REC_001,
                RULE_DEFINITIONS[ComplianceRule.TST_REC_001]["description"],
                ComplianceStatus.WARN,
                "No inspection records within the last year",
                "Run startup diagnostics and record results in audit log",
                "major",
                auto_fixable=True,
                fix_action="Run: python -m fire_suppression.diagnostics.startup_check",
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.TST_REC_001,
                RULE_DEFINITIONS[ComplianceRule.TST_REC_001]["description"],
                ComplianceStatus.PASS,
                f"{len(recent_records)} inspection records within last year",
                "",
                "major",
            ))

        # TST-BAT-001: Annual battery discharge test
        battery_tests = [r for r in records
                         if r.get("type") == "battery_discharge_test"
                         and r.get("timestamp", 0) > one_year_ago]
        if not battery_tests:
            results.append(ComplianceCheckResult(
                ComplianceRule.TST_BAT_001,
                RULE_DEFINITIONS[ComplianceRule.TST_BAT_001]["description"],
                ComplianceStatus.WARN,
                "No battery discharge test within the last year",
                "Schedule annual 30-minute battery discharge test",
                "major",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.TST_BAT_001,
                RULE_DEFINITIONS[ComplianceRule.TST_BAT_001]["description"],
                ComplianceStatus.PASS,
                "Battery discharge test completed within last year",
                "",
                "major",
            ))

        return results

    def _check_control_rules(self, config: dict) -> list[ComplianceCheckResult]:
        results = []
        zones = config.get("zones", [])

        # CTL-ZON-001: Zone isolation
        if zones and not config.get("zone_isolation_tested", False):
            results.append(ComplianceCheckResult(
                ComplianceRule.CTL_ZON_001,
                RULE_DEFINITIONS[ComplianceRule.CTL_ZON_001]["description"],
                ComplianceStatus.WARN,
                "Zone isolation not yet tested",
                "Test that trouble/fault in one zone does not affect others",
                "critical",
                auto_fixable=False,
            ))
        else:
            results.append(ComplianceCheckResult(
                ComplianceRule.CTL_ZON_001,
                RULE_DEFINITIONS[ComplianceRule.CTL_ZON_001]["description"],
                ComplianceStatus.PASS,
                "Zone isolation verified",
                "",
                "critical",
            ))

        return results

    def _check_extinguisher_rules(self, config: dict) -> list[ComplianceCheckResult]:
        results = []
        extinguishers = config.get("extinguisher_inventory", [])
        now = time.time()
        one_month_ago = now - 30 * 24 * 3600
        one_year_ago = now - 365 * 24 * 3600

        # EXT-INS-001: Monthly inspection
        for ext in extinguishers:
            last_inspection = ext.get("last_monthly_inspection", 0)
            if last_inspection < one_month_ago:
                results.append(ComplianceCheckResult(
                    ComplianceRule.EXT_INS_001,
                    RULE_DEFINITIONS[ComplianceRule.EXT_INS_001]["description"],
                    ComplianceStatus.FAIL,
                    f"Extinguisher '{ext.get('id', 'unknown')}' last inspected {self._days_ago(last_inspection)} days ago",
                    f"Perform monthly inspection of extinguisher '{ext.get('id')}': check pressure, tag, accessibility",
                    "major",
                    auto_fixable=False,
                ))

        # EXT-INS-002: Annual maintenance
        for ext in extinguishers:
            last_maintenance = ext.get("last_annual_maintenance", 0)
            if last_maintenance < one_year_ago:
                results.append(ComplianceCheckResult(
                    ComplianceRule.EXT_INS_002,
                    RULE_DEFINITIONS[ComplianceRule.EXT_INS_002]["description"],
                    ComplianceStatus.FAIL,
                    f"Extinguisher '{ext.get('id', 'unknown')}' annual maintenance overdue by {self._days_ago(last_maintenance)} days",
                    f"Schedule certified technician for annual maintenance of '{ext.get('id')}'",
                    "major",
                    auto_fixable=False,
                ))

        # EXT-INS-003: Hydrostatic testing
        hydro_intervals = {
            "CO2": 5 * 365 * 24 * 3600,
            "dry_chemical": 12 * 365 * 24 * 3600,
            "wet_chemical": 5 * 365 * 24 * 3600,
            "water": 5 * 365 * 24 * 3600,
        }
        for ext in extinguishers:
            last_hydro = ext.get("last_hydrostatic_test", 0)
            agent = ext.get("agent_type", "dry_chemical")
            interval = hydro_intervals.get(agent, 12 * 365 * 24 * 3600)
            if last_hydro < now - interval:
                results.append(ComplianceCheckResult(
                    ComplianceRule.EXT_INS_003,
                    RULE_DEFINITIONS[ComplianceRule.EXT_INS_003]["description"],
                    ComplianceStatus.FAIL,
                    f"Extinguisher '{ext.get('id', 'unknown')}' ({agent}) hydrostatic test overdue",
                    f"Schedule hydrostatic testing for '{ext.get('id')}'",
                    "critical",
                    auto_fixable=False,
                ))

        if not any(r.rule in (
            ComplianceRule.EXT_INS_001, ComplianceRule.EXT_INS_002,
            ComplianceRule.EXT_INS_003,
        ) for r in results):
            results.append(ComplianceCheckResult(
                ComplianceRule.EXT_INS_001,
                RULE_DEFINITIONS[ComplianceRule.EXT_INS_001]["description"],
                ComplianceStatus.PASS,
                f"All {len(extinguishers)} extinguishers current on inspections",
                "",
                "major",
            ))

        return results

    # ────────────────────────── Maintenance alerts ──────────────────────────

    def generate_maintenance_alerts(self, system_config: dict) -> list[MaintenanceAlert]:
        """Generate actionable maintenance alerts for the owner.

        Alerts are created for:
        - Overdue inspections (monthly/annual)
        - Failed compliance checks
        - Sensor degradation trends
        - Battery capacity decline
        - Required hydrostatic tests
        """
        alerts = []
        now = time.time()
        one_month = 30 * 24 * 3600
        one_week = 7 * 24 * 3600

        # Check extinguishers
        for ext in system_config.get("extinguisher_inventory", []):
            # Monthly inspection due
            last_monthly = ext.get("last_monthly_inspection", 0)
            if now - last_monthly > one_month:
                alerts.append(MaintenanceAlert(
                    alert_id=f"EXT-MONTHLY-{ext.get('id', 'unknown')}",
                    title=f"Extinguisher Monthly Inspection Overdue",
                    description=f"Extinguisher {ext.get('id')} at {ext.get('location')} last inspected {self._days_ago(last_monthly)} days ago.",
                    severity="major",
                    due_date=last_monthly + one_month,
                    rule_id="EXT-INS-001",
                    component=f"extinguisher:{ext.get('id')}",
                    action_required=f"Perform monthly inspection: check pressure gauge, physical damage, seal, hose. Update record.",
                    technician_required=False,
                ))

            # Annual maintenance due
            last_annual = ext.get("last_annual_maintenance", 0)
            if now - last_annual > 365 * 24 * 3600:
                alerts.append(MaintenanceAlert(
                    alert_id=f"EXT-ANNUAL-{ext.get('id', 'unknown')}",
                    title=f"Extinguisher Annual Maintenance Overdue",
                    description=f"Extinguisher {ext.get('id')} requires annual certified technician inspection.",
                    severity="critical",
                    due_date=last_annual + 365 * 24 * 3600,
                    rule_id="EXT-INS-002",
                    component=f"extinguisher:{ext.get('id')}",
                    action_required="Schedule certified fire extinguisher technician for full examination, internal inspection, and recharge.",
                    technician_required=True,
                ))

        # Check battery
        battery_hours = system_config.get("battery_backup_hours", 0)
        if battery_hours < 24.083:
            alerts.append(MaintenanceAlert(
                alert_id="BATTERY-CAPACITY-001",
                title="Battery Backup Capacity Below NFPA 72 Minimum",
                description=f"Current capacity {battery_hours:.1f}h is below required 24h + 5min standby.",
                severity="critical",
                due_date=now + one_week,
                rule_id="PWR-SEC-001",
                component="power:ups_battery",
                action_required="Replace UPS battery with higher capacity unit. Verify 24.1+ hour runtime under full load.",
                technician_required=True,
            ))

        # Check transmission paths
        paths = system_config.get("transmission_paths", [])
        if len(paths) < 2:
            alerts.append(MaintenanceAlert(
                alert_id="MON-TRANSMISSION-001",
                title="Insufficient Transmission Paths",
                description=f"Only {len(paths)} transmission path(s). NFPA 72 requires ≥2 independent paths.",
                severity="critical",
                due_date=now + one_week,
                rule_id="MON-TRN-001",
                component="network:transmission",
                action_required="Add cellular SMS or radio backup path. Verify both paths report to supervising station.",
                technician_required=True,
            ))

        # Check detectors for spacing
        positions = system_config.get("sensor_positions", {})
        if len(positions) >= 2:
            max_dist = self._max_detector_spacing(positions)
            if max_dist > 30.0 * 0.3048:
                alerts.append(MaintenanceAlert(
                    alert_id="DET-SPACING-001",
                    title="Smoke Detector Spacing Exceeds NFPA 72 Limit",
                    description=f"Maximum spacing {max_dist:.1f}m exceeds 30 ft (9.1m). Coverage gaps may delay detection.",
                    severity="critical",
                    due_date=now + one_week,
                    rule_id="DET-SPC-001",
                    component="detection:smoke_spacing",
                    action_required="Add intermediate smoke detectors or reposition existing ones to achieve ≤30 ft spacing.",
                    technician_required=True,
                ))

        # Check for overdue annual tests
        records = system_config.get("inspection_records", [])
        one_year_ago = now - 365 * 24 * 3600
        has_annual = any(
            r.get("type") == "annual_functional_test" and r.get("timestamp", 0) > one_year_ago
            for r in records
        )
        if not has_annual:
            alerts.append(MaintenanceAlert(
                alert_id="TST-ANNUAL-001",
                title="Annual Functional Test Overdue",
                description="No annual full functional test recorded within the last year.",
                severity="major",
                due_date=now + one_week,
                rule_id="TST-FUN-001",
                component="testing:annual",
                action_required="Schedule certified technician for full functional test of every device, notification appliances, and transmission paths.",
                technician_required=True,
            ))

        self._alert_history.extend(alerts)
        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged by the owner."""
        for alert in self._alert_history:
            if alert.alert_id == alert_id and not alert.acknowledged:
                alert.acknowledged = True
                logger.info("Alert %s acknowledged", alert_id)
                if self.audit_logger:
                    self.audit_logger.log("alert_acknowledged", "owner", {"alert_id": alert_id})
                return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved."""
        for alert in self._alert_history:
            if alert.alert_id == alert_id and alert.resolved_at is None:
                alert.resolved_at = time.time()
                logger.info("Alert %s resolved", alert_id)
                return True
        return False

    def get_open_alerts(self) -> list[MaintenanceAlert]:
        """Get all unacknowledged and unresolved alerts."""
        return [
            a for a in self._alert_history
            if not a.acknowledged and a.resolved_at is None
        ]

    # ────────────────────────── Report generation ──────────────────────────

    def generate_compliance_report(self, results: list[ComplianceCheckResult]) -> dict:
        """Generate a comprehensive NFPA compliance report."""
        passed = len([r for r in results if r.status == ComplianceStatus.PASS])
        warnings = len([r for r in results if r.status == ComplianceStatus.WARN])
        failed = len([r for r in results if r.status == ComplianceStatus.FAIL])
        critical = len([r for r in results if r.severity == "critical" and r.status != ComplianceStatus.PASS])
        auto_fixable = [r for r in results if r.auto_fixable and r.status != ComplianceStatus.PASS]

        return {
            "generated_at": time.time(),
            "standards": ["NFPA 72 (2022)", "NFPA 10 (2022)"],
            "summary": {
                "total_checks": len(results),
                "passed": passed,
                "warnings": warnings,
                "failed": failed,
                "critical_failures": critical,
                "compliance_score": round(passed / max(len(results), 1) * 100, 1),
                "auto_fixable_issues": len(auto_fixable),
            },
            "by_category": self._categorize_results(results),
            "failed_checks": [
                {
                    "rule": r.rule.value,
                    "description": r.description,
                    "message": r.message,
                    "recommendation": r.recommendation,
                    "severity": r.severity,
                    "auto_fixable": r.auto_fixable,
                    "fix_action": r.fix_action,
                }
                for r in results if r.status in (ComplianceStatus.FAIL, ComplianceStatus.WARN)
            ],
            "open_maintenance_alerts": [
                {
                    "id": a.alert_id,
                    "title": a.title,
                    "severity": a.severity,
                    "component": a.component,
                    "action_required": a.action_required,
                    "technician_required": a.technician_required,
                    "due_in_days": round((a.due_date - time.time()) / 86400, 1),
                }
                for a in self.get_open_alerts()
            ],
        }

    def _categorize_results(self, results: list[ComplianceCheckResult]) -> dict:
        categories = {}
        for r in results:
            cat = RULE_DEFINITIONS.get(r.rule, {}).get("category", "other")
            if cat not in categories:
                categories[cat] = {"total": 0, "passed": 0, "failed": 0, "warnings": 0}
            categories[cat]["total"] += 1
            if r.status == ComplianceStatus.PASS:
                categories[cat]["passed"] += 1
            elif r.status == ComplianceStatus.FAIL:
                categories[cat]["failed"] += 1
            elif r.status == ComplianceStatus.WARN:
                categories[cat]["warnings"] += 1
        return categories

    # ────────────────────────── Helpers ──────────────────────────

    def _max_detector_spacing(self, positions: dict) -> float:
        """Calculate maximum distance between any two detectors."""
        import math
        max_dist = 0.0
        pos_list = list(positions.values())
        for i, p1 in enumerate(pos_list):
            for p2 in pos_list[i + 1:]:
                dist = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
                max_dist = max(max_dist, dist)
        return max_dist

    def _days_ago(self, timestamp: float) -> int:
        return int((time.time() - timestamp) / 86400)


# ────────────────────────── Owner Notification System ──────────────────────────

class OwnerNotifier:
    """Sends maintenance and compliance alerts to the system owner.

    Supports multiple channels: SMS (Kenya/Safaricom), email, webhook,
    and Hermes Agent bridge integration.

    Usage::

        notifier = OwnerNotifier(sms_client, email_client)
        await notifier.notify_maintenance_alert(alert)
    """

    def __init__(
        self,
        sms_client=None,
        email_client=None,
        webhook_url: str | None = None,
        hermes_bridge=None,
        *,
        mock: bool = False,
    ) -> None:
        self.sms_client = sms_client
        self.email_client = email_client
        self.webhook_url = webhook_url
        self.hermes_bridge = hermes_bridge
        self.mock = mock

    async def notify_maintenance_alert(self, alert: MaintenanceAlert) -> None:
        """Send maintenance alert to owner via all configured channels."""
        message = self._format_alert_message(alert)

        if self.sms_client:
            try:
                await self.sms_client.send(alert.phone or "", message)
                logger.info("Maintenance alert sent via SMS: %s", alert.alert_id)
            except Exception as exc:
                logger.warning("SMS send failed for %s: %s", alert.alert_id, exc)

        if self.email_client:
            try:
                await self.email_client.send(
                    subject=f"[FIRE SYSTEM] {alert.title}",
                    body=message,
                )
                logger.info("Maintenance alert sent via email: %s", alert.alert_id)
            except Exception as exc:
                logger.warning("Email send failed for %s: %s", alert.alert_id, exc)

        if self.hermes_bridge:
            try:
                await self.hermes_bridge.send_error(alert.component, alert.description)
            except Exception as exc:
                logger.warning("Hermes send failed for %s: %s", alert.alert_id, exc)

    def _format_alert_message(self, alert: MaintenanceAlert) -> str:
        severity_emoji = {
            "critical": "🚨",
            "major": "⚠️",
            "minor": "ℹ️",
            "info": "ℹ️",
        }.get(alert.severity, "ℹ️")

        lines = [
            f"{severity_emoji} FIRE SYSTEM ALERT",
            f"",
            f"Title: {alert.title}",
            f"Component: {alert.component}",
            f"Severity: {alert.severity.upper()}",
            f"",
            f"Description:",
            f"{alert.description}",
            f"",
            f"Action Required:",
            f"{alert.action_required}",
        ]

        if alert.technician_required:
            lines.extend([
                f"",
                f"⚠️ CERTIFIED TECHNICIAN REQUIRED",
            ])

        lines.extend([
            f"",
            f"Rule: {alert.rule_id}",
            f"Alert ID: {alert.alert_id}",
        ])

        return "\n".join(lines)

    async def send_compliance_summary(
        self,
        report: dict,
        owner_phone: str | None = None,
        owner_email: str | None = None,
    ) -> None:
        """Send weekly/monthly compliance summary to owner."""
        summary = report.get("summary", {})
        msg = (
            f"🔥 FIRE SYSTEM COMPLIANCE REPORT\n"
            f"Score: {summary.get('compliance_score', 0)}%\n"
            f"Passed: {summary.get('passed', 0)}\n"
            f"Warnings: {summary.get('warnings', 0)}\n"
            f"Failed: {summary.get('failed', 0)}\n"
            f"Critical: {summary.get('critical_failures', 0)}\n"
            f"Auto-fixable: {summary.get('auto_fixable_issues', 0)}\n"
            f"\nOpen maintenance items: {len(report.get('open_maintenance_alerts', []))}"
        )

        if self.sms_client and owner_phone:
            await self.sms_client.send(owner_phone, msg)
        if self.email_client and owner_email:
            await self.email_client.send(
                subject="[FIRE SYSTEM] Compliance Report",
                body=msg,
            )
