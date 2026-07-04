"""V7-002 — Multi-Building Command Console

Allows a single dashboard/API to command and monitor multiple fire-suppression
units (buildings, wings, floors). Each remote unit reports via a compact
heartbeat; the console aggregates status and can broadcast commands.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


@dataclass
class UnitHeartbeat:
    unit_id: str
    building: str
    floor: str | None
    online: bool
    fire_state: str
    battery_percent: float
    last_seen: float
    sensors_online: int
    actuation_state: str = "idle"
    meta: dict[str, Any] = field(default_factory=dict)


class MultiBuildingConsole:
    """Aggregates multiple remote fire-suppression units."""

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        cfg = self.config.section("multi_building_console")
        self.timeout_seconds = float(cfg.get("unit_timeout_seconds", 30.0))
        self.units: dict[str, UnitHeartbeat] = {}
        self._commands: list[dict[str, Any]] = []

    def register_unit(self, unit_id: str, building: str, floor: str | None = None) -> None:
        self.units[unit_id] = UnitHeartbeat(
            unit_id=unit_id,
            building=building,
            floor=floor,
            online=True,
            fire_state="clear",
            battery_percent=100.0,
            last_seen=time.time(),
            sensors_online=0,
        )

    def heartbeat(self, data: dict[str, Any]) -> None:
        """Accept a heartbeat payload from a remote unit."""
        uid = data.get("unit_id")
        if not uid:
            return
        if uid not in self.units:
            self.register_unit(uid, data.get("building", "unknown"), data.get("floor"))
        unit = self.units[uid]
        unit.online = True
        unit.fire_state = data.get("fire_state", "clear")
        unit.battery_percent = float(data.get("battery_percent", 0))
        unit.sensors_online = int(data.get("sensors_online", 0))
        unit.actuation_state = data.get("actuation_state", "idle")
        unit.last_seen = time.time()
        unit.meta.update(data.get("meta", {}))

    def unit_status(self, unit_id: str) -> dict[str, Any]:
        u = self.units.get(unit_id)
        if not u:
            return {"unit_id": unit_id, "online": False}
        age = time.time() - u.last_seen
        return {
            "unit_id": u.unit_id,
            "building": u.building,
            "floor": u.floor,
            "online": u.online and age <= self.timeout_seconds,
            "fire_state": u.fire_state,
            "battery_percent": u.battery_percent,
            "sensors_online": u.sensors_online,
            "actuation_state": u.actuation_state,
            "last_seen_seconds": round(age, 1),
            "meta": u.meta,
        }

    def all_status(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-002",
            "units": {uid: self.unit_status(uid) for uid in self.units},
            "online_count": sum(1 for u in self.units.values() if self._is_online(u)),
            "alerting_count": sum(1 for u in self.units.values()
                                 if self._is_online(u) and u.fire_state not in ("clear", "idle")),
        }

    def _is_online(self, unit: UnitHeartbeat) -> bool:
        return unit.online and (time.time() - unit.last_seen) <= self.timeout_seconds

    def issue_command(self, unit_id: str | None, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Issue a command to one unit or broadcast to all."""
        targets = [unit_id] if unit_id else list(self.units.keys())
        payload = {"command": command, "params": params or {}, "issued_at": time.time()}
        issued = []
        for uid in targets:
            if uid in self.units:
                entry = {"unit_id": uid, **payload}
                self._commands.append(entry)
                issued.append(entry)
                logger.info("Command '%s' issued to %s", command, uid)
            else:
                issued.append({"unit_id": uid, "error": "unknown unit", **payload})
        return {"issued": issued, "count": len(issued)}

    def pending_commands(self, unit_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Remote unit calls this to pull its pending commands."""
        now = time.time()
        cmds = [c for c in self._commands if c.get("unit_id") == unit_id and c.get("issued_at", now) > now - 300]
        return cmds[-limit:]

    def to_dict(self) -> dict[str, Any]:
        return self.all_status()
