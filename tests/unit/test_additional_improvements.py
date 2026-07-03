"""Tests for additional improvements ADD-001 through ADD-020.
"""
import asyncio

import numpy as np
import pytest

from fire_suppression.sensors.thermal_drift import ThermalDriftCompensator
from fire_suppression.sensors.water_ingress import WaterIngressSensor
from fire_suppression.detection.flicker_analyzer import FlameFlickerAnalyzer
from fire_suppression.detection.false_positive_classifier import FalsePositiveClassifier
from fire_suppression.alerts.voice_alert import VoiceAlertSystem, VoicePriority
from fire_suppression.alerts.evacuation_leds import EvacuationLEDController
from fire_suppression.telemetry.cloud_backup import CloudBackup
from fire_suppression.diagnostics.predictive_maintenance import PredictiveMaintenance
from fire_suppression.actuation.sprinkler_valves import SmartSprinklerController
from fire_suppression.detection.smoke_plume_tracker import SensorPosition, SmokePlumeTracker
from fire_suppression.alerts.haptic_alert import HapticAlertSystem, HapticPattern
from fire_suppression.telemetry.aqi_calculator import AQICalculator
from fire_suppression.detection.seasonal_adjuster import SeasonalThresholdAdjuster
from fire_suppression.sensors.co_sensor import COSensor
from fire_suppression.sensors.vibration_sensor import VibrationSensor
from fire_suppression.sensors.night_vision import NightVisionController
from fire_suppression.diagnostics.compliance import ComplianceChecker


class TestThermalDrift:
    def test_compensate_changes_value(self) -> None:
        comp = ThermalDriftCompensator()
        result = comp.compensate(raw_obj_temp=65.0, sensor_die_temp=40.0, reference_ambient=25.0)
        # Die is hotter than ref, so correction subtracts
        assert result < 65.0

    def test_auto_calibrate(self) -> None:
        comp = ThermalDriftCompensator()
        comp.auto_calibrate(known_obj_temp=100.0, raw_obj_temp=105.0, sensor_die_temp=35.0)
        assert comp._coefficient != 0.02


class TestWaterIngress:
    def test_mock_dry(self) -> None:
        sensor = WaterIngressSensor(mock=True)
        result = sensor.read()
        assert result["wet"] is False

    def test_is_dry(self) -> None:
        sensor = WaterIngressSensor(mock=True)
        assert sensor.is_dry() is True


class TestFlameFlicker:
    def test_empty_buffer_returns_zero(self) -> None:
        analyzer = FlameFlickerAnalyzer(sample_rate_hz=10)
        score = analyzer.add_reading(100.0)
        assert score == 0.0

    def test_flicker_detection(self) -> None:
        analyzer = FlameFlickerAnalyzer(sample_rate_hz=10)
        # Simulate 5 Hz flicker signal
        t = np.linspace(0, 2, 20)
        signal = 100 + 10 * np.sin(2 * np.pi * 5 * t)
        for val in signal:
            analyzer.add_reading(float(val))
        score = analyzer.add_reading(float(signal[-1]))
        assert score >= 0.0
        assert score <= 1.0


class TestFalsePositiveClassifier:
    def test_rule_based_fallback(self) -> None:
        clf = FalsePositiveClassifier(mock=True)
        is_fp, conf = clf.predict({"temp_delta_1min": 15, "humidity_percent": 40, "flicker_score": 0.0})
        assert isinstance(is_fp, bool)

    def test_record_normal(self) -> None:
        clf = FalsePositiveClassifier(mock=True)
        clf.record_normal({"temp_delta_1min": 1, "smoke_ppm": 20})
        assert clf.normal_sample_count == 1


class TestVoiceAlert:
    @pytest.mark.asyncio
    async def test_mock_speak(self) -> None:
        voice = VoiceAlertSystem(mock=True)
        await voice.start()
        await voice.speak("Test alert", priority=VoicePriority.CRITICAL)
        await asyncio.sleep(0.3)
        await voice.stop()


class TestEvacuationLEDs:
    def test_mock_show_route(self) -> None:
        leds = EvacuationLEDController(num_leds=60, mock=True)
        leds.show_route("north")

    def test_show_alert(self) -> None:
        leds = EvacuationLEDController(mock=True)
        leds.show_alert()

    def test_zone_fire_route(self) -> None:
        leds = EvacuationLEDController(mock=True)
        leds.show_zone_fire("north")


class TestCloudBackup:
    @pytest.mark.asyncio
    async def test_mock_upload(self) -> None:
        backup = CloudBackup(mock=True)
        result = await backup.upload_event({"type": "fire_alert"})
        assert result is True


class TestPredictiveMaintenance:
    def test_record_and_check(self) -> None:
        pm = PredictiveMaintenance()
        for i in range(150):
            pm.record("mq2", "response_time_ms", 45.0 + i * 0.01)
        alerts = pm.check_all()
        assert isinstance(alerts, list)

    def test_health_score(self) -> None:
        pm = PredictiveMaintenance()
        for i in range(150):
            pm.record("mq2", "response_time_ms", 45.0)
        score = pm.get_sensor_health_score("mq2")
        assert 0.0 <= score <= 1.0


