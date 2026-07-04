"""FastAPI web dashboard and API for open-fire-suppression.

# T002 — Real-Time Dashboard API
# T003 — Dashboard WebSocket
# T004 — Historical Data Query
# UI-001..UI-010 — Dashboard Improvements
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from fire_suppression.web.dashboard_ui import DashboardUI, SystemHealth, ZoneStatus

if TYPE_CHECKING:
    from fire_suppression.telemetry.logger import TelemetryLogger

logger = logging.getLogger(__name__)

# In-memory status cache (updated by main loop)
_status_cache: dict = {
    "sensors": {},
    "detection": {},
    "safety": {"state": "disarmed"},
    "power": {},
    "timestamp": time.time(),
}
_status_lock = asyncio.Lock()


async def update_status_cache(status: dict) -> None:
    """Call from main loop to update the dashboard data."""
    async with _status_lock:
        _status_cache.update(status)
        _status_cache["timestamp"] = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the WebSocket broadcast task lifecycle."""
    broadcast_task = asyncio.create_task(_broadcast_loop())
    yield
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="open-fire-suppression Dashboard", lifespan=lifespan)
_clients: list[WebSocket] = []
_dashboard_ui = DashboardUI(mock=True)


# ── API Endpoints ──

@app.get("/")
async def root() -> dict:
    return {"message": "open-fire-suppression API", "version": "0.8.0"}


@app.get("/api/status")
async def api_status() -> dict:
    """Return current system status including all sensor readings and system state.

    # T002 — Real-Time Dashboard API
    """
    async with _status_lock:
        return dict(_status_cache)


@app.get("/api/sensors/{sensor_name}/history")
async def sensor_history(sensor_name: str, limit: int = 100) -> list[dict]:
    """Query historical sensor readings.

    # T004 — Historical Data Query
    """
    async with _status_lock:
        readings = _status_cache.get("sensor_history", {}).get(sensor_name, [])
        return readings[-limit:]


@app.get("/api/events")
async def api_events(limit: int = 50, severity: str | None = None) -> list[dict]:
    """Return recent system events."""
    async with _status_lock:
        events = _status_cache.get("events", [])
        if severity:
            events = [e for e in events if e.get("severity") == severity]
        return events[-limit:]


# ── Module Aggregation ──

