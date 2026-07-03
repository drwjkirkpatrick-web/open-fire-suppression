"""Tests for v0.4.0 modules: distributed audio, directional voice,
LiDAR, mmWave, acoustic fire signature, gas chromatograph, smart
building bridge, occupancy-aware detection, drone recon, blockchain
audit, satellite thermal, firefighter PPE, pressure differential, arc
fault, battery thermal runaway, smart glass, elevator recall, HVAC
shutdown, mass notification, post-fire air quality.
"""
import asyncio
import time

import numpy as np
import pytest

from fire_suppression.actuation.elevator_recall import Elevator, ElevatorRecall, ElevatorState
from fire_suppression.actuation.hvac_shutdown import HVACSmokeControl, HVACZone
from fire_suppression.actuation.smart_glass_opacity import SmartGlassController, SmartGlassPanel, GlassState
from fire_suppression.alerts.directional_voice_evac import DirectionalVoiceEvacuation, EvacuationRoute
from fire_suppression.alerts.firefighter_ppe_bridge import FirefighterPPEBridge
from fire_suppression.alerts.mass_notification_gateway import MassNotificationGateway
from fire_suppression.detection.arc_fault_detector import ArcFaultDetector
from fire_suppression.detection.battery_thermal_runaway import BatteryThermalRunawayDetector
from fire_suppression.detection.distributed_audio import DistributedSpeakerArray, SpeakerConfig
from fire_suppression.detection.mmwave_radar import MmwaveFireDetector
from fire_suppression.detection.occupancy_aware import OccupancyAwareDetector
from fire_suppression.detection.pressure_differential import PressureDifferentialDetector
from fire_suppression.detection.acoustic_fire_signature import AcousticFireDetector
from fire_suppression.network.drone_fire_recon import DroneFireRecon
from fire_suppression.network.smart_building_bridge import SmartBuildingBridge
from fire_suppression.sensors.gas_chromatograph import GasChromatographDetector
from fire_suppression.sensors.lidar_smoke import LidarSmokeDetector
from fire_suppression.telemetry.blockchain_audit import BlockchainAudit
from fire_suppression.detection.satellite_thermal import SatelliteThermalMonitor
from fire_suppression.telemetry.post_fire_air_quality import PostFireAirQualityMonitor


class TestDistributedAudio:
    def test_add_speaker(self) -> None:
        arr = DistributedSpeakerArray(mock=True)
        spk = SpeakerConfig("spk1", 0, 0, "zone_a", gpio_pin=17, target_db=83.0)
        arr.add_speaker(spk)
        assert len(arr.speakers) == 1
        assert arr.health["spk1"].online is True

    def test_calculate_spacing(self) -> None:
        arr = DistributedSpeakerArray(mock=True)
        result = arr.calculate_spacing(30, 20)
        assert result["speakers_count"] >= 4
        assert result["spacing_compliant"] is True

    def test_predicted_db(self) -> None:
        arr = DistributedSpeakerArray(mock=True)
        arr.add_speaker(SpeakerConfig("s1", 0, 0, "z", target_db=83.0))
        db = arr.predicted_db_at_point(0, 0)
        assert db > 70

    def test_compliance_check(self) -> None:
        arr = DistributedSpeakerArray(mock=True)
        arr.add_speaker(SpeakerConfig("s1", 0, 0, "z", target_db=83.0))
        arr.add_speaker(SpeakerConfig("s2", 10, 0, "z", target_db=83.0))
        arr.add_speaker(SpeakerConfig("s3", 0, 10, "z", target_db=83.0))
        arr.add_speaker(SpeakerConfig("s4", 10, 10, "z", target_db=83.0))
        comp = arr.check_compliance((0, 0, 10, 10))
        assert "coverage_percent" in comp
        assert comp["speakers_online"] >= 3

    @pytest.mark.asyncio
    async def test_activate_zone_mock(self) -> None:
        arr = DistributedSpeakerArray(mock=True)
        arr.add_speaker(SpeakerConfig("s1", 0, 0, "z", target_db=83.0))
        await arr.activate_zone("z")
        assert arr.health["s1"].online is True

    @pytest.mark.asyncio
    async def test_run_speaker_test(self) -> None:
        arr = DistributedSpeakerArray(mock=True)
        arr.add_speaker(SpeakerConfig("s1", 0, 0, "z", target_db=83.0))
        results = await arr.run_speaker_test()
        assert "s1" in results
        assert results["s1"]["passed"] is True

    def test_to_dict(self) -> None:
        arr = DistributedSpeakerArray(mock=True)
        d = arr.to_dict()
        assert "speaker_count" in d


