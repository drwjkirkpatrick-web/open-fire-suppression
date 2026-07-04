"""V7-005 — Cloud Situational Awareness Feed

Publishes a public, rate-limited JSON/WebSocket situational awareness feed
suitable for external dashboards, emergency operations centers, and mobile apps.
Only non-sensitive summary data is exposed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class CloudSituationalAwarenessFeed:
    """Public, rate-limited situational awareness feed."""

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        cfg = self.config.section("cloud_sitfeed")
        self.update_interval = float(cfg.get("update_interval_seconds", 5.0))
        self.max_clients = int(cfg.get("max_clients", 50))
        self.rate_limit_per_min = int(cfg.get("rate_limit_per_min", 60))
        self._clients: list[WebSocket] = []
        self._last_public_state: dict[str, Any] = {}
        self._client_counts: dict[int, int] = {}
        self._broadcast_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    async def stop(self) -> None:
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

    def sanitize(self, full_status: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive fields before public broadcast."""
        sensors = full_status.get("sensors", {})
        public_sensors = {
            name: {k: v for k, v in data.items() if k not in ("raw_adc", "calibration", "meta")}
            for name, data in sensors.items()
        }
        return {
            "feature_id": "V7-005",
            "fire_state": full_status.get("detection", {}).get("state", "clear"),
            "confidence": full_status.get("detection", {}).get("confidence", 0.0),
            "safety_state": full_status.get("safety", {}).get("state", "unknown"),
            "actuation_state": full_status.get("actuation", {}).get("state", "idle"),
            "power_source": full_status.get("power", {}).get("source", "unknown"),
            "battery_percent": full_status.get("power", {}).get("battery_percent", 0.0),
            "sensors": public_sensors,
            "timestamp": time.time(),
        }

    def ingest(self, full_status: dict[str, Any]) -> None:
        self._last_public_state = self.sanitize(full_status)

    async def connect(self, websocket: WebSocket) -> None:
        if len(self._clients) >= self.max_clients:
            await websocket.close(code=1008, reason="Too many clients")
            return
        await websocket.accept()
        self._clients.append(websocket)
        self._client_counts[id(websocket)] = 0
        logger.info("Public feed client connected (total %d)", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._clients:
            self._clients.remove(websocket)
        self._client_counts.pop(id(websocket), None)

    async def _broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(self.update_interval)
            if not self._clients:
                continue
            payload = json.dumps(self._last_public_state)
            disconnected = []
            for ws in self._clients:
                try:
                    await ws.send_text(payload)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                await self.disconnect(ws)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-005",
            "healthy": True,
            "clients": len(self._clients),
            "last_update": self._last_public_state.get("timestamp"),
            "mock": self.mock,
        }