@app.get("/api/modules")
async def api_modules() -> dict[str, Any]:
    """Aggregate health/status from all system modules."""
    modules: dict[str, Any] = {}

    # Core subsystems that should always be present
    _try_module(modules, "safety", "fire_suppression.safety.interlock", "SafetyInterlock")
    _try_module(modules, "detection", "fire_suppression.detection.engine", "FireDetectionEngine")
    _try_module(modules, "actuation", "fire_suppression.actuation.relay", "RelayController")
    _try_module(modules, "power", "fire_suppression.power.manager", "PowerManager")
    _try_module(modules, "telemetry", "fire_suppression.telemetry.logger", "TelemetryLogger")
    _try_module(modules, "zones", "fire_suppression.detection.zones", "ZoneManager")

    # Security / Resilience
    _try_module(modules, "hsm", "fire_suppression.diagnostics.hsm_bridge", "HSMBridge")
    _try_module(modules, "ids", "fire_suppression.diagnostics.intrusion_detection", "IntrusionDetectionSystem")
    _try_module(modules, "vault", "fire_suppression.config.secure_vault", "SecureConfigVault")
    _try_module(modules, "file_integrity", "fire_suppression.diagnostics.file_integrity_monitor", "FileIntegrityMonitor")
    _try_module(modules, "blockchain_audit", "fire_suppression.telemetry.blockchain_audit", "BlockchainAuditLog")

    # Bottleneck / watchdog
    _try_module(modules, "engine_timeout", "fire_suppression.detection.engine_timeout", "EngineTimeout")
    _try_module(modules, "db_resilience", "fire_suppression.telemetry.db_resilience", "ResilientDB")
    _try_module(modules, "memory_monitor", "fire_suppression.diagnostics.memory_monitor", "MemoryMonitor")
    _try_module(modules, "store_forward", "fire_suppression.telemetry.store_forward", "StoreForwardQueue")
    _try_module(modules, "config_reload", "fire_suppression.web.config_atomic_reload", "ConfigAtomicReload")
    _try_module(modules, "rtc_sync", "fire_suppression.diagnostics.rtc_sync", "RTCSync")
    _try_module(modules, "watchdog", "fire_suppression.diagnostics.watchdog", "Watchdog")

    # v0.4.0 / v0.5.0 / v0.6.0 modules
    _try_module(modules, "baseline", "fire_suppression.detection.baseline", "EnvironmentalBaseline")
    _try_module(modules, "false_positive_classifier", "fire_suppression.detection.false_positive_classifier", "FalsePositiveClassifier")
    _try_module(modules, "flicker_analyzer", "fire_suppression.detection.flicker_analyzer", "FlickerAnalyzer")
    _try_module(modules, "kalman_fusion", "fire_suppression.detection.kalman_fusion", "KalmanFusion")
    _try_module(modules, "seasonal_adjuster", "fire_suppression.detection.seasonal_adjuster", "SeasonalAdjuster")
    _try_module(modules, "smoke_plume_tracker", "fire_suppression.detection.smoke_plume_tracker", "SmokePlumeTracker")
    _try_module(modules, "tflite_detector", "fire_suppression.detection.tflite_detector", "TFLiteDetector")
    _try_module(modules, "occupancy_aware", "fire_suppression.detection.occupancy_aware", "OccupancyAwareDetector")
    _try_module(modules, "acoustic_fire", "fire_suppression.detection.acoustic_fire_signature", "AcousticFireSignature")
    _try_module(modules, "arc_fault", "fire_suppression.detection.arc_fault_detector", "ArcFaultDetector")
    _try_module(modules, "battery_thermal_runaway", "fire_suppression.detection.battery_thermal_runaway", "BatteryThermalRunaway")
    _try_module(modules, "mmwave_radar", "fire_suppression.detection.mmwave_radar", "mmWaveRadarDetector")
    _try_module(modules, "pressure_differential", "fire_suppression.detection.pressure_differential", "PressureDifferentialDetector")
    _try_module(modules, "satellite_thermal", "fire_suppression.detection.satellite_thermal", "SatelliteThermalMonitor")

    # Actuation modules
    _try_module(modules, "elevator_recall", "fire_suppression.actuation.elevator_recall", "ElevatorRecall")
    _try_module(modules, "hvac_shutdown", "fire_suppression.actuation.hvac_shutdown", "HVACShutdown")
    _try_module(modules, "smart_glass", "fire_suppression.actuation.smart_glass_opacity", "SmartGlassOpacity")
    _try_module(modules, "sprinkler_valves", "fire_suppression.actuation.sprinkler_valves", "SprinklerValveController")
    _try_module(modules, "targeting", "fire_suppression.actuation.targeting", "TargetingSystem")

    # Alerts
    _try_module(modules, "audio_keep_alive", "fire_suppression.alerts.audio_keep_alive", "AudioKeepAlive")
    _try_module(modules, "directional_voice_evac", "fire_suppression.alerts.directional_voice_evac", "DirectionalVoiceEvacuation")
    _try_module(modules, "evacuation_leds", "fire_suppression.alerts.evacuation_leds", "EvacuationLEDController")
    _try_module(modules, "firefighter_ppe", "fire_suppression.alerts.firefighter_ppe_bridge", "FirefighterPPEBridge")
    _try_module(modules, "haptic_alert", "fire_suppression.alerts.haptic_alert", "HapticAlertSystem")
    _try_module(modules, "kenya_sms", "fire_suppression.alerts.kenya_sms", "KenyaSMSNotifier")
    _try_module(modules, "mass_notification", "fire_suppression.alerts.mass_notification_gateway", "MassNotificationGateway")
    _try_module(modules, "phrase_database", "fire_suppression.alerts.phrase_database", "PhraseDatabase")
    _try_module(modules, "voice_alert", "fire_suppression.alerts.voice_alert", "VoiceAlertSystem")

    # Network / building
    _try_module(modules, "drone_recon", "fire_suppression.network.drone_fire_recon", "DroneFireRecon")
    _try_module(modules, "mesh", "fire_suppression.network.mesh", "MeshNetwork")
    _try_module(modules, "smart_building", "fire_suppression.network.smart_building_bridge", "SmartBuildingBridge")

    # Diagnostics / compliance
    _try_module(modules, "compliance", "fire_suppression.diagnostics.compliance", "ComplianceChecker")
    _try_module(modules, "nfpa_compliance", "fire_suppression.diagnostics.nfpa_compliance", "NFPAComplianceChecker")
    _try_module(modules, "predictive_maintenance", "fire_suppression.diagnostics.predictive_maintenance", "PredictiveMaintenance")
    _try_module(modules, "startup_check", "fire_suppression.diagnostics.startup_check", "StartupDiagnostics")
    _try_module(modules, "usb_update_agent", "fire_suppression.diagnostics.usb_update_agent", "USBUpdateAgent")

    # Resilience / fault isolation
    _try_module(modules, "fault_isolation", "fire_suppression.resilience.fault_isolation", "FaultIsolatedExecutor")
    _try_module(modules, "stay_alive", "fire_suppression.resilience.stay_alive", "StayAliveMonitor")

    # Telemetry extras
    _try_module(modules, "aqi_calculator", "fire_suppression.telemetry.aqi_calculator", "AQICalculator")
    _try_module(modules, "audit", "fire_suppression.telemetry.audit", "AuditLog")
    _try_module(modules, "cloud_backup", "fire_suppression.telemetry.cloud_backup", "CloudBackup")
    _try_module(modules, "incident_report", "fire_suppression.telemetry.incident_report", "IncidentReportGenerator")
    _try_module(modules, "mqtt_client", "fire_suppression.telemetry.mqtt_client", "MQTTClient")
    _try_module(modules, "notifier", "fire_suppression.telemetry.notifier", "Notifier")
    _try_module(modules, "post_fire_air_quality", "fire_suppression.telemetry.post_fire_air_quality", "PostFireAirQuality")
    _try_module(modules, "usb_export", "fire_suppression.telemetry.usb_export", "USBDataExporter")

    # Extra sensors
    _try_module(modules, "co_sensor", "fire_suppression.sensors.co_sensor", "COSensor")
    _try_module(modules, "gas_chromatograph", "fire_suppression.sensors.gas_chromatograph", "GasChromatograph")
    _try_module(modules, "lidar_smoke", "fire_suppression.sensors.lidar_smoke", "LiDARSmokeDetector")
    _try_module(modules, "night_vision", "fire_suppression.sensors.night_vision", "NightVisionSystem")
    _try_module(modules, "thermal_drift", "fire_suppression.sensors.thermal_drift", "ThermalDriftCompensator")
    _try_module(modules, "vibration_sensor", "fire_suppression.sensors.vibration_sensor", "VibrationSensor")
    _try_module(modules, "water_ingress", "fire_suppression.sensors.water_ingress", "WaterIngressSensor")

    # Dashboard UI
    _try_module(modules, "dashboard_ui", "fire_suppression.web.dashboard_ui", "DashboardUI")

    # Hermes bridge
    _try_module(modules, "hermes_bridge", "fire_suppression.bridge.hermes_bridge", "HermesBridge")

    # v0.7.0 modules
    _try_module(modules, "alert_prioritizer", "fire_suppression.alerts.alert_prioritizer", "AlertPrioritizer")
    _try_module(modules, "multi_building_console", "fire_suppression.web.multi_building_console", "MultiBuildingConsole")
    _try_module(modules, "self_test_scheduler", "fire_suppression.diagnostics.self_test_scheduler", "SelfTestScheduler")
    _try_module(modules, "fire_marshal_handoff", "fire_suppression.telemetry.fire_marshal_handoff", "FireMarshalHandoff")
    _try_module(modules, "cloud_sitfeed", "fire_suppression.telemetry.cloud_sitfeed", "CloudSituationalAwarenessFeed")
    _try_module(modules, "voice_command", "fire_suppression.alerts.voice_command_interface", "VoiceCommandInterface")
    _try_module(modules, "battery_balancer", "fire_suppression.power.battery_balancer", "SmartBatteryLoadBalancer")
    _try_module(modules, "drift_calibration", "fire_suppression.sensors.drift_calibration", "SensorDriftAutoCalibration")
    _try_module(modules, "occupancy_risk_map", "fire_suppression.detection.occupancy_risk_map", "OccupancyAwareRiskMap")
    _try_module(modules, "regulatory_manifest", "fire_suppression.diagnostics.regulatory_manifest", "RegulatoryFirmwareManifest")

    return {"modules": modules, "timestamp": time.time()}