class TestDirectionalVoiceEvac:
    def test_add_route(self) -> None:
        dve = DirectionalVoiceEvacuation(mock=True)
        route = EvacuationRoute("lobby", "kitchen", "east", "Main Exit", "Go east")
        dve.add_route(route)
        assert dve.get_route("lobby", "kitchen") is not None

    def test_generate_fire_message(self) -> None:
        dve = DirectionalVoiceEvacuation(mock=True)
        msg = dve.generate_fire_message("Kitchen", "en")
        assert "Fire detected" in msg
        assert "Kitchen" in msg

    def test_generate_directional_message(self) -> None:
        dve = DirectionalVoiceEvacuation(mock=True)
        dve.add_route(EvacuationRoute("lobby", "kitchen", "east", "Main Exit", "Go east", distance_meters=20))
        msg = dve.generate_directional_message("lobby", "kitchen", "en")
        assert msg is not None
        assert "east" in msg.lower()

    def test_generate_all_clear_message(self) -> None:
        dve = DirectionalVoiceEvacuation(mock=True)
        msg = dve.generate_all_clear_message("en")
        assert "clear" in msg.lower()

    def test_verify_intelligibility(self) -> None:
        dve = DirectionalVoiceEvacuation(mock=True)
        result = dve.verify_voice_intelligibility("lobby")
        assert "intelligible" in result

    def test_to_dict(self) -> None:
        dve = DirectionalVoiceEvacuation(mock=True)
        d = dve.to_dict()
        assert "route_count" in d


class TestLidarSmoke:
    @pytest.mark.asyncio
    async def test_calibrate(self) -> None:
        lidar = LidarSmokeDetector(mock=True)
        await lidar.calibrate(duration_sec=12.0)
        assert lidar._calibrated is True
        assert len(lidar._baseline) > 0

    @pytest.mark.asyncio
    async def test_read(self) -> None:
        lidar = LidarSmokeDetector(mock=True)
        await lidar.calibrate(duration_sec=12.0)
        result = await lidar.read()
        assert "status" in result
        assert result.get("calibrated") is True

    def test_to_dict(self) -> None:
        lidar = LidarSmokeDetector(mock=True)
        d = lidar.to_dict()
        assert "sensor_id" in d


class TestMmwaveRadar:
    @pytest.mark.asyncio
    async def test_detect_mock(self) -> None:
        radar = MmwaveFireDetector(mock=True)
        await radar.start()
        # Need 10 frames before detection
        for _ in range(15):
            await radar.detect()
        result = await radar.detect()
        assert "status" in result
        assert "confidence" in result
        await radar.stop()

    def test_to_dict(self) -> None:
        radar = MmwaveFireDetector(mock=True)
        d = radar.to_dict()
        assert "sensor_id" in d


class TestAcousticFireDetector:
    @pytest.mark.asyncio
    async def test_detect_mock(self) -> None:
        det = AcousticFireDetector(mock=True)
        await det.start()
        # Need 30 readings for calibration
        for _ in range(35):
            result = await det.detect()
        assert "status" in result
        assert "confidence" in result
        await det.stop()

    def test_to_dict(self) -> None:
        det = AcousticFireDetector(mock=True)
        d = det.to_dict()
        assert "sensor_id" in d


class TestGasChromatograph:
    @pytest.mark.asyncio
    async def test_calibrate(self) -> None:
        gc = GasChromatographDetector(mock=True)
        await gc.calibrate()
        assert gc._calibrated is True

    @pytest.mark.asyncio
    async def test_detect(self) -> None:
        gc = GasChromatographDetector(mock=True)
        await gc.calibrate()
        result = await gc.detect()
        assert "status" in result
        assert "concentrations_ppm" in result

    def test_to_dict(self) -> None:
        gc = GasChromatographDetector(mock=True)
        d = gc.to_dict()
        assert "sensor_id" in d


