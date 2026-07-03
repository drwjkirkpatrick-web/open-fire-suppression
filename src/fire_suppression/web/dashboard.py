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
from fastapi.responses import HTMLResponse

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


# ── API Endpoints ──

@app.get("/")
async def root() -> dict:
    return {"message": "open-fire-suppression API", "version": "0.6.1"}


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
            payload = json.dumps({"type": "status", "data": dict(_status_cache)})
        disconnected = []
        for ws in _clients:
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in _clients:
                _clients.remove(ws)


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
  --font: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
}
html, body { height: 100%; }
body {
  margin: 0; padding: 0; font-family: var(--font); background: var(--bg); color: var(--text);
  display: flex; flex-direction: column;
}
header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: var(--panel); border-bottom: 1px solid var(--panel-border);
}
header h1 { font-size: 1.1rem; margin: 0; display: flex; align-items: center; gap: 8px; }
.badge {
  font-size: .75rem; padding: 2px 8px; border-radius: 999px; background: #334155; color: #cbd5e1;
}
#conn-status { font-size: .8rem; color: var(--muted); }
#conn-status.online { color: var(--ok); }
#conn-status.offline { color: var(--crit); }
#conn-status.reconnect { color: var(--warn); }
main {
  flex: 1; overflow-y: auto; padding: 12px 16px 80px;
}
.grid {
  display: grid; gap: 12px;
}
@media (min-width: 1200px) {
  .grid { grid-template-columns: repeat(4, 1fr); }
  .col-span-2 { grid-column: span 2; }
  .col-span-3 { grid-column: span 3; }
  .col-span-4 { grid-column: span 4; }
}
@media (min-width: 768px) and (max-width: 1199px) {
  .grid { grid-template-columns: repeat(2, 1fr); }
  .col-span-2 { grid-column: span 2; }
}
@media (max-width: 767px) {
  .grid { grid-template-columns: 1fr; }
}
.card {
  background: var(--panel); border: 1px solid var(--panel-border); border-radius: 12px;
  padding: 14px; display: flex; flex-direction: column; gap: 10px;
  box-shadow: 0 1px 2px rgba(0,0,0,.35);
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
.bar > i { display: block; height: 100%; border-radius: 999px; background: var(--accent); }
.sensor-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; }
.sensor-item {
  background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px;
}
.sensor-item .name { font-size: .8rem; color: var(--muted); }
.sensor-item .val { font-size: 1.1rem; font-weight: 600; }
.sensor-ok { border-left: 3px solid var(--ok); }
.sensor-warn { border-left: 3px solid var(--warn); }
.sensor-error { border-left: 3px solid var(--crit); }
.module-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.mod {
  background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px;
  font-size: .8rem;
}
.mod .mod-name { color: var(--muted); }
.mod .mod-status { font-weight: 600; }
.mod-ok .mod-status { color: var(--ok); }
.mod-warn .mod-status { color: var(--warn); }
.mod-err .mod-status { color: var(--crit); }
#log-wrap { max-height: 220px; overflow-y: auto; }
#log { display: flex; flex-direction: column; gap: 6px; font-size: .82rem; }
.log-entry { display: flex; gap: 8px; }
.log-time { color: #64748b; font-variant-numeric: tabular-nums; white-space: nowrap; }
.log-msg { color: #e2e8f0; }
footer {
  position: fixed; bottom: 0; left: 0; right: 0;
  padding: 8px 16px; background: rgba(11,15,25,.9); border-top: 1px solid var(--panel-border);
  display: flex; align-items: center; justify-content: space-between; font-size: .78rem; color: var(--muted);
}
#last-update { font-variant-numeric: tabular-nums; }
.controls { display: flex; gap: 6px; align-items: center; }
button {
  background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px; padding: 4px 10px; cursor: pointer; font: inherit; font-size: .78rem;
}
button:hover { background: #334155; }
button.primary { background: var(--accent); color: #0b0f19; border-color: var(--accent); font-weight: 600; }
</style>
</head>
<body>
<header>
  <h1>🔥 open-fire-suppression <span class="badge">v0.6.1</span></h1>
  <div class="controls">
    <button id="lang-btn" title="EN / SW">EN</button>
    <span id="conn-status" class="offline">● disconnected</span>
  </div>
</header>
<main>
  <div class="grid">
    <!-- System status -->
    <div class="card col-span-2">
      <h2 id="lbl-system-status">System Status</h2>
      <div class="row">
        <div>Fire State</div>
        <div id="fire-state" class="big state-unknown">UNKNOWN</div>
      </div>
      <div class="row">
        <div>Confidence</div>
        <div class="value"><span id="confidence">0.00</span> %</div>
      </div>
      <div class="row">
        <div>Safety</div>
        <div id="safety-state" class="value state-unknown">UNKNOWN</div>
      </div>
      <div class="row">
        <div>Latency</div>
        <div class="value"><span id="latency">0</span> ms</div>
      </div>
      <div class="row">
        <div>Actuation</div>
        <div id="actuation-state" class="value state-unknown">UNKNOWN</div>
      </div>
    </div>

    <!-- Power -->
    <div class="card">
      <h2 id="lbl-power">Power</h2>
      <div class="row">
        <div>Source</div>
        <div id="power-source" class="value">AC</div>
      </div>
      <div class="row">
        <div>Battery</div>
        <div class="value"><span id="battery">0</span> %</div>
      </div>
      <div class="row">
        <div>Charging</div>
        <div id="charging" class="value">—</div>
      </div>
      <div class="bar"><i id="battery-bar" style="width:0%"></i></div>
    </div>

    <!-- Detection -->
    <div class="card">
      <h2 id="lbl-detection">Detection</h2>
      <div class="row">
        <div>State</div>
        <div id="det-state" class="value state-unknown">CLEAR</div>
      </div>
      <div class="row">
        <div>Triggered</div>
        <div id="det-triggered" class="value">—</div>
      </div>
      <div class="row">
        <div>Reason</div>
        <div id="det-reason" class="value" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">—</div>
      </div>
    </div>

    <!-- Sensors -->
    <div class="card col-span-2">
      <h2 id="lbl-sensors">Sensor Readings</h2>
      <div id="sensors" class="sensor-grid"></div>
    </div>

    <!-- Module Health -->
    <div class="card col-span-2">
      <h2 id="lbl-modules">Module Health</h2>
      <div id="modules" class="module-grid"></div>
    </div>

    <!-- Event Log -->
    <div class="card col-span-4">
      <h2 id="lbl-events">Event Log</h2>
      <div id="log-wrap"><div id="log"></div></div>
    </div>
  </div>
</main>
<footer>
  <div id="last-update">Updated: —</div>
  <div>open-fire-suppression · Dashboard UI v0.6.1</div>
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
      disconnected: '● disconnected',
      online: '● online',
      reconnecting: '● reconnecting…',
    },
    sw: {
      'lbl-system-status': 'Hali ya Mfumo',
      'lbl-power': 'Nguvu',
      'lbl-detection': 'Ugunduzi',
      'lbl-sensors': 'Visomaji vya Sensaa',
      'lbl-modules': 'Hali ya Moduli',
      'lbl-events': 'Kumbukumbu ya Tukio',
      disconnected: '● kimekatika',
      online: '● mtandaoni',
      reconnecting: '● kuunganisha upya…',
    }
  };
  let lang = 'en';
  $('lang-btn').addEventListener('click', () => {
    lang = lang === 'en' ? 'sw' : 'en';
    $('lang-btn').textContent = lang.toUpperCase();
    Object.keys(tr[lang]).forEach(k => {
      const el = $(k);
      if (el) el.textContent = tr[lang][k];
    });
  });

  let ws = null;
  let reconnectTimer = null;
  let reconnectDelay = 1;
  let lastPing = 0;
  let pingTimer = null;
  let modulesLoaded = false;

  const stateClass = s => {
    const v = (s || '').toLowerCase();
    if (v === 'clear') return 'state-clear';
    if (v === 'warning') return 'state-warning';
    if (v === 'alert') return 'state-alert';
    if (v === 'confirmed') return 'state-confirmed';
    return 'state-unknown';
  };

  function setConn(status) {
    const el = $('conn-status');
    el.className = status;
    if (status === 'online') el.textContent = tr[lang].online;
    else if (status === 'reconnect') el.textContent = tr[lang].reconnecting;
    else el.textContent = tr[lang].disconnected;
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
          if (Date.now() - lastPing > 15000) {
            // No pong in 15s → force reconnect
            ws.close();
          }
        }
      }, 5000);
      // Load modules once after connect
      if (!modulesLoaded) loadModules();
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'pong') { lastPing = Date.now(); return; }
        if (msg.type !== 'status') return;
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

  async function loadModules() {
    try {
      const res = await fetch('/api/modules');
      const json = await res.json();
      modulesLoaded = true;
      renderModules(json.modules || {});
    } catch (e) {}
  }

  let lang = 'en';

  const stateClass = s => {
    const v = (s || '').toLowerCase();
    if (v === 'clear') return 'state-clear';
    if (v === 'warning') return 'state-warning';
    if (v === 'alert') return 'state-alert';
    if (v === 'confirmed') return 'state-confirmed';
    return 'state-unknown';
  };

  function renderModules(modules) {
    const container = $('modules');
    container.innerHTML = '';
    Object.entries(modules).forEach(([name, data]) => {
      const div = document.createElement('div');
      div.className = 'mod';
      let status = 'OK';
      if (data.error || data.healthy === false || data.present === false) status = 'ERROR';
      else if (data.degraded) status = 'DEGRADED';
      else if (data.healthy === false) status = 'WARN';
      const stClass = status === 'OK' ? 'mod-ok' : (status === 'DEGRADED' ? 'mod-warn' : 'mod-err');
      div.className = 'mod ' + stClass;
      const nameSpan = document.createElement('div'); nameSpan.className = 'mod-name'; nameSpan.textContent = name;
      const statusSpan = document.createElement('div'); statusSpan.className = 'mod-status'; statusSpan.textContent = status;
      div.appendChild(nameSpan); div.appendChild(statusSpan);
      container.appendChild(div);
    });
  }

  function render(data) {
    // System status
    const det = data.detection || {};
    const fEl = $('fire-state');
    fEl.textContent = (det.state || 'CLEAR').toUpperCase();
    fEl.className = 'big ' + stateClass(det.state);
    $('confidence').textContent = ((det.confidence || 0) * 100).toFixed(1);
    $('latency').textContent = (det.latency_ms || 0).toFixed(0);

    // Safety
    const safety = data.safety || {};
    const sEl = $('safety-state');
    sEl.textContent = (safety.state || 'unknown').toUpperCase();
    sEl.className = 'value ' + stateClass(safety.state);

    // Actuation
    const act = data.actuation || {};
    const aEl = $('actuation-state');
    aEl.textContent = (act.state || 'idle').toUpperCase();
    aEl.className = 'value ' + stateClass(act.state);

    // Power
    const power = data.power || {};
    $('power-source').textContent = (power.source || 'AC').toUpperCase();
    const bat = power.battery_percent || 0;
    $('battery').textContent = bat.toFixed(0);
    $('charging').textContent = power.is_charging ? 'YES' : 'NO';
    $('battery-bar').style.width = Math.max(0, Math.min(100, bat)) + '%';

    // Detection summary
    $('det-state').textContent = (det.state || 'CLEAR').toUpperCase();
    $('det-state').className = 'value ' + stateClass(det.state);
    $('det-triggered').textContent = (det.triggered_sensors || []).join(', ') || '—';
    $('det-reason').textContent = det.reason || '—';

    // Sensors
    const sensorsDiv = $('sensors');
    sensorsDiv.innerHTML = '';
    for (const [name, reading] of Object.entries(data.sensors || {})) {
      if (!reading) continue;
      const div = document.createElement('div');
      div.className = 'sensor-item sensor-ok';
      const nameDiv = document.createElement('div'); nameDiv.className = 'name'; nameDiv.textContent = name;
      const valDiv = document.createElement('div'); valDiv.className = 'val';
      let vals = [];
      for (const [k, v] of Object.entries(reading.values || {})) {
        if (typeof v === 'number') vals.push(`${k}: ${v.toFixed(1)}`);
        else vals.push(`${k}: ${v}`);
      }
      valDiv.textContent = vals.join(', ');
      div.appendChild(nameDiv); div.appendChild(valDiv);
      sensorsDiv.appendChild(div);
    }

    // Events
    const log = $('log');
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const ts = fmtTime(data.timestamp || Date.now() / 1000);
    const timeSpan = document.createElement('span'); timeSpan.className = 'log-time'; timeSpan.textContent = ts;
    const msgSpan = document.createElement('span'); msgSpan.className = 'log-msg';
    msgSpan.textContent = 'Status update · ' + (det.state || 'CLEAR').toUpperCase();
    entry.appendChild(timeSpan); entry.appendChild(msgSpan);
    log.insertBefore(entry, log.firstChild);
    while (log.children.length > 60) log.removeChild(log.lastChild);

    $('last-update').textContent = 'Updated: ' + ts;
  }

  connect();
})();
</script>
</body>
</html>
"""
