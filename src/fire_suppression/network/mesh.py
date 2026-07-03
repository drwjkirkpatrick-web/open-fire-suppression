"""Neighbor mesh network for inter-unit fire communication.

# ADD-013 — Neighbor Network Mesh (Inter-Unit Communication)

Uses ESP-NOW or LoRa to communicate between nearby fire suppression
units. If Unit A detects fire, Units B/C/D auto-arm and increase
polling frequency.

For Pi 5, this uses a serial-connected ESP32 running ESP-NOW firmware.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class MeshMessage:
    source_id: str
    message_type: str  # "fire_alert" | "heartbeat" | "arm_request" | "status"
    payload: dict
    timestamp: float
    ttl: int = 3  # Time-to-live for mesh hops


class NeighborMesh:
    """Mesh network coordinator for inter-unit fire communication.

    Usage::

        mesh = NeighborMesh(unit_id="building_a_unit_1")
        await mesh.connect("/dev/ttyUSB0")
        mesh.on_fire_alert = lambda msg: arm_system()
        await mesh.broadcast_fire_alert({"zone": "kitchen", "confidence": 0.92})
    """

    def __init__(self, unit_id: str, *, mock: bool = False) -> None:
        self.unit_id = unit_id
        self.mock = mock
        self._serial = None
        self._running = False
        self._neighbors: set[str] = set()
        self._last_heartbeat: dict[str, float] = {}
        self.on_fire_alert: callable | None = None
        self.on_arm_request: callable | None = None
        self._task: asyncio.Task | None = None

    async def connect(self, serial_port: str = "/dev/ttyUSB0", baud: int = 115200) -> bool:
        """Connect to ESP32 mesh radio via serial."""
        if self.mock:
            logger.info("[MOCK MESH] Connected as %s", self.unit_id)
            return True
        try:
            import serial
            self._serial = serial.Serial(serial_port, baud, timeout=1.0)
            self._running = True
            self._task = asyncio.create_task(self._receive_loop())
            logger.info("Mesh connected on %s@%d", serial_port, baud)
            return True
        except ImportError:
            logger.warning("pyserial not installed — mesh disabled")
            self.mock = True
            return False
        except Exception as exc:
            logger.error("Mesh connection failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._serial:
            self._serial.close()

    async def broadcast_fire_alert(self, fire_data: dict) -> None:
        """Broadcast fire alert to all neighbors."""
        msg = MeshMessage(
            source_id=self.unit_id,
            message_type="fire_alert",
            payload=fire_data,
            timestamp=time.time(),
        )
        await self._send(msg)

    async def broadcast_arm_request(self) -> None:
        """Request all neighbors to arm."""
        msg = MeshMessage(
            source_id=self.unit_id,
            message_type="arm_request",
            payload={},
            timestamp=time.time(),
        )
        await self._send(msg)

    async def send_heartbeat(self) -> None:
        msg = MeshMessage(
            source_id=self.unit_id,
            message_type="heartbeat",
            payload={"status": "alive"},
            timestamp=time.time(),
        )
        await self._send(msg)

    async def _send(self, msg: MeshMessage) -> None:
        data = json.dumps({
            "src": msg.source_id,
            "type": msg.message_type,
            "payload": msg.payload,
            "ts": msg.timestamp,
            "ttl": msg.ttl,
        }) + "\n"

        if self.mock:
            logger.info("[MOCK MESH] Broadcast: %s", msg.message_type)
            return

        if self._serial:
            try:
                self._serial.write(data.encode())
            except Exception as exc:
                logger.warning("Mesh send failed: %s", exc)

    async def _receive_loop(self) -> None:
        """Receive and process incoming mesh messages."""
        if not self._serial:
            return
        while self._running:
            try:
                line = self._serial.readline().decode().strip()
                if not line:
                    await asyncio.sleep(0.1)
                    continue
                data = json.loads(line)
                msg = MeshMessage(
                    source_id=data["src"],
                    message_type=data["type"],
                    payload=data["payload"],
                    timestamp=data["ts"],
                    ttl=data.get("ttl", 1) - 1,
                )

                if msg.ttl <= 0:
                    continue
                if msg.source_id == self.unit_id:
                    continue

                self._neighbors.add(msg.source_id)
                self._last_heartbeat[msg.source_id] = time.time()
                logger.info("Mesh message from %s: %s", msg.source_id, msg.message_type)

                if msg.message_type == "fire_alert" and self.on_fire_alert:
                    await self.on_fire_alert(msg.payload)
                elif msg.message_type == "arm_request" and self.on_arm_request:
                    await self.on_arm_request()

            except json.JSONDecodeError:
                pass
            except Exception as exc:
                logger.debug("Mesh receive error: %s", exc)
                await asyncio.sleep(0.5)

    def get_neighbors(self) -> list[str]:
        """Return list of recently active neighbor unit IDs."""
        now = time.time()
        return [n for n, t in self._last_heartbeat.items() if now - t < 300]

    def get_status(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "connected": self._serial is not None or self.mock,
            "neighbors": self.get_neighbors(),
            "neighbor_count": len(self.get_neighbors()),
        }