class TestSmartBuildingBridge:
    @pytest.mark.asyncio
    async def test_connect(self) -> None:
        bridge = SmartBuildingBridge(mock=True)
        ok = await bridge.connect()
        assert ok is True

    @pytest.mark.asyncio
    async def test_fire_response(self) -> None:
        bridge = SmartBuildingBridge(mock=True)
        await bridge.connect()
        result = await bridge.execute_fire_response("zone_a")
        assert result["elevator_recall"] is True
        assert result["emergency_exits"] is True

    def test_to_dict(self) -> None:
        bridge = SmartBuildingBridge(mock=True)
        d = bridge.to_dict()
        assert "connected" in d


class TestOccupancyAware:
    def test_init(self) -> None:
        det = OccupancyAwareDetector(zones=["kitchen", "lobby"], mock=True)
        assert len(det.zones) == 2

    def test_get_adjusted_thresholds(self) -> None:
        det = OccupancyAwareDetector(zones=["kitchen"], mock=True)
        base = {"smoke_warning": 100, "smoke_alert": 200, "temp_rise_rate": 5.0}
        adjusted = det.get_adjusted_thresholds("kitchen", base)
        assert adjusted["occupancy_adjusted"] is True

    def test_set_schedule(self) -> None:
        det = OccupancyAwareDetector(zones=["kitchen"], mock=True)
        det.set_schedule("kitchen", "08:00", "18:00")
        assert "kitchen" in det._schedule

    def test_to_dict(self) -> None:
        det = OccupancyAwareDetector(zones=["kitchen"], mock=True)
        d = det.to_dict()
        assert "zones" in d


class TestDroneFireRecon:
    @pytest.mark.asyncio
    async def test_plan_mission(self) -> None:
        drone = DroneFireRecon(base_lat=37.7749, base_lon=-122.4194, mock=True)
        waypoints = drone.plan_recon_mission((37.7750, -122.4195))
        assert len(waypoints) >= 3
        assert waypoints[-1].action == "return"

    @pytest.mark.asyncio
    async def test_dispatch_mock(self) -> None:
        drone = DroneFireRecon(base_lat=37.7749, base_lon=-122.4194, mock=True)
        result = await drone.dispatch((37.7750, -122.4195))
        assert result["status"] == "completed"
        assert result["thermal_detections"] >= 0

    def test_get_hotspots(self) -> None:
        drone = DroneFireRecon(base_lat=37.7749, base_lon=-122.4194, mock=True)
        # Need to dispatch first
        asyncio.run(drone.dispatch((37.7750, -122.4195)))
        hotspots = drone.get_hotspots()
        assert isinstance(hotspots, list)

    def test_to_dict(self) -> None:
        drone = DroneFireRecon(mock=True)
        d = drone.to_dict()
        assert "drone_id" in d


class TestBlockchainAudit:
    def test_init_creates_genesis(self) -> None:
        ba = BlockchainAudit(mock=True)
        assert ba.get_block_count() >= 1
        assert ba._headers[0].event_type == "GENESIS"

    def test_add_event(self) -> None:
        ba = BlockchainAudit(mock=True)
        block = ba.add_event("fire_alert", {"zone": "kitchen"})
        assert block.index >= 1
        assert block.event_type == "fire_alert"

    def test_verify_chain(self) -> None:
        ba = BlockchainAudit(mock=True)
        ba.add_event("fire_alert", {"zone": "kitchen"})
        ba.add_event("suppression", {"relay": 1})
        result = ba.verify_chain()
        assert result["valid"] is True
        assert result["total_blocks"] == 3

    def test_verify_chain_tampered(self) -> None:
        ba = BlockchainAudit(mock=True)
        ba.add_event("fire_alert", {"zone": "kitchen"})
        # Tamper with the stored block hash
        original_hash = ba._headers[1].block_hash
        ba._headers[1].block_hash = b"\xff" * 32
        result = ba.verify_chain()
        assert result["valid"] is False
        assert result["tampered_count"] > 0

    def test_merkle_root(self) -> None:
        ba = BlockchainAudit(mock=True)
        ba.add_event("test", {"a": 1})
        root = ba.get_merkle_root()
        assert len(root) == 64

    def test_to_dict(self) -> None:
        ba = BlockchainAudit(mock=True)
        d = ba.to_dict()
        assert "block_count" in d


