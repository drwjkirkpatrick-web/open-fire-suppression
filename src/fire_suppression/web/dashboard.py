"""FastAPI web dashboard and API for open-fire-suppression.

# T002 — Real-Time Dashboard API
# T003 — Dashboard WebSocket
# T004 — Historical Data Query
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

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
    return {"message": "open-fire-suppression API", "version": "0.1.0"}


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
    # In production, this would query the TelemetryLogger
    # For now, return from cache
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


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """Serve a simple HTML dashboard with real-time WebSocket updates."""
    return DASHBOARD_HTML


# ── WebSocket ──

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Push real-time status updates at 1 Hz.

    # T003 — Dashboard WebSocket
    """
    await websocket.accept()
    _clients.append(websocket)
    logger.info("WebSocket client connected (total: %d)", len(_clients))
    try:
        while True:
            # Client can send commands; we just acknowledge
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
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
<html>
<head>
<meta charset="UTF-8">
<title>open-fire-suppression Dashboard</title>
<style>
body { font-family: monospace; background: #0a0a0a; color: #00ff00; margin: 0; padding: 20px; }
h1 { color: #ff6600; margin-top: 0; }
.card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 15px; margin: 10px 0; }
.card h2 { margin-top: 0; color: #ff9900; font-size: 1.1em; }
.status-clear { color: #00ff00; }
.status-warning { color: #ffff00; }
.status-alert { color: #ff6600; }
.status-confirmed { color: #ff0000; }
.sensor-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }
.sensor-item { background: #222; padding: 10px; border-radius: 4px; }
.sensor-ok { border-left: 3px solid #00ff00; }
.sensor-warn { border-left: 3px solid #ffff00; }
.sensor-error { border-left: 3px solid #ff0000; }
#log { background: #111; border: 1px solid #333; padding: 10px; height: 200px; overflow-y: auto; font-size: 0.85em; }
.timestamp { color: #666; }
</style>
</head>
<body>
<h1>🔥 open-fire-suppression Dashboard</h1>
<div class="card">
  <h2>System Status</h2>
  <p>Fire State: <span id="fire-state" class="status-clear">CLEAR</span></p>
  <p>Confidence: <span id="confidence">0.00</span></p>
  <p>Safety: <span id="safety-state">DISARMED</span></p>
  <p>Power: <span id="power-source">AC</span> | Battery: <span id="battery">100%</span></p>
  <p>Latency: <span id="latency">0</span> ms</p>
</div>
<div class="card">
  <h2>Sensor Readings</h2>
  <div id="sensors" class="sensor-grid"></div>
</div>
<div class="card">
  <h2>Event Log</h2>
  <div id="log"></div>
</div>
<script>
const ws = new WebSocket(`ws://${window.location.host}/ws`);
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type !== 'status') return;
  const data = msg.data;
  // Fire state
  const det = data.detection || {};
  const stateEl = document.getElementById('fire-state');
  stateEl.textContent = (det.state || 'CLEAR').toUpperCase();
  stateEl.className = 'status-' + (det.state || 'clear');
  document.getElementById('confidence').textContent = (det.confidence || 0).toFixed(2);
  document.getElementById('latency').textContent = (det.latency_ms || 0).toFixed(0);
  // Safety
  const safety = data.safety || {};
  document.getElementById('safety-state').textContent = (safety.state || 'unknown').toUpperCase();
  // Power
  const power = data.power || {};
  document.getElementById('power-source').textContent = (power.source || 'AC').toUpperCase();
  document.getElementById('battery').textContent = (power.battery_percent || 0).toFixed(0) + '%';
  // Sensors
  const sensorsDiv = document.getElementById('sensors');
  sensorsDiv.innerHTML = '';
  for (const [name, reading] of Object.entries(data.sensors || {})) {
    if (!reading) continue;
    const div = document.createElement('div');
    div.className = 'sensor-item sensor-ok';
    let vals = [];
    for (const [k, v] of Object.entries(reading.values || {})) {
      vals.push(`${k}: ${typeof v === 'number' ? v.toFixed(1) : v}`);
    }
    div.innerHTML = `<strong>${name}</strong><br><small>${vals.join(', ')}</small>`;
    sensorsDiv.appendChild(div);
  }
  // Log timestamp
  const log = document.getElementById('log');
  const entry = document.createElement('div');
  entry.innerHTML = `<span class="timestamp">${new Date().toLocaleTimeString()}</span> Update received`;
  log.insertBefore(entry, log.firstChild);
  if (log.children.length > 50) log.removeChild(log.lastChild);
};
ws.onclose = () => {
  document.getElementById('fire-state').textContent = 'DISCONNECTED';
  document.getElementById('fire-state').className = 'status-alert';
};
</script>
</body>
</html>
"""
