"""Hermes Agent bridge for open-fire-suppression notifications.

# HBR-001 — Hermes Humidity Notifications
# HBR-002 — Hermes Fire Alert Notifications
# HBR-003 — Hermes Status Reports

Enables the fire suppression system to send rich status updates,
alerts, and telemetry to a Hermes agent instance via structured
messages. This allows the Hermes agent to relay notifications to
Telegram, SMS, or other channels with full context.

Usage from main loop::

    from fire_suppression.bridge.hermes_bridge import HermesBridge
    bridge = HermesBridge()
    await bridge.connect()
    await bridge.send_fire_alert(detection_result)
    await bridge.send_status_report(system_status)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fire_suppression.detection.engine import DetectionResult
    from fire_suppression.sensors.base import SensorReading

logger = logging.getLogger(__name__)

# Hermes bridge uses a Unix socket or local file for IPC
DEFAULT_HERMES_SOCKET = "/run/hermes/fire_suppression.sock"
DEFAULT_STATUS_FILE = "/run/hermes/fire_suppression_status.json"


@dataclass
class HermesMessage:
    """Structured message for Hermes agent consumption."""
    message_type: str  # "fire_alert" | "humidity_alert" | "status" | "heartbeat" | "error"
    priority: str      # "critical" | "high" | "medium" | "low"
    payload: dict
    timestamp: float


class HermesBridge:
    """Bridge between fire suppression system and Hermes agent.

    Sends notifications via:
    1. Unix domain socket (if Hermes is local)
    2. JSON status file ( polled by Hermes cron job)
    3. HTTP POST to Hermes API (if configured)

    All methods are async-safe and queue messages if the bridge
    is temporarily unavailable.
    """

    def __init__(
        self,
        socket_path: str | None = None,
        status_file: str | Path | None = None,
        api_url: str | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.socket_path = socket_path or DEFAULT_HERMES_SOCKET
        self.status_file = Path(status_file) if status_file else Path(DEFAULT_STATUS_FILE)
        self.api_url = api_url
        self.mock = mock
        self._queue: asyncio.Queue[HermesMessage] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_status: dict = {}

    async def connect(self) -> None:
        """Start the bridge dispatch loop."""
        self._running = True
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info("Hermes bridge started (socket=%s, status_file=%s)", self.socket_path, self.status_file)

    async def disconnect(self) -> None:
        """Stop the bridge."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ── Public API ──

    async def send_fire_alert(self, result: "DetectionResult", sensor_data: dict | None = None) -> None:
        """Send a fire alert with full detection context."""
        msg = HermesMessage(
            message_type="fire_alert",
            priority="critical",
            payload={
                "state": result.state.value,
                "confidence": result.confidence,
                "reason": result.reason,
                "latencies_ms": getattr(result, 'latency_ms', 0.0),
                "sensor_data": sensor_data or {},
                "suppression_activated": getattr(result, 'suppression_activated', False),
                "suggested_action": "EVACUATE" if result.state.value == "confirmed" else "INVESTIGATE",
            },
            timestamp=time.time(),
        )
        await self._enqueue(msg)

    async def send_humidity_alert(
        self,
        reading: SensorReading,
        threshold_percent: float,
        zone: str = "default",
    ) -> None:
        """Send a humidity-related alert (too low = fire risk, too high = equipment risk)."""
        humidity = reading.values.get("humidity_percent", 0)
        alert_type = "low_humidity" if humidity < threshold_percent else "high_humidity"
        priority = "high" if humidity < 10 else "medium"

        msg = HermesMessage(
            message_type="humidity_alert",
            priority=priority,
            payload={
                "zone": zone,
                "humidity_percent": humidity,
                "threshold_percent": threshold_percent,
                "alert_type": alert_type,
                "sensor": reading.sensor_name,
                "temperature_c": reading.values.get("temperature_c"),
                "risk_assessment": (
                    "CRITICAL: Extremely dry conditions increase fire risk significantly"
                    if humidity < 10 else
                    "WARNING: Low humidity detected"
                ),
            },
            timestamp=time.time(),
        )
        await self._enqueue(msg)

    async def send_status_report(
        self,
        system_status: dict,
        sensor_readings: dict[str, SensorReading] | None = None,
    ) -> None:
        """Send periodic status report with full system snapshot."""
        readings_summary = {}
        if sensor_readings:
            for name, reading in sensor_readings.items():
                readings_summary[name] = {
                    "values": reading.values,
                    "timestamp": reading.timestamp,
                    "health": reading.health_status.value,
                }

        msg = HermesMessage(
            message_type="status",
            priority="low",
            payload={
                "system": system_status,
                "sensor_summary": readings_summary,
                "uptime_seconds": system_status.get("uptime_seconds", 0),
                "armed": system_status.get("armed", False),
                "fire_state": system_status.get("fire_state", "unknown"),
                "battery_percent": system_status.get("battery_percent"),
                "timestamp_confidence": system_status.get("timestamp_confidence", "unknown"),
            },
            timestamp=time.time(),
        )
        self._last_status = msg.payload
        await self._enqueue(msg)
        # Also write to status file for polling
        await self._write_status_file(msg.payload)

    async def send_error(self, component: str, error: str, details: dict | None = None) -> None:
        """Send an error/crash report."""
        msg = HermesMessage(
            message_type="error",
            priority="high",
            payload={
                "component": component,
                "error": error,
                "details": details or {},
            },
            timestamp=time.time(),
        )
        await self._enqueue(msg)

    async def send_heartbeat(self) -> None:
        """Send periodic heartbeat to confirm system is alive."""
        msg = HermesMessage(
            message_type="heartbeat",
            priority="low",
            payload={"alive": True},
            timestamp=time.time(),
        )
        await self._enqueue(msg)

    # ── Internal dispatch ──

    async def _enqueue(self, msg: HermesMessage) -> None:
        self._queue.put_nowait(msg)

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            # Try socket first, then file, then HTTP
            sent = False
            if not self.mock:
                sent = await self._send_via_socket(msg)
                if not sent:
                    sent = await self._send_via_http(msg)

            if not sent or self.mock:
                # Always write to status file as fallback
                await self._append_to_message_log(msg)
                if self.mock:
                    logger.debug("[MOCK HERMES] %s: %s", msg.message_type, msg.payload)

    async def _send_via_socket(self, msg: HermesMessage) -> bool:
        """Send message via Unix domain socket."""
        try:
            import socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect(self.socket_path)
            data = json.dumps({
                "type": msg.message_type,
                "priority": msg.priority,
                "payload": msg.payload,
                "timestamp": msg.timestamp,
            }).encode()
            sock.sendall(data + b"\n")
            sock.close()
            return True
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            return False
        except Exception as exc:
            logger.debug("Socket send failed: %s", exc)
            return False

    async def _send_via_http(self, msg: HermesMessage) -> bool:
        """Send message via HTTP POST to Hermes API."""
        if not self.api_url:
            return False
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json={
                        "type": msg.message_type,
                        "priority": msg.priority,
                        "payload": msg.payload,
                        "timestamp": msg.timestamp,
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status < 400
        except Exception as exc:
            logger.debug("HTTP send failed: %s", exc)
            return False

    async def _write_status_file(self, payload: dict) -> None:
        """Write current status to JSON file for Hermes polling."""
        try:
            temp = self.status_file.with_suffix(".tmp")
            temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp.replace(self.status_file)
        except Exception as exc:
            logger.warning("Status file write failed: %s", exc)

    async def _append_to_message_log(self, msg: HermesMessage) -> None:
        """Append message to a local log file for later replay."""
        log_file = self.status_file.parent / "message_log.jsonl"
        try:
            with open(log_file, "a") as fh:
                fh.write(json.dumps({
                    "type": msg.message_type,
                    "priority": msg.priority,
                    "payload": msg.payload,
                    "timestamp": msg.timestamp,
                }) + "\n")
        except Exception as exc:
            logger.debug("Message log append failed: %s", exc)

    def get_last_status(self) -> dict:
        """Return the most recently sent status payload."""
        return self._last_status.copy()