class TestSatelliteThermal:
    def test_haversine(self) -> None:
        mon = SatelliteThermalMonitor(facility_lat=0.0, facility_lon=0.0, radius_km=10, mock=True)
        dist = mon._haversine_distance(0, 0, 0, 1)
        assert abs(dist - 111.0) < 2  # ~111 km per degree lon at equator

    @pytest.mark.asyncio
    async def test_fetch_firms(self) -> None:
        mon = SatelliteThermalMonitor(facility_lat=37.7749, facility_lon=-122.4194, mock=True)
        hotspots = await mon.fetch_nasa_firms()
        assert isinstance(hotspots, list)

    @pytest.mark.asyncio
    async def test_correlate(self) -> None:
        mon = SatelliteThermalMonitor(facility_lat=37.7749, facility_lon=-122.4194, mock=True)
        await mon.fetch_nasa_firms()
        result = mon.correlate_with_local(37.7749, -122.4194)
        assert "correlated" in result

    def test_to_dict(self) -> None:
        mon = SatelliteThermalMonitor(facility_lat=0.0, facility_lon=0.0, mock=True)
        d = mon.to_dict()
        assert "facility" in d


class TestFirefighterPPEBridge:
    @pytest.mark.asyncio
    async def test_update_status(self) -> None:
        bridge = FirefighterPPEBridge(mock=True)
        await bridge.update_firefighter_status()
        assert len(bridge._firefighters) >= 0

    def test_get_summary(self) -> None:
        bridge = FirefighterPPEBridge(mock=True)
        asyncio.run(bridge.update_firefighter_status())
        summary = bridge.get_firefighter_summary()
        assert isinstance(summary, list)

    def test_send_building_data(self) -> None:
        bridge = FirefighterPPEBridge(mock=True)
        data = bridge.send_building_data("kitchen", {"co": 10})
        assert "fire_zone" in data

    def test_to_dict(self) -> None:
        bridge = FirefighterPPEBridge(mock=True)
        d = bridge.to_dict()
        assert "mock" in d


class TestPressureDifferential:
    @pytest.mark.asyncio
    async def test_calibrate(self) -> None:
        det = PressureDifferentialDetector(mock=True)
        await det.calibrate(duration_sec=2.0)
        assert det._calibrated is True

    @pytest.mark.asyncio
    async def test_detect(self) -> None:
        det = PressureDifferentialDetector(mock=True)
        await det.calibrate(duration_sec=2.0)
        result = await det.detect()
        assert "status" in result
        assert "differential_pa" in result

    @pytest.mark.asyncio
    async def test_stairwell_check(self) -> None:
        det = PressureDifferentialDetector(mock=True)
        result = await det.check_stairwell_pressurization()
        assert "compliant" in result

    def test_to_dict(self) -> None:
        det = PressureDifferentialDetector(mock=True)
        d = det.to_dict()
        assert "baseline_pa" in d


class TestArcFaultDetector:
    @pytest.mark.asyncio
    async def test_detect(self) -> None:
        det = ArcFaultDetector(mock=True)
        await det.start()
        # Need 10 waveforms for calibration
        for _ in range(15):
            result = await det.detect()
        assert "status" in result
        assert "confidence" in result
        await det.stop()

    def test_to_dict(self) -> None:
        det = ArcFaultDetector(mock=True)
        d = det.to_dict()
        assert "sensor_id" in d


class TestBatteryThermalRunaway:
    @pytest.mark.asyncio
    async def test_detect(self) -> None:
        det = BatteryThermalRunawayDetector(mock=True)
        await det.start()
        result = await det.detect()
        assert "status" in result
        assert "max_stage" in result
        await det.stop()

    def test_to_dict(self) -> None:
        det = BatteryThermalRunawayDetector(mock=True)
        d = det.to_dict()
        assert "battery_id" in d