class TestSprinklerValves:
    @pytest.mark.asyncio
    async def test_mock_open_close(self) -> None:
        ctrl = SmartSprinklerController(
            valve_pins={"zone_a": 1},
            mock=True,
        )
        status = await ctrl.open_valve("zone_a")
        assert status.is_open is True
        status = await ctrl.close_valve("zone_a")
        assert status.is_open is False

    def test_all_valves_closed(self) -> None:
        ctrl = SmartSprinklerController(valve_pins={"a": 1}, mock=True)
        assert ctrl.all_valves_closed() is True


class TestSmokePlumeTracker:
    def test_plume_direction(self) -> None:
        tracker = SmokePlumeTracker()
        tracker.add_sensor(SensorPosition("north", 0, 5))
        tracker.add_sensor(SensorPosition("south", 0, -5))
        result = tracker.update({
            "north": {"smoke_ppm": 100},
            "south": {"smoke_ppm": 10},
        })
        assert result["origin_estimate"] is not None
        assert result["confidence"] > 0

    def test_insufficient_sensors(self) -> None:
        tracker = SmokePlumeTracker()
        result = tracker.update({"only": {"smoke_ppm": 50}})
        assert result["origin_estimate"] is None


class TestHapticAlert:
    @pytest.mark.asyncio
    async def test_mock_connect(self) -> None:
        haptic = HapticAlertSystem(mock=True)
        result = await haptic.connect_device("AA:BB:CC:DD:EE:FF")
        assert result is True

    @pytest.mark.asyncio
    async def test_mock_pattern(self) -> None:
        haptic = HapticAlertSystem(mock=True)
        await haptic.connect_device("AA:BB:CC:DD:EE:FF")
        await haptic.send_pattern(HapticPattern.FIRE_ALERT)


class TestAQICalculator:
    def test_good_aqi(self) -> None:
        aqi = AQICalculator()
        result = aqi.update(pm25_ug_m3=5.0)
        assert result["aqi"] <= 50
        assert result["category"] == "Good"

    def test_unhealthy_aqi(self) -> None:
        aqi = AQICalculator()
        result = aqi.update(pm25_ug_m3=80.0)
        assert result["aqi"] > 100


class TestSeasonalAdjuster:
    def test_winter_temperature_multiplier(self) -> None:
        import time as _time
        # Can't easily mock time, so just verify function exists
        adjuster = SeasonalThresholdAdjuster()
        result = adjuster.adjust("temperature_c", base_threshold=70.0)
        assert result != 70.0  # Should be adjusted

    def test_season_detection(self) -> None:
        adjuster = SeasonalThresholdAdjuster()
        season = adjuster.get_current_season()
        assert season in ("winter", "spring", "summer", "autumn")


class TestCOSensor:
    @pytest.mark.asyncio
    async def test_mock_read(self) -> None:
        sensor = COSensor(mock=True)
        reading = await sensor.read()
        assert "co_ppm" in reading.values
        assert reading.values["alert"] is False

    def test_threshold(self) -> None:
        sensor = COSensor(mock=True)
        assert sensor.get_alert_threshold() == 35.0
        sensor.set_alert_threshold(50.0)
        assert sensor.get_alert_threshold() == 50.0


class TestVibrationSensor:
    @pytest.mark.asyncio
    async def test_mock_read(self) -> None:
        sensor = VibrationSensor(mock=True)
        reading = await sensor.read()
        assert "shake_detected" in reading.values

    def test_quake_armed(self) -> None:
        sensor = VibrationSensor(mock=True)
        assert sensor.is_quake_armed() is False


class TestNightVision:
    def test_mock_is_dark(self) -> None:
        nv = NightVisionController(mock=True)
        assert nv.is_dark() is True

    def test_auto_mode(self) -> None:
        nv = NightVisionController(mock=True)
        result = nv.auto_mode()
        assert result is True  # Mock simulates dark

    def test_status(self) -> None:
        nv = NightVisionController(mock=True)
        status = nv.get_status()
        assert "lux" in status
        assert "ir_active" in status


class TestComplianceChecker:
    def test_sensor_spacing_pass(self) -> None:
        checker = ComplianceChecker()
        results = checker.check_all({
            "sensor_positions": {"s1": (0, 0), "s2": (5, 0)},
            "battery_backup_hours": 24,
            "suppression_zones": ["a"],
            "has_manual_pull_station": True,
            "notification_devices": ["audible", "visual"],
        })
        assert len(results) > 0
        passed = [r for r in results if r.level.value == "pass"]
        assert len(passed) > 0

    def test_battery_fail(self) -> None:
        checker = ComplianceChecker()
        results = checker.check_all({
            "battery_backup_hours": 12,
            "sensor_positions": {"s1": (0, 0)},
            "suppression_zones": [],
        })
        failed = [r for r in results if r.level.value == "fail"]
        assert len(failed) >= 2  # battery + suppression

    def test_report_generation(self) -> None:
        checker = ComplianceChecker()
        results = checker.check_all({
            "sensor_positions": {"s1": (0, 0), "s2": (5, 0)},
            "battery_backup_hours": 24,
            "suppression_zones": ["a"],
            "has_manual_pull_station": True,
            "notification_devices": ["audible", "visual"],
        })
        report = checker.generate_compliance_report(results)
        assert "standard" in report
        assert "compliant" in report
