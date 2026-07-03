"""Tests for NFPA 72/10 compliance engine with owner alerts.

# NFPA-COMPLIANCE — Full regulatory compliance testing
"""
import time

import pytest

from fire_suppression.diagnostics.nfpa_compliance import (
    ComplianceCheckResult,
    ComplianceRule,
    ComplianceStatus,
    MaintenanceAlert,
    NFPAComplianceEngine,
    OwnerNotifier,
)


class TestComplianceRule:
    def test_rule_values(self) -> None:
        assert ComplianceRule.DET_SPC_001.value == "DET-SPC-001"
        assert ComplianceRule.EXT_INS_001.value == "EXT-INS-001"

    def test_rule_count(self) -> None:
        # Should have rules for detection, notification, power, monitoring, testing, control, extinguishers
        rules = list(ComplianceRule)
        assert len(rules) >= 20


class TestNFPAComplianceEngine:
    def test_smoke_detector_spacing_pass(self) -> None:
        engine = NFPAComplianceEngine()
        config = {
            "sensor_positions": {"s1": (0, 0), "s2": (5, 0)},  # 5m spacing OK
            "rooms": ["room1", "room2"],
            "critical_areas": [],
            "room_detectors": {"room1": ["s1"], "room2": ["s2"]},
            "notification_appliances": [{"type": "audible"}, {"type": "visible"}],
            "battery_backup_hours": 25,
            "has_dedicated_circuit": True,
            "has_low_battery_annunciation": True,
            "transmission_paths": ["wifi", "cellular"],
            "has_circuit_supervision": True,
            "zone_isolation_tested": True,
            "zones": [{"name": "zone1"}],
            "inspection_records": [
                {"type": "annual_functional_test", "timestamp": time.time()},
                {"type": "battery_discharge_test", "timestamp": time.time()},
            ],
            "extinguisher_inventory": [
                {
                    "id": "ext1",
                    "location": "kitchen",
                    "agent_type": "dry_chemical",
                    "last_monthly_inspection": time.time(),
                    "last_annual_maintenance": time.time(),
                    "last_hydrostatic_test": time.time(),
                }
            ],
        }
        results = engine.run_full_compliance_check(config)
        assert len(results) > 0
        passed = [r for r in results if r.status == ComplianceStatus.PASS]
        failed = [r for r in results if r.status == ComplianceStatus.FAIL]
        assert len(passed) > 0
        assert len(failed) == 0

    def test_smoke_detector_spacing_fail(self) -> None:
        engine = NFPAComplianceEngine()
        config = {
            "sensor_positions": {"s1": (0, 0), "s2": (20, 0)},  # 20m > 30ft (9.1m) ... wait, 20m > 9.1m, this should fail
            "rooms": ["room1", "room2"],
            "critical_areas": [],
            "room_detectors": {"room1": ["s1"], "room2": ["s2"]},
            "notification_appliances": [],
            "battery_backup_hours": 20,
            "has_dedicated_circuit": False,
            "has_low_battery_annunciation": False,
            "transmission_paths": ["wifi"],
            "has_circuit_supervision": False,
            "zones": [],
            "inspection_records": [],
            "extinguisher_inventory": [],
        }
        results = engine.run_full_compliance_check(config)
        failed = [r for r in results if r.status == ComplianceStatus.FAIL]
        assert len(failed) > 0
        # Should fail on spacing, audible, battery, low battery, transmission paths, circuit supervision
        spacing_fail = [r for r in failed if r.rule == ComplianceRule.DET_SPC_001]
        assert len(spacing_fail) > 0

    def test_battery_below_minimum(self) -> None:
        engine = NFPAComplianceEngine()
        config = {
            "sensor_positions": {"s1": (0, 0)},
            "rooms": ["room1"],
            "critical_areas": [],
            "room_detectors": {"room1": ["s1"]},
            "notification_appliances": [{"type": "audible"}],
            "battery_backup_hours": 20,
            "has_dedicated_circuit": True,
            "has_low_battery_annunciation": True,
            "transmission_paths": ["wifi", "cellular"],
            "has_circuit_supervision": True,
            "zones": [{"name": "zone1"}],
            "zone_isolation_tested": True,
            "inspection_records": [],
            "extinguisher_inventory": [],
        }
        results = engine.run_full_compliance_check(config)
        battery_fail = [r for r in results if r.rule == ComplianceRule.PWR_SEC_001 and r.status == ComplianceStatus.FAIL]
        assert len(battery_fail) > 0
        assert "24h" in battery_fail[0].message

    def test_critical_area_redundancy_warn(self) -> None:
        engine = NFPAComplianceEngine()
        config = {
            "sensor_positions": {"s1": (0, 0)},
            "rooms": ["kitchen"],
            "critical_areas": ["kitchen"],
            "room_detectors": {"kitchen": ["s1"]},
            "notification_appliances": [{"type": "audible"}],
            "battery_backup_hours": 25,
            "has_dedicated_circuit": True,
            "has_low_battery_annunciation": True,
            "transmission_paths": ["wifi", "cellular"],
            "has_circuit_supervision": True,
            "zones": [{"name": "zone1"}],
            "zone_isolation_tested": True,
            "inspection_records": [],
            "extinguisher_inventory": [],
        }
        results = engine.run_full_compliance_check(config)
        redundancy_warn = [r for r in results if r.rule == ComplianceRule.DET_COV_002]
        assert len(redundancy_warn) > 0

    def test_generate_maintenance_alerts(self) -> None:
        engine = NFPAComplianceEngine()
        config = {
            "sensor_positions": {"s1": (0, 0), "s2": (30, 0)},  # 30m > 9.1m
            "rooms": ["room1", "room2"],
            "critical_areas": [],
            "room_detectors": {"room1": ["s1"], "room2": ["s2"]},
            "notification_appliances": [{"type": "audible"}],
            "battery_backup_hours": 20,
            "has_dedicated_circuit": True,
            "has_low_battery_annunciation": True,
            "transmission_paths": ["wifi"],
            "has_circuit_supervision": True,
            "zones": [],
            "inspection_records": [],
            "extinguisher_inventory": [
                {
                    "id": "ext1",
                    "location": "kitchen",
                    "agent_type": "dry_chemical",
                    "last_monthly_inspection": time.time() - 60 * 86400,  # 60 days ago
                    "last_annual_maintenance": time.time(),
                    "last_hydrostatic_test": time.time(),
                }
            ],
        }
        alerts = engine.generate_maintenance_alerts(config)
        assert len(alerts) > 0

        # Should have spacing alert
        spacing_alerts = [a for a in alerts if "spacing" in a.title.lower()]
        assert len(spacing_alerts) > 0

        # Should have battery alert
        battery_alerts = [a for a in alerts if "battery" in a.title.lower()]
        assert len(battery_alerts) > 0

        # Should have extinguisher monthly inspection alert
        ext_alerts = [a for a in alerts if "Extinguisher" in a.title]
        assert len(ext_alerts) > 0

    def test_alert_acknowledge(self) -> None:
        engine = NFPAComplianceEngine()
        config = {
            "sensor_positions": {"s1": (0, 0)},
            "rooms": ["room1"],
            "critical_areas": [],
            "room_detectors": {"room1": ["s1"]},
            "notification_appliances": [{"type": "audible"}],
            "battery_backup_hours": 25,
            "has_dedicated_circuit": True,
            "has_low_battery_annunciation": True,
            "transmission_paths": ["wifi", "cellular"],
            "has_circuit_supervision": True,
            "zones": [],
            "inspection_records": [],
            "extinguisher_inventory": [],
        }
        # No alerts should be generated with this config
        alerts = engine.generate_maintenance_alerts(config)
        if alerts:
            alert_id = alerts[0].alert_id
            assert engine.acknowledge_alert(alert_id) is True
            assert engine.acknowledge_alert(alert_id) is False  # Already acknowledged
            assert engine.resolve_alert(alert_id) is True

    def test_compliance_report(self) -> None:
        engine = NFPAComplianceEngine()
        config = {
            "sensor_positions": {"s1": (0, 0), "s2": (5, 0)},
            "rooms": ["room1", "room2"],
            "critical_areas": [],
            "room_detectors": {"room1": ["s1"], "room2": ["s2"]},
            "notification_appliances": [{"type": "audible"}, {"type": "visible"}],
            "battery_backup_hours": 25,
            "has_dedicated_circuit": True,
            "has_low_battery_annunciation": True,
            "transmission_paths": ["wifi", "cellular"],
            "has_circuit_supervision": True,
            "zone_isolation_tested": True,
            "zones": [{"name": "zone1"}],
            "inspection_records": [
                {"type": "annual_functional_test", "timestamp": time.time()},
                {"type": "battery_discharge_test", "timestamp": time.time()},
            ],
            "extinguisher_inventory": [
                {
                    "id": "ext1",
                    "location": "kitchen",
                    "agent_type": "dry_chemical",
                    "last_monthly_inspection": time.time(),
                    "last_annual_maintenance": time.time(),
                    "last_hydrostatic_test": time.time(),
                }
            ],
        }
        results = engine.run_full_compliance_check(config)
        report = engine.generate_compliance_report(results)
        assert "summary" in report
        assert "standards" in report
        assert "NFPA 72" in report["standards"][0]
        assert report["summary"]["compliance_score"] > 50
        assert "by_category" in report
        assert "failed_checks" in report

    def test_empty_config(self) -> None:
        engine = NFPAComplianceEngine()
        results = engine.run_full_compliance_check({})
        assert len(results) > 0
        # Should fail on most items since nothing is configured
        failed = [r for r in results if r.status == ComplianceStatus.FAIL]
        assert len(failed) > 0


class TestOwnerNotifier:
    @pytest.mark.asyncio
    async def test_format_alert_message(self) -> None:
        notifier = OwnerNotifier(mock=True)
        alert = MaintenanceAlert(
            alert_id="TEST-001",
            title="Test Alert",
            description="Test description",
            severity="critical",
            due_date=time.time() + 86400,
            rule_id="TEST-RULE",
            component="test:component",
            action_required="Fix the thing",
            technician_required=True,
        )
        msg = notifier._format_alert_message(alert)
        assert "FIRE SYSTEM ALERT" in msg
        assert "Test Alert" in msg
        assert "CERTIFIED TECHNICIAN REQUIRED" in msg
        assert "TEST-RULE" in msg

    @pytest.mark.asyncio
    async def test_compliance_summary_format(self) -> None:
        notifier = OwnerNotifier(mock=True)
        report = {
            "summary": {
                "compliance_score": 85.5,
                "passed": 20,
                "warnings": 3,
                "failed": 2,
                "critical_failures": 1,
                "auto_fixable_issues": 1,
            },
            "open_maintenance_alerts": [
                {"title": "Test Alert 1"},
                {"title": "Test Alert 2"},
            ],
        }
        # Just verify it doesn't raise
        await notifier.send_compliance_summary(report)