class TestSmartGlass:
    @pytest.mark.asyncio
    async def test_fire_response(self) -> None:
        ctrl = SmartGlassController(mock=True)
        ctrl.add_panel(SmartGlassPanel("p1", "kitchen", gpio_pin=22))
        ctrl.add_panel(SmartGlassPanel("p2", "lobby", gpio_pin=23))
        result = await ctrl.handle_fire_detection("kitchen", radiant_heat_kw_m2=3.0)
        assert result["panels_adjusted"] == 2

    @pytest.mark.asyncio
    async def test_set_state(self) -> None:
        ctrl = SmartGlassController(mock=True)
        ctrl.add_panel(SmartGlassPanel("p1", "kitchen"))
        ok = await ctrl.set_state("p1", GlassState.OPAQUE)
        assert ok is True
        assert ctrl.panels["p1"].current_state == GlassState.OPAQUE

    def test_to_dict(self) -> None:
        ctrl = SmartGlassController(mock=True)
        ctrl.add_panel(SmartGlassPanel("p1", "kitchen"))
        d = ctrl.to_dict()
        assert "panel_count" in d


class TestElevatorRecall:
    @pytest.mark.asyncio
    async def test_recall_all(self) -> None:
        recall = ElevatorRecall(mock=True)
        recall.add_elevator(Elevator("elev_1", designated_floor=1, current_floor=5))
        result = await recall.recall_all(fire_zone="kitchen")
        assert result["elevators_recalled"] == 1
        assert recall.elevators["elev_1"].state == ElevatorState.AT_DESIGNATED

    @pytest.mark.asyncio
    async def test_phase_ii(self) -> None:
        recall = ElevatorRecall(mock=True)
        recall.add_elevator(Elevator("elev_1"))
        ok = await recall.enable_phase_ii("elev_1")
        assert ok is True
        assert recall.elevators["elev_1"].state == ElevatorState.PHASE_II

    def test_to_dict(self) -> None:
        recall = ElevatorRecall(mock=True)
        d = recall.to_dict()
        assert "elevator_count" in d


class TestHVACSmokeControl:
    @pytest.mark.asyncio
    async def test_smoke_control(self) -> None:
        hvac = HVACSmokeControl(mock=True)
        hvac.add_zone(HVACZone("kitchen", is_stairwell=False))
        hvac.add_zone(HVACZone("stairwell_a", is_stairwell=True))
        result = await hvac.execute_smoke_control("kitchen")
        assert result["zones_controlled"] == 2
        assert result["all_success"] is True

    def test_to_dict(self) -> None:
        hvac = HVACSmokeControl(mock=True)
        d = hvac.to_dict()
        assert "zone_count" in d


class TestMassNotification:
    @pytest.mark.asyncio
    async def test_send_ipaws_mock(self) -> None:
        gateway = MassNotificationGateway(mock=True)
        result = await gateway.send_ipaws_alert(
            headline="Test Fire",
            description="Test description",
            area_description="Test area",
            geocodes=["06037"],
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_fire_alert(self) -> None:
        gateway = MassNotificationGateway(mock=True)
        result = await gateway.send_fire_alert(
            building_name="Test Building",
            fire_zone="Kitchen",
            geocodes=["06037"],
        )
        assert "headline" in result

    def test_to_dict(self) -> None:
        gateway = MassNotificationGateway(mock=True)
        d = gateway.to_dict()
        assert "alerts_sent" in d


class TestPostFireAirQuality:
    @pytest.mark.asyncio
    async def test_check_air_quality(self) -> None:
        mon = PostFireAirQualityMonitor(mock=True)
        result = await mon.check_air_quality()
        assert "status" in result
        assert "safe" in result
        assert "values" in result

    def test_generate_report_insufficient_data(self) -> None:
        mon = PostFireAirQualityMonitor(mock=True)
        report = mon.generate_all_clear_report()
        assert report["ready"] is False

    @pytest.mark.asyncio
    async def test_generate_report_with_data(self) -> None:
        mon = PostFireAirQualityMonitor(mock=True)
        mon._suppression_start_time = time.time() - 7200
        for _ in range(5):
            await mon.check_air_quality()
        report = mon.generate_all_clear_report()
        assert "ready" in report

    def test_to_dict(self) -> None:
        mon = PostFireAirQualityMonitor(mock=True)
        d = mon.to_dict()
        assert "monitor_id" in d