def _try_module(modules: dict, key: str, module_path: str, class_name: str) -> None:
    """Try to instantiate a module in mock mode and call to_dict() / health_check()."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        instance = cls(mock=True)
        data: dict[str, Any] = {}
        if hasattr(instance, "to_dict"):
            data = instance.to_dict()
        elif hasattr(instance, "health_check"):
            data = instance.health_check()
        elif hasattr(instance, "get_status"):
            data = instance.get_status()  # type: ignore[assignment]
        else:
            data = {"present": True, "note": "no export method"}
        modules[key] = data
    except Exception as exc:
        modules[key] = {"present": False, "error": str(exc)}


# ── Security (v0.5.0) ────────────────────────────────────────────────────────

@app.get("/api/security/hsm")
async def api_hsm_status() -> dict[str, Any]:
    """SEC-002 — Hardware Security Module Bridge status."""
    from fire_suppression.diagnostics.hsm_bridge import HSMBridge

    try:
        hsm = HSMBridge(mock=True)
        return hsm.health_check()
    except Exception as exc:
        logger.warning("HSM health check error: %s", exc)
        return {"feature_id": "SEC-002", "error": str(exc), "healthy": False}


@app.get("/api/security/ids")
async def api_ids_status() -> dict[str, Any]:
    """SEC-003 — Intrusion Detection System status."""
    from fire_suppression.diagnostics.intrusion_detection import IntrusionDetectionSystem

    try:
        ids = IntrusionDetectionSystem(mock=True)
        return ids.to_dict()
    except Exception as exc:
        logger.warning("IDS status error: %s", exc)
        return {"feature_id": "SEC-003", "error": str(exc), "healthy": False}


@app.get("/api/security/vault")
async def api_vault_status() -> dict[str, Any]:
    """SEC-004 — Secure Config Vault status."""
    from fire_suppression.config.secure_vault import SecureConfigVault

    try:
        vault = SecureConfigVault(mock=True)
        return vault.to_dict()
    except Exception as exc:
        logger.warning("Vault status error: %s", exc)
        return {"feature_id": "SEC-004", "error": str(exc), "healthy": False}


# ── Bottleneck Mitigations ───────────────────────────────────────────────────

@app.get("/api/bottlenecks/engine_timeout")
async def api_engine_timeout_status() -> dict[str, Any]:
    """BOT-002 — Detection Engine Timeout status."""
    from fire_suppression.detection.engine_timeout import EngineTimeout

    try:
        et = EngineTimeout(mock=True)
        return et.to_dict()
    except Exception as exc:
        return {"feature_id": "BOT-002", "error": str(exc), "healthy": False}


@app.get("/api/bottlenecks/db_resilience")
async def api_db_resilience_status() -> dict[str, Any]:
    """BOT-003 — SQLite DB Resilience status."""
    from fire_suppression.telemetry.db_resilience import ResilientDB

    try:
        db = ResilientDB(mock=True)
        return db.to_dict()
    except Exception as exc:
        return {"feature_id": "BOT-003", "error": str(exc), "healthy": False}


@app.get("/api/bottlenecks/memory")
async def api_memory_status() -> dict[str, Any]:
    """BOT-004 — Memory Monitor status."""
    from fire_suppression.diagnostics.memory_monitor import MemoryMonitor

    try:
        mm = MemoryMonitor(mock=True)
        return mm.to_dict()
    except Exception as exc:
        return {"feature_id": "BOT-004", "error": str(exc), "healthy": False}


@app.get("/api/bottlenecks/store_forward")
async def api_store_forward_status() -> dict[str, Any]:
    """BOT-005 — Store-and-Forward Queue status."""
    from fire_suppression.telemetry.store_forward import StoreForwardQueue

    try:
        sf = StoreForwardQueue(mock=True)
        return sf.to_dict()
    except Exception as exc:
        return {"feature_id": "BOT-005", "error": str(exc), "healthy": False}


@app.get("/api/bottlenecks/config_reload")
async def api_config_reload_status() -> dict[str, Any]:
    """BOT-007 — Atomic Config Reload status."""
    from fire_suppression.web.config_atomic_reload import ConfigAtomicReload

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as fh:
            fh.write("system:\\n  name: test\\n")
            tmp = fh.name
        ca = ConfigAtomicReload(tmp, mock=True)
        return ca.to_dict()
    except Exception as exc:
        return {"feature_id": "BOT-007", "error": str(exc), "healthy": False}


@app.get("/api/bottlenecks/rtc")
async def api_rtc_status() -> dict[str, Any]:
    """BOT-009 — RTC/NTP Sync status."""
    from fire_suppression.diagnostics.rtc_sync import RTCSync

    try:
        rtc = RTCSync(mock=True)
        return rtc.to_dict()
    except Exception as exc:
        return {"feature_id": "BOT-009", "error": str(exc), "healthy": False}


@app.get("/api/bottlenecks/watchdog")
async def api_watchdog_status() -> dict[str, Any]:
    """BOT-010 — System Watchdog status."""
    from fire_suppression.diagnostics.watchdog import Watchdog

    try:
        wd = Watchdog(mock=True)
        return wd.to_dict()
    except Exception as exc:
        return {"feature_id": "BOT-010", "error": str(exc), "healthy": False}




# ── Dashboard UI Endpoints ──

@app.get("/api/health")
async def api_health() -> dict:
    """Return overall system health for the dashboard."""
    return {"system_health": _dashboard_ui._health}


@app.get("/api/zones")
async def api_zones() -> dict:
    """Return zone risk list for the dashboard."""
    zones = list(_dashboard_ui._zones.values())
    if not zones:
        # Provide demo zones when no real data exists yet.
        demo = [
            ZoneStatus(zone_id="kitchen", name="Kitchen", temperature_c=42.0, smoke_ppm=12.0, co_ppm=0.5, occupancy_count=1, alert_level="normal", last_update=time.time(), sensor_health={"mq2": "ok", "temp": "ok"}),
            ZoneStatus(zone_id="hallway", name="Hallway", temperature_c=24.0, smoke_ppm=2.0, co_ppm=0.0, occupancy_count=0, alert_level="normal", last_update=time.time(), sensor_health={"mq2": "ok", "temp": "ok"}),
            ZoneStatus(zone_id="garage", name="Garage", temperature_c=31.0, smoke_ppm=5.0, co_ppm=0.2, occupancy_count=0, alert_level="normal", last_update=time.time(), sensor_health={"mq2": "ok", "temp": "ok"}),
        ]
        for z in demo:
            _dashboard_ui.update_zone(z)
        zones = list(_dashboard_ui._zones.values())
    result = []
    for z in zones:
        risk = _dashboard_ui.calculate_fire_risk(z.zone_id)
        result.append({**z.__dict__, "risk_percent": risk.get("risk_percent", 0), "risk_level": risk.get("alert_level", "normal")})
    return {"zones": result, "timestamp": time.time()}


@app.get("/api/sparkline")
async def api_sparkline(zone_id: str, sensor_type: str, duration: int = 30) -> dict:
    """Return sparkline data for a sensor in a zone."""
    return _dashboard_ui.get_sensor_sparkline(zone_id, sensor_type, duration)


@app.post("/api/emergency")
async def api_emergency(payload: dict) -> dict:
    """Execute one-click emergency action."""
    action = payload.get("action", "")
    zone_id = payload.get("zone_id")
    result = await _dashboard_ui.emergency_action(action, zone_id)
    return result


@app.get("/api/theme")
async def api_theme() -> dict:
    """Return current dashboard theme."""
    return {"theme": _dashboard_ui._theme}


@app.post("/api/theme")
async def api_theme_set(payload: dict) -> dict:
    """Set dashboard theme."""
    return _dashboard_ui.set_theme(payload.get("theme"))


@app.get("/api/language")
async def api_language() -> dict:
    """Return current dashboard language."""
    return {"language": _dashboard_ui._language}


@app.post("/api/language")
async def api_language_set(payload: dict) -> dict:
    """Set dashboard language."""
    return _dashboard_ui.set_language(payload.get("language", "en"))


@app.get("/api/accessibility")
async def api_accessibility() -> dict:
    """Return accessibility mode status."""
    return {"enabled": _dashboard_ui._accessibility_mode}


@app.post("/api/accessibility")
async def api_accessibility_set(payload: dict) -> dict:
    """Toggle accessibility mode."""
    return _dashboard_ui.set_accessibility_mode(payload.get("enabled", False))

# ── Dashboard HTML ──

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """Serve a professional HTML dashboard with real-time WebSocket updates."""
    return DASHBOARD_HTML


# ── WebSocket ──

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Push real-time status updates at 1 Hz with keep-alive ping/pong.

    # T003 — Dashboard WebSocket
    """
    await websocket.accept()
    _clients.append(websocket)
    logger.info("WebSocket client connected (total: %d)", len(_clients))
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "ts": time.time()}))
                elif msg.get("action") == "subscribe":
                    await websocket.send_text(json.dumps({"type": "subscribed", "channels": msg.get("channels", ["status"])}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _clients:
            _clients.remove(websocket)
        logger.info("WebSocket client disconnected (total: %d)", len(_clients))


async def _broadcast_loop() -> None:
    """Broadcast status updates to all connected WebSocket clients at 1 Hz."""
    while True:
        await asyncio.sleep(1.0)
        if not _clients:
            continue
        async with _status_lock:
            data = dict(_status_cache)
            # Enrich with dashboard UI computed data
            zones = list(_dashboard_ui._zones.values())
            if zones:
                enriched_zones = []
                for z in zones:
                    risk = _dashboard_ui.calculate_fire_risk(z.zone_id)
                    enriched_zones.append({**z.__dict__, "risk_percent": risk.get("risk_percent", 0), "risk_level": risk.get("alert_level", "normal")})
                data["zones"] = enriched_zones
            if _dashboard_ui._health.last_update:
                data["system_health"] = _dashboard_ui._health.__dict__
            payload = json.dumps({"type": "status", "data": data})
        disconnected = []
        for ws in _clients:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in _clients:
                _clients.remove(ws)




# ── Dashboard UI Endpoints ──

@app.get("/api/health")
async def api_health() -> dict:
    """Return overall system health for the dashboard."""
    return {"system_health": _dashboard_ui._health}


@app.get("/api/zones")
async def api_zones() -> dict:
    """Return zone risk list for the dashboard."""
    zones = list(_dashboard_ui._zones.values())
    if not zones:
        # Provide demo zones when no real data exists yet.
        demo = [
            ZoneStatus(zone_id="kitchen", name="Kitchen", temperature_c=42.0, smoke_ppm=12.0, co_ppm=0.5, occupancy_count=1, alert_level="normal", last_update=time.time(), sensor_health={"mq2": "ok", "temp": "ok"}),
            ZoneStatus(zone_id="hallway", name="Hallway", temperature_c=24.0, smoke_ppm=2.0, co_ppm=0.0, occupancy_count=0, alert_level="normal", last_update=time.time(), sensor_health={"mq2": "ok", "temp": "ok"}),
            ZoneStatus(zone_id="garage", name="Garage", temperature_c=31.0, smoke_ppm=5.0, co_ppm=0.2, occupancy_count=0, alert_level="normal", last_update=time.time(), sensor_health={"mq2": "ok", "temp": "ok"}),
        ]
        for z in demo:
            _dashboard_ui.update_zone(z)
        zones = list(_dashboard_ui._zones.values())
    result = []
    for z in zones:
        risk = _dashboard_ui.calculate_fire_risk(z.zone_id)
        result.append({**z.__dict__, "risk_percent": risk.get("risk_percent", 0), "risk_level": risk.get("alert_level", "normal")})
    return {"zones": result, "timestamp": time.time()}


@app.get("/api/sparkline")
async def api_sparkline(zone_id: str, sensor_type: str, duration: int = 30) -> dict:
    """Return sparkline data for a sensor in a zone."""
    return _dashboard_ui.get_sensor_sparkline(zone_id, sensor_type, duration)


@app.post("/api/emergency")
async def api_emergency(payload: dict) -> dict:
    """Execute one-click emergency action."""
    action = payload.get("action", "")
    zone_id = payload.get("zone_id")
    result = await _dashboard_ui.emergency_action(action, zone_id)
    return result


@app.get("/api/theme")
async def api_theme() -> dict:
    """Return current dashboard theme."""
    return {"theme": _dashboard_ui._theme}


@app.post("/api/theme")
async def api_theme_set(payload: dict) -> dict:
    """Set dashboard theme."""
    return _dashboard_ui.set_theme(payload.get("theme"))


@app.get("/api/language")
async def api_language() -> dict:
    """Return current dashboard language."""
    return {"language": _dashboard_ui._language}


@app.post("/api/language")
async def api_language_set(payload: dict) -> dict:
    """Set dashboard language."""
    return _dashboard_ui.set_language(payload.get("language", "en"))


@app.get("/api/accessibility")
async def api_accessibility() -> dict:
    """Return accessibility mode status."""
    return {"enabled": _dashboard_ui._accessibility_mode}


@app.post("/api/accessibility")
async def api_accessibility_set(payload: dict) -> dict:
    """Toggle accessibility mode."""
    return _dashboard_ui.set_accessibility_mode(payload.get("enabled", False))

# ── Dashboard HTML ──

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>open-fire-suppression Dashboard</title>
<style>
:root {
  --bg: #0b0f19;
  --panel: #121827;
  --panel-border: #1e293b;
  --text: #e2e8f0;
  --muted: #94a3b8;
  --accent: #0ea5e9;
  --ok: #22c55e;
  --warn: #f59e0b;
  --alert: #f97316;
  --crit: #ef4444;
  --info: #3b82f6;
  --font: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  --radius: 12px;
  --shadow: 0 1px 2px rgba(0,0,0,.35);
}
html, body { height: 100%; }
body {
  margin: 0; padding: 0; font-family: var(--font); background: var(--bg); color: var(--text);
  display: flex; flex-direction: column;
}
body.light {
  --bg: #f1f2f6;
  --panel: #ffffff;
  --panel-border: #dfe4ea;
  --text: #2f3542;
  --muted: #57606f;
  --shadow: 0 1px 3px rgba(0,0,0,.1);
}
body.high-contrast {
  --bg: #000000;
  --panel: #000000;
  --panel-border: #ffffff;
  --text: #ffffff;
  --muted: #cccccc;
  --accent: #00ffff;
  --ok: #00ff00;
  --warn: #ffff00;
  --alert: #ff9900;
  --crit: #ff0000;
  --info: #00ccff;
}
body.reduced-motion * { animation: none !important; transition: none !important; }
header {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: var(--panel); border-bottom: 1px solid var(--panel-border);
  box-shadow: var(--shadow);
  flex-wrap: wrap; gap: 10px;
}
header h1 { font-size: 1.1rem; margin: 0; display: flex; align-items: center; gap: 8px; }
.badge {
  font-size: .75rem; padding: 2px 8px; border-radius: 999px; background: #334155; color: #cbd5e1;
}
body.light .badge { background: #e2e8f0; color: #475569; }
#conn-status { font-size: .8rem; color: var(--muted); white-space: nowrap; }
#conn-status.online { color: var(--ok); }
#conn-status.offline { color: var(--crit); }
#conn-status.reconnect { color: var(--warn); }
.controls { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
main { flex: 1; overflow-y: auto; padding: 12px 16px 100px; }
.grid { display: grid; gap: 12px; }
@media (min-width: 1200px) {
  .grid { grid-template-columns: repeat(4, 1fr); }
  .col-span-2 { grid-column: span 2; }
  .col-span-3 { grid-column: span 3; }
  .col-span-4 { grid-column: span 4; }
}
@media (min-width: 768px) and (max-width: 1199px) {
  .grid { grid-template-columns: repeat(2, 1fr); }
  .col-span-2 { grid-column: span 2; }
  .col-span-3 { grid-column: span 2; }
  .col-span-4 { grid-column: span 2; }
}
@media (max-width: 767px) {
  .grid { grid-template-columns: 1fr; }
  .col-span-2, .col-span-3, .col-span-4 { grid-column: span 1; }
  header h1 { font-size: .95rem; }
}
.card {
  background: var(--panel); border: 1px solid var(--panel-border); border-radius: var(--radius);
  padding: 14px; display: flex; flex-direction: column; gap: 10px;
  box-shadow: var(--shadow);
}
.card h2 { font-size: .85rem; text-transform: uppercase; letter-spacing: .08em; margin: 0; color: var(--muted); }
.row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.value { font-variant-numeric: tabular-nums; }
.big { font-size: 1.6rem; font-weight: 700; }
.state-clear { color: var(--ok); }
.state-warning { color: var(--warn); }
.state-alert { color: var(--alert); }
.state-confirmed { color: var(--crit); }
.state-unknown { color: var(--muted); }
.bar { height: 6px; border-radius: 999px; background: #1e293b; overflow: hidden; }
body.light .bar { background: #e2e8f0; }
.bar > i { display: block; height: 100%; border-radius: 999px; background: var(--accent); transition: width .3s ease; }
.battery-low .bar > i { background: var(--warn); }
.battery-critical .bar > i { background: var(--crit); }
.battery-ok .bar > i { background: var(--ok); }
.sensor-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px; }
.sensor-item {
  background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px;
  position: relative; overflow: hidden;
}
body.light .sensor-item { background: #f8fafc; border-color: #e2e8f0; }
.sensor-item .name { font-size: .8rem; color: var(--muted); display: flex; align-items: center; justify-content: space-between; }
.sensor-item .val { font-size: 1.1rem; font-weight: 600; }
.sensor-item .spark { height: 28px; margin-top: 6px; }
.sensor-ok { border-left: 3px solid var(--ok); }
.sensor-warn { border-left: 3px solid var(--warn); }
.sensor-error { border-left: 3px solid var(--crit); }
.module-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.mod {
  background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px;
  font-size: .8rem;
}
body.light .mod { background: #f8fafc; border-color: #e2e8f0; }
.mod .mod-name { color: var(--muted); }
.mod .mod-status { font-weight: 600; }
.mod-ok .mod-status { color: var(--ok); }
.mod-warn .mod-status { color: var(--warn); }
.mod-err .mod-status { color: var(--crit); }
#log-wrap { max-height: 220px; overflow-y: auto; }
#log { display: flex; flex-direction: column; gap: 6px; font-size: .82rem; }
.log-entry { display: flex; gap: 8px; }
.log-time { color: #64748b; font-variant-numeric: tabular-nums; white-space: nowrap; }
body.light .log-time { color: #64748b; }
.log-msg { color: var(--text); }
.log-severity-critical { color: var(--crit); font-weight: 700; }
.log-severity-warning { color: var(--warn); }
.log-severity-info { color: var(--info); }
footer {
  position: fixed; bottom: 0; left: 0; right: 0;
  padding: 8px 16px; background: rgba(11,15,25,.92); border-top: 1px solid var(--panel-border);
  display: flex; align-items: center; justify-content: space-between; font-size: .78rem; color: var(--muted);
}
body.light footer { background: rgba(241,242,246,.95); }
#last-update { font-variant-numeric: tabular-nums; }
button, .btn {
  background: #1e293b; color: var(--text); border: 1px solid #334155; border-radius: 6px; padding: 6px 12px; cursor: pointer; font: inherit; font-size: .78rem; transition: background .15s ease;
}
body.light button, body.light .btn { background: #e2e8f0; border-color: #cbd5e1; color: #334155; }
button:hover, .btn:hover { background: #334155; }
body.light button:hover, body.light .btn:hover { background: #cbd5e1; }
button.primary { background: var(--accent); color: #0b0f19; border-color: var(--accent); font-weight: 600; }
button.crit { background: var(--crit); color: #fff; border-color: var(--crit); }
button.warn { background: var(--warn); color: #000; border-color: var(--warn); }
button:disabled { opacity: .6; cursor: not-allowed; }
.alert-banner {
  border-radius: var(--radius); padding: 12px 16px; margin-bottom: 12px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
}
.alert-banner.clear { background: rgba(34,197,94,.15); color: var(--ok); border: 1px solid rgba(34,197,94,.3); }
.alert-banner.warning { background: rgba(245,158,11,.15); color: var(--warn); border: 1px solid rgba(245,158,11,.3); }
.alert-banner.alert { background: rgba(249,115,22,.15); color: var(--alert); border: 1px solid rgba(249,115,22,.3); }
.alert-banner.confirmed { background: rgba(239,68,68,.2); color: var(--crit); border: 1px solid rgba(239,68,68,.4); animation: pulse-alert 2s infinite; }
body.light .alert-banner.confirmed { animation: pulse-alert 2s infinite; }
@keyframes pulse-alert { 0% { box-shadow: 0 0 0 0 rgba(239,68,68,.4); } 70% { box-shadow: 0 0 0 10px rgba(239,68,68,0); } 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); } }
.empty-state { color: var(--muted); font-size: .85rem; text-align: center; padding: 20px 10px; }
.skeleton { background: linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%); background-size: 200% 100%; animation: skeleton 1.5s infinite; border-radius: 4px; height: 1em; }
body.light .skeleton { background: linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%); background-size: 200% 100%; }
@keyframes skeleton { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.zone-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.zone-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; }
body.light .zone-card { background: #f8fafc; border-color: #e2e8f0; }
.zone-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.zone-name { font-weight: 600; }
.zone-risk { font-size: 1.4rem; font-weight: 700; }
.zone-risk.normal { color: var(--ok); }
.zone-risk.warning { color: var(--warn); }
.zone-risk.alert { color: var(--alert); }
.zone-risk.critical { color: var(--crit); }
.zone-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: .8rem; }
.zone-metric { display: flex; justify-content: space-between; }
.zone-metric span:first-child { color: var(--muted); }
.resource-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.resource-item { display: flex; flex-direction: column; gap: 4px; }
.resource-label { font-size: .75rem; color: var(--muted); display: flex; justify-content: space-between; }
.resource-bar { height: 6px; border-radius: 999px; background: #1e293b; overflow: hidden; }
body.light .resource-bar { background: #e2e8f0; }
.resource-bar > i { display: block; height: 100%; border-radius: 999px; }
.resource-bar > i.good { background: var(--ok); }
.resource-bar > i.warn { background: var(--warn); }
.resource-bar > i.crit { background: var(--crit); }
.confirm-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.7); z-index: 100;
  display: none; align-items: center; justify-content: center; padding: 16px;
}
.confirm-overlay.active { display: flex; }
.confirm-box { background: var(--panel); border: 1px solid var(--panel-border); border-radius: var(--radius); padding: 20px; max-width: 360px; width: 100%; }
.confirm-box p { margin: 0 0 16px; }
.confirm-actions { display: flex; gap: 8px; justify-content: flex-end; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
</style>
</head>
<body>
<div class="confirm-overlay" id="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
  <div class="confirm-box">
    <p id="confirm-title">Confirm action?</p>
    <div class="confirm-actions">
      <button id="confirm-cancel">Cancel</button>
      <button id="confirm-ok" class="primary">OK</button>
    </div>
  </div>
</div>
<header>
  <h1>open-fire-suppression <span class="badge">v0.8.0</span></h1>
  <div class="controls">
    <button id="btn-evacuate" class="crit">Evacuate</button>
    <button id="btn-test">Test</button>
    <button id="btn-silence">Silence</button>
    <button id="btn-reset">Reset</button>
    <button id="theme-btn" title="Theme">Dark</button>
    <button id="a11y-btn" title="Accessibility">A11y</button>
    <button id="lang-btn" title="EN / SW">EN</button>
    <span id="conn-status" class="offline" aria-live="polite">● disconnected</span>
  </div>
</header>
<main>
  <div id="alert-banner" class="alert-banner clear" role="status" aria-live="assertive">
    <span id="alert-title">System clear</span>
    <span id="alert-time">—</span>
  </div>
  <div class="grid">
    <!-- System status -->
    <div class="card col-span-2">
      <h2 id="lbl-system-status">System Status</h2>
      <div class="row"><div>Fire State</div><div id="fire-state" class="big state-unknown">UNKNOWN</div></div>
      <div class="row"><div>Confidence</div><div class="value"><span id="confidence">0.00</span> %</div></div>
      <div class="row"><div>Safety</div><div id="safety-state" class="value state-unknown">UNKNOWN</div></div>
      <div class="row"><div>Latency</div><div class="value"><span id="latency">0</span> ms</div></div>
      <div class="row"><div>Actuation</div><div id="actuation-state" class="value state-unknown">UNKNOWN</div></div>
    </div>

    <!-- Power -->
    <div class="card" id="power-card">
      <h2 id="lbl-power">Power</h2>
      <div class="row"><div>Source</div><div id="power-source" class="value">AC</div></div>
      <div class="row"><div>Battery</div><div class="value"><span id="battery">0</span> %</div></div>
      <div class="row"><div>Charging</div><div id="charging" class="value">—</div></div>
      <div class="bar"><i id="battery-bar" style="width:0%"></i></div>
    </div>

    <!-- Detection -->
    <div class="card">
      <h2 id="lbl-detection">Detection</h2>
      <div class="row"><div>State</div><div id="det-state" class="value state-unknown">CLEAR</div></div>
      <div class="row"><div>Triggered</div><div id="det-triggered" class="value">—</div></div>
      <div class="row"><div>Reason</div><div id="det-reason" class="value" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">—</div></div>
    </div>

    <!-- System Resources -->
    <div class="card col-span-2">
      <h2 id="lbl-resources">System Resources</h2>
      <div class="resource-grid" id="resources">
        <div class="resource-item"><div class="resource-label"><span>CPU</span><span id="cpu-val">—</span></div><div class="resource-bar"><i id="cpu-bar" style="width:0%"></i></div></div>
        <div class="resource-item"><div class="resource-label"><span>Memory</span><span id="mem-val">—</span></div><div class="resource-bar"><i id="mem-bar" style="width:0%"></i></div></div>
        <div class="resource-item"><div class="resource-label"><span>Disk</span><span id="disk-val">—</span></div><div class="resource-bar"><i id="disk-bar" style="width:0%"></i></div></div>
        <div class="resource-item"><div class="resource-label"><span>Network</span><span id="net-val">—</span></div><div class="resource-bar"><i id="net-bar" style="width:0%"></i></div></div>
      </div>
    </div>

    <!-- Zones / Risk -->
    <div class="card col-span-2">
      <h2 id="lbl-zones">Zone Risk</h2>
      <div id="zones" class="zone-grid"><div class="empty-state">Waiting for zone data...</div></div>
    </div>

    <!-- Sensors -->
    <div class="card col-span-2">
      <h2 id="lbl-sensors">Sensor Readings</h2>
      <div id="sensors" class="sensor-grid"><div class="empty-state">Waiting for sensor data...</div></div>
    </div>

    <!-- Module Health -->
    <div class="card col-span-2">
      <h2 id="lbl-modules">Module Health</h2>
      <div id="modules" class="module-grid"><div class="empty-state">Waiting for module data...</div></div>
    </div>

    <!-- Event Log -->
    <div class="card col-span-4">
      <h2 id="lbl-events">Event Log</h2>
      <div id="log-wrap"><div id="log"><div class="empty-state">Waiting for events...</div></div></div>
    </div>
  </div>
</main>
<footer>
  <div id="last-update">Updated: —</div>
  <div>open-fire-suppression · Dashboard UI v0.8.0</div>
</footer>
<script>
(function () {
  const $ = id => document.getElementById(id);
  const fmtTime = ts => {
    try { return new Date(ts * 1000).toLocaleTimeString(); } catch (e) { return '—'; }
  };
  const tr = {
    en: {
      'lbl-system-status': 'System Status',
      'lbl-power': 'Power',
      'lbl-detection': 'Detection',
      'lbl-sensors': 'Sensor Readings',
      'lbl-modules': 'Module Health',
      'lbl-events': 'Event Log',
      'lbl-resources': 'System Resources',
      'lbl-zones': 'Zone Risk',
      'btn-evacuate': 'Evacuate',
      'btn-test': 'Test',
      'btn-silence': 'Silence',
      'btn-reset': 'Reset',
      'theme-btn': 'Dark',
      'a11y-btn': 'A11y',
      disconnected: '● disconnected',
      online: '● online',
      reconnecting: '● reconnecting…',
      'alert-clear': 'System clear',
      'alert-warning': 'Warning condition',
      'alert-alert': 'Alert condition',
      'alert-confirmed': 'FIRE CONFIRMED',
      confirm_evacuate: 'Initiate building evacuation?',
      confirm_silence: 'Silence alarms for 5 minutes?',
      confirm_reset: 'Reset system to normal state?',
      cancel: 'Cancel',
      ok: 'OK',
      'empty-sensors': 'Waiting for sensor data...',
      'empty-modules': 'Waiting for module data...',
      'empty-events': 'Waiting for events...',
      'empty-zones': 'Waiting for zone data...',
    },
    sw: {
      'lbl-system-status': 'Hali ya Mfumo',
      'lbl-power': 'Nguvu',
      'lbl-detection': 'Ugunduzi',
      'lbl-sensors': 'Visomaji vya Sensaa',
      'lbl-modules': 'Hali ya Moduli',
      'lbl-events': 'Kumbukumbu ya Tukio',
      'lbl-resources': 'Rasilimali za Mfumo',
      'lbl-zones': 'Hatari ya Eneo',
      'btn-evacuate': 'Ondoka',
      'btn-test': 'Jaribu',
      'btn-silence': 'Nyamazisha',
      'btn-reset': 'Weka upya',
      'theme-btn': 'Giza',
      'a11y-btn': 'A11y',
      disconnected: '● kimekatika',
      online: '● mtandaoni',
      reconnecting: '● kuunganisha upya…',
      'alert-clear': 'Mfumo salama',
      'alert-warning': 'Hali ya onyo',
      'alert-alert': 'Hali ya tahadhari',
      'alert-confirmed': 'MOTO UMEOTHIBITISHWA',
      confirm_evacuate: 'Anzisha kutoka jengoni?',
      confirm_silence: 'Nyamazisha kengele kwa dakika 5?',
      confirm_reset: 'Weka upya mfumo hadi hali ya kawaida?',
      cancel: 'Ghairi',
      ok: 'Sawa',
      'empty-sensors': 'Inasubiri data ya sensaa...',
      'empty-modules': 'Inasubiri data ya moduli...',
      'empty-events': 'Inasubiri matukio...',
      'empty-zones': 'Inasubiri data ya eneo...',
    }
  };
  let lang = localStorage.getItem('fire_lang') || 'en';
  let theme = localStorage.getItem('fire_theme') || 'dark';
  let highContrast = localStorage.getItem('fire_high_contrast') === 'true';
  let reducedMotion = localStorage.getItem('fire_reduced_motion') === 'true' || window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function applyLang() {
    $('lang-btn').textContent = lang.toUpperCase();
    const labels = tr[lang];
    Object.keys(labels).forEach(k => {
      const el = $(k);
      if (el) el.textContent = labels[k];
    });
    localStorage.setItem('fire_lang', lang);
    updateConnText();
    updateAlertText();
  }
  function applyTheme() {
    document.body.classList.remove('light', 'high-contrast', 'reduced-motion');
    if (theme === 'light') document.body.classList.add('light');
    if (theme === 'auto') {
      const hour = new Date().getHours();
      if (hour < 6 || hour >= 18) document.body.classList.remove('light');
      else document.body.classList.add('light');
    }
    if (highContrast) document.body.classList.add('high-contrast');
    if (reducedMotion) document.body.classList.add('reduced-motion');
    $('theme-btn').textContent = tr[lang]['theme-btn'] + (theme === 'auto' ? '/A' : '');
    localStorage.setItem('fire_theme', theme);
    localStorage.setItem('fire_high_contrast', highContrast);
    localStorage.setItem('fire_reduced_motion', reducedMotion);
  }
  function updateConnText() {
    const el = $('conn-status');
    if (el.classList.contains('online')) el.textContent = tr[lang].online;
    else if (el.classList.contains('reconnect')) el.textContent = tr[lang].reconnecting;
    else el.textContent = tr[lang].disconnected;
  }
  function updateAlertText() {
    const banner = $('alert-banner');
    const title = $('alert-title');
    if (banner.classList.contains('clear')) title.textContent = tr[lang]['alert-clear'];
    else if (banner.classList.contains('warning')) title.textContent = tr[lang]['alert-warning'];
    else if (banner.classList.contains('alert')) title.textContent = tr[lang]['alert-alert'];
    else if (banner.classList.contains('confirmed')) title.textContent = tr[lang]['alert-confirmed'];
  }
  $('lang-btn').addEventListener('click', () => { lang = lang === 'en' ? 'sw' : 'en'; applyLang(); applyTheme(); });
  $('theme-btn').addEventListener('click', () => { theme = theme === 'dark' ? 'light' : (theme === 'light' ? 'auto' : 'dark'); applyTheme(); });
  $('a11y-btn').addEventListener('click', () => {
    if (!highContrast && !reducedMotion) { highContrast = true; }
    else if (highContrast && !reducedMotion) { reducedMotion = true; }
    else { highContrast = false; reducedMotion = false; }
    applyTheme();
  });

  let ws = null;
  let reconnectTimer = null;
  let reconnectDelay = 1;
  let lastPing = 0;
  let pingTimer = null;
  let modulesLoaded = false;
  let hasReceivedStatus = false;

  const stateClass = s => {
    const v = (s || '').toLowerCase();
    if (v === 'clear') return 'state-clear';
    if (v === 'warning') return 'state-warning';
    if (v === 'alert') return 'state-alert';
    if (v === 'confirmed') return 'state-confirmed';
    return 'state-unknown';
  };
  const alertClass = s => {
    const v = (s || '').toLowerCase();
    if (v === 'clear') return 'clear';
    if (v === 'warning') return 'warning';
    if (v === 'alert') return 'alert';
    if (v === 'confirmed') return 'confirmed';
    return 'clear';
  };

  function setConn(status) {
    const el = $('conn-status');
    el.className = status;
    updateConnText();
  }

  function connect() {
    if (ws) { try { ws.close(); } catch (e) {} ws = null; }
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.onopen = () => {
      setConn('online');
      reconnectDelay = 1;
      lastPing = Date.now();
      if (pingTimer) clearInterval(pingTimer);
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: 'ping' }));
          if (Date.now() - lastPing > 15000) ws.close();
        }
      }, 5000);
      if (!modulesLoaded) loadModules();
      if (!hasReceivedStatus) fetchStatus();
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'pong') { lastPing = Date.now(); return; }
        if (msg.type !== 'status') return;
        hasReceivedStatus = true;
        render(msg.data);
      } catch (e) {}
    };
    ws.onclose = () => {
      setConn('offline');
      if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
      scheduleReconnect();
    };
    ws.onerror = () => { ws.close(); };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    setConn('reconnect');
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      reconnectDelay = Math.min(reconnectDelay * 2, 30);
      connect();
    }, reconnectDelay * 1000);
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      hasReceivedStatus = true;
      render(data);
    } catch (e) {}
  }

  async function loadModules() {
    try {
      const res = await fetch('/api/modules');
      const json = await res.json();
      modulesLoaded = true;
      renderModules(json.modules || {});
    } catch (e) {}
  }

  async function loadZones() {
    try {
      const res = await fetch('/api/zones');
      const json = await res.json();
      renderZones(json.zones || []);
    } catch (e) {}
  }

  async function loadResources() {
    try {
      const res = await fetch('/api/health');
      const json = await res.json();
      renderResources(json.system_health || {});
    } catch (e) {}
  }

  function setResourceBar(id, val) {
    const bar = $(id + '-bar');
    const num = $(id + '-val');
    if (!bar || !num) return;
    const pct = Math.max(0, Math.min(100, val || 0));
    bar.style.width = pct + '%';
    bar.className = pct > 90 ? 'crit' : (pct > 75 ? 'warn' : 'good');
    num.textContent = pct.toFixed(0) + '%';
  }

  function renderResources(health) {
    setResourceBar('cpu', health.cpu_percent);
    setResourceBar('mem', health.memory_percent);
    setResourceBar('disk', health.disk_percent);
    const net = health.network_status || 'online';
    $('net-val').textContent = net;
    const netBar = $('net-bar');
    const netPct = net === 'online' ? 100 : (net === 'degraded' ? 50 : 0);
    netBar.style.width = netPct + '%';
    netBar.className = net === 'online' ? 'good' : (net === 'degraded' ? 'warn' : 'crit');
  }

  function sparkline(readings) {
    if (!readings || readings.length < 2) return '';
    const w = 100, h = 28;
    const vals = readings.map(r => r.value);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = max - min || 1;
    const points = vals.map((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" class="spark" aria-hidden="true"><polyline fill="none" stroke="var(--accent)" stroke-width="2" points="${points}"/></svg>`;
  }

  function renderModules(modules) {
    const container = $('modules');
    container.innerHTML = '';
    const entries = Object.entries(modules);
    if (entries.length === 0) {
      container.innerHTML = `<div class="empty-state">${tr[lang]['empty-modules']}</div>`;
      return;
    }
    entries.forEach(([name, data]) => {
      const div = document.createElement('div');
      let status = 'OK';
      if (data.error || data.healthy === false || data.present === false) status = 'ERROR';
      else if (data.degraded) status = 'DEGRADED';
      const stClass = status === 'OK' ? 'mod-ok' : (status === 'DEGRADED' ? 'mod-warn' : 'mod-err');
      div.className = 'mod ' + stClass;
      const nameSpan = document.createElement('div'); nameSpan.className = 'mod-name'; nameSpan.textContent = name;
      const statusSpan = document.createElement('div'); statusSpan.className = 'mod-status'; statusSpan.textContent = status;
      div.appendChild(nameSpan); div.appendChild(statusSpan);
      container.appendChild(div);
    });
  }

  function renderZones(zones) {
    const container = $('zones');
    container.innerHTML = '';
    if (!zones || zones.length === 0) {
      container.innerHTML = `<div class="empty-state">${tr[lang]['empty-zones']}</div>`;
      return;
    }
    zones.forEach(z => {
      const risk = z.risk_percent || 0;
      const level = risk >= 80 ? 'critical' : (risk >= 60 ? 'alert' : (risk >= 40 ? 'warning' : 'normal'));
      const div = document.createElement('div');
      div.className = 'zone-card';
      div.innerHTML = `
        <div class="zone-header"><span class="zone-name">${escapeHtml(z.name || z.zone_id)}</span><span class="zone-risk ${level}">${risk.toFixed(0)}%</span></div>
        <div class="zone-metrics">
          <div class="zone-metric"><span>Temp</span><span>${(z.temperature_c || 0).toFixed(1)} C</span></div>
          <div class="zone-metric"><span>Smoke</span><span>${(z.smoke_ppm || 0).toFixed(1)}</span></div>
          <div class="zone-metric"><span>CO</span><span>${(z.co_ppm || 0).toFixed(1)}</span></div>
          <div class="zone-metric"><span>Occ</span><span>${z.occupancy_count || 0}</span></div>
        </div>`;
      container.appendChild(div);
    });
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function render(data) {
    const det = data.detection || {};
    const state = det.state || 'CLEAR';
    const fEl = $('fire-state');
    fEl.textContent = state.toUpperCase();
    fEl.className = 'big ' + stateClass(state);
    $('confidence').textContent = ((det.confidence || 0) * 100).toFixed(1);
    $('latency').textContent = (det.latency_ms || 0).toFixed(0);

    const banner = $('alert-banner');
    banner.className = 'alert-banner ' + alertClass(state);
    $('alert-time').textContent = fmtTime(data.timestamp || Date.now()/1000);
    updateAlertText();

    const safety = data.safety || {};
    const sEl = $('safety-state');
    sEl.textContent = (safety.state || 'unknown').toUpperCase();
    sEl.className = 'value ' + stateClass(safety.state);

    const act = data.actuation || {};
    const aEl = $('actuation-state');
    aEl.textContent = (act.state || 'idle').toUpperCase();
    aEl.className = 'value ' + stateClass(act.state);

    const power = data.power || {};
    $('power-source').textContent = (power.source || 'AC').toUpperCase();
    const bat = power.battery_percent || 0;
    $('battery').textContent = bat.toFixed(0);
    $('charging').textContent = power.is_charging ? 'YES' : 'NO';
    $('battery-bar').style.width = Math.max(0, Math.min(100, bat)) + '%';
    const powerCard = $('power-card');
    powerCard.classList.remove('battery-ok','battery-low','battery-critical');
    if (bat <= 5) powerCard.classList.add('battery-critical');
    else if (bat <= 20) powerCard.classList.add('battery-low');
    else powerCard.classList.add('battery-ok');

    $('det-state').textContent = state.toUpperCase();
    $('det-state').className = 'value ' + stateClass(state);
    const trig = (det.triggered_sensors || []).join(', ') || '—';
    $('det-triggered').textContent = trig;
    $('det-triggered').title = trig;
    $('det-reason').textContent = det.reason || '—';
    $('det-reason').title = det.reason || '';

    const sensorsDiv = $('sensors');
    sensorsDiv.innerHTML = '';
    const sensorEntries = Object.entries(data.sensors || {});
    if (sensorEntries.length === 0) {
      sensorsDiv.innerHTML = `<div class="empty-state">${tr[lang]['empty-sensors']}</div>`;
    }
    sensorEntries.forEach(([name, reading]) => {
      if (!reading) return;
      const div = document.createElement('div');
      const health = (reading.health || 'ok').toLowerCase();
      div.className = 'sensor-item sensor-' + (health === 'ok' ? 'ok' : (health === 'degraded' ? 'warn' : 'error'));
      const nameDiv = document.createElement('div'); nameDiv.className = 'name';
      nameDiv.innerHTML = `<span>${escapeHtml(name)}</span><span>${escapeHtml(reading.unit || '')}</span>`;
      const valDiv = document.createElement('div'); valDiv.className = 'val';
      let vals = [];
      for (const [k, v] of Object.entries(reading.values || {})) {
        if (typeof v === 'number') vals.push(`${k}: ${v.toFixed(1)}`);
        else vals.push(`${k}: ${v}`);
      }
      valDiv.textContent = vals.join(', ') || '—';
      div.appendChild(nameDiv); div.appendChild(valDiv);
      if (reading.history && reading.history.length > 1) {
        const sparkDiv = document.createElement('div'); sparkDiv.className = 'spark'; sparkDiv.innerHTML = sparkline(reading.history);
        div.appendChild(sparkDiv);
      }
      sensorsDiv.appendChild(div);
    });

    const log = $('log');
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const ts = fmtTime(data.timestamp || Date.now() / 1000);
    const timeSpan = document.createElement('span'); timeSpan.className = 'log-time'; timeSpan.textContent = ts;
    const msgSpan = document.createElement('span'); msgSpan.className = 'log-msg log-severity-' + (state === 'confirmed' ? 'critical' : (state === 'alert' ? 'warning' : 'info'));
    msgSpan.textContent = 'Status update · ' + state.toUpperCase();
    entry.appendChild(timeSpan); entry.appendChild(msgSpan);
    if (log.children.length === 1 && log.children[0].classList.contains('empty-state')) log.innerHTML = '';
    log.insertBefore(entry, log.firstChild);
    while (log.children.length > 60) log.removeChild(log.lastChild);

    $('last-update').textContent = 'Updated: ' + ts;

    renderResources(data.system_health || {});
    if (data.zones) renderZones(data.zones);
  }

  let pendingAction = null;
  function showConfirm(title, action, zoneId) {
    $('confirm-title').textContent = title;
    $('confirm-overlay').classList.add('active');
    $('confirm-ok').textContent = tr[lang].ok;
    $('confirm-cancel').textContent = tr[lang].cancel;
    pendingAction = { action, zoneId };
  }
  function hideConfirm() { $('confirm-overlay').classList.remove('active'); pendingAction = null; }
  $('confirm-cancel').addEventListener('click', hideConfirm);
  $('confirm-ok').addEventListener('click', async () => {
    if (!pendingAction) return;
    try {
      await fetch('/api/emergency', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: pendingAction.action, zone_id: pendingAction.zoneId})
      });
    } catch (e) {}
    hideConfirm();
  });
  $('btn-evacuate').addEventListener('click', () => showConfirm(tr[lang].confirm_evacuate, 'evacuate'));
  $('btn-silence').addEventListener('click', () => showConfirm(tr[lang].confirm_silence, 'silence'));
  $('btn-reset').addEventListener('click', () => showConfirm(tr[lang].confirm_reset, 'reset'));
  $('btn-test').addEventListener('click', async () => {
    try {
      await fetch('/api/emergency', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action: 'test'})});
    } catch (e) {}
  });

  applyLang();
  applyTheme();
  loadModules();
  loadZones();
  loadResources();
  connect();
})();
</script>
</body>
</html>
"""
