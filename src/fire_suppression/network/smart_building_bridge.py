"""Smart building bridge for BMS integration (BACnet/IP, Modbus TCP, KNX).

# MOD-007 — Smart Building Bridge

Integrates open-fire-suppression with commercial building management
systems:
- BACnet/IP: elevators, HVAC dampers, smoke control fans
- Modbus TCP: fire doors, pressurization fans
- KNX: lighting, blinds, access control

On fire detection, automatically:
1. Recall elevators to designated floor
2. Close fire dampers
3. Activate smoke exhaust fans
4. Unlock emergency exits
5. Turn on emergency lighting
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BMSCommand:
    protocol: str      # "bacnet", "modbus", "knx"
    device_id: str
    object_type: str # "analog-output", "coil", "group-address"
    property: str    # "present-value", "priority-array"
    value: float | bool | str
    priority: int = 8  # BACnet priority 8 = manual operator


class SmartBuildingBridge:
    """Bridge to commercial building management systems.

    Provides unified interface for fire-related BMS commands across
    BACnet/IP, Modbus TCP, and KNX protocols.
    """

    def __init__(
        self,
        bacnet_ip: str | None = None,
        modbus_host: str | None = None,
        modbus_port: int = 502,
        knx_gateway: str | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.bacnet_ip = bacnet_ip
        self.modbus_host = modbus_host
        self.modbus_port = modbus_port
        self.knx_gateway = knx_gateway
        self.mock = mock
        self._command_log: list[dict] = []
        self._connected = False

        logger.info("SmartBuildingBridge: BACnet=%s Modbus=%s KNX=%s",
                    bacnet_ip, modbus_host, knx_gateway)

    # ── Connection ──────────────────────────────────────────────────

    async def connect(self) -> bool:
        if self.mock:
            self._connected = True
            return True

        # BACnet
        if self.bacnet_ip:
            try:
                import BAC0  # type: ignore
                self._bacnet = BAC0.lite(ip=self.bacnet_ip)
                logger.info("BACnet connected to %s", self.bacnet_ip)
            except Exception:
                logger.exception("BACnet connection failed")

        # Modbus
        if self.modbus_host:
            try:
                from pymodbus.client import ModbusTcpClient  # type: ignore
                self._modbus = ModbusTcpClient(self.modbus_host, port=self.modbus_port)
                self._modbus.connect()
                logger.info("Modbus connected to %s:%d", self.modbus_host, self.modbus_port)
            except Exception:
                logger.exception("Modbus connection failed")

        # KNX
        if self.knx_gateway:
            try:
                from xknx import XKNX  # type: ignore
                self._knx = XKNX()
                await self._knx.start()
                logger.info("KNX connected to %s", self.knx_gateway)
            except Exception:
                logger.exception("KNX connection failed")

        self._connected = True
        return True

    async def disconnect(self) -> None:
        if hasattr(self, "_bacnet"):
            self._bacnet.disconnect()
        if hasattr(self, "_modbus"):
            self._modbus.close()
        if hasattr(self, "_knx"):
            await self._knx.stop()
        self._connected = False

    # ── Fire Commands ───────────────────────────────────────────────

    async def _send_command(self, cmd: BMSCommand) -> bool:
        """Send a BMS command and log it."""
        if self.mock:
            self._command_log.append({
                "timestamp": time.time(),
                "protocol": cmd.protocol,
                "device": cmd.device_id,
                "value": cmd.value,
                "priority": cmd.priority,
            })
            logger.info("[MOCK BMS] %s/%s -> %s", cmd.protocol, cmd.device_id, cmd.value)
            return True

        try:
            if cmd.protocol == "bacnet" and hasattr(self, "_bacnet"):
                # BACnet write_property
                self._bacnet.write(cmd.device_id, cmd.object_type, cmd.property,
                                   cmd.value, priority=cmd.priority)
                return True
            elif cmd.protocol == "modbus" and hasattr(self, "_modbus"):
                # Modbus write coil or register
                if isinstance(cmd.value, bool):
                    self._modbus.write_coil(int(cmd.device_id), cmd.value)
                else:
                    self._modbus.write_register(int(cmd.device_id), int(cmd.value))
                return True
            elif cmd.protocol == "knx" and hasattr(self, "_knx"):
                # KNX group address write
                from xknx import Telegram, GroupAddress, DPTBinary  # type: ignore
                ga = GroupAddress(cmd.device_id)
                payload = DPTBinary(1) if cmd.value else DPTBinary(0)
                telegram = Telegram(ga, payload=payload)
                await self._knx.telegrams.put(telegram)
                return True
        except Exception:
            logger.exception("BMS command failed")
        return False

    async def recall_elevators(self, floor: int = 1) -> bool:
        """NFPA 72 §21.3: Recall all elevators to designated floor."""
        logger.warning("Recalling elevators to floor %d", floor)
        return await self._send_command(BMSCommand(
            protocol="bacnet",
            device_id="elevator_controller_1",
            object_type="analog-output",
            property="present-value",
            value=float(floor),
            priority=1,  # Life safety = highest priority
        ))

    async def close_fire_dampers(self, zones: list[str] | None = None) -> dict[str, bool]:
        """Close HVAC fire dampers in specified zones."""
        results = {}
        zones = zones or ["all"]
        for zone in zones:
            results[zone] = await self._send_command(BMSCommand(
                protocol="bacnet",
                device_id=f"damper_{zone}",
                object_type="binary-output",
                property="present-value",
                value=True,  # True = closed
                priority=1,
            ))
        return results

    async def activate_smoke_exhaust(self, zones: list[str] | None = None) -> dict[str, bool]:
        """Activate smoke exhaust fans."""
        results = {}
        zones = zones or ["all"]
        for zone in zones:
            results[zone] = await self._send_command(BMSCommand(
                protocol="modbus",
                device_id=f"exhaust_fan_{zone}",
                object_type="coil",
                property="coil",
                value=True,
                priority=1,
            ))
        return results

    async def unlock_emergency_exits(self) -> bool:
        """Unlock all emergency exit doors."""
        return await self._send_command(BMSCommand(
            protocol="knx",
            device_id="1/2/100",  # Group address for emergency exits
            object_type="group-address",
            property="value",
            value=True,
            priority=1,
        ))

    async def activate_emergency_lighting(self) -> bool:
        """Turn on all emergency lighting."""
        return await self._send_command(BMSCommand(
            protocol="knx",
            device_id="1/3/50",  # Group address for emergency lighting
            object_type="group-address",
            property="value",
            value=True,
            priority=1,
        ))

    # ── NFPA 72 Integration ───────────────────────────────────────────

    async def execute_fire_response(self, fire_zone: str) -> dict:
        """Execute complete NFPA 72 fire response sequence."""
        logger.critical("EXECUTING NFPA 72 FIRE RESPONSE for zone '%s'", fire_zone)
        results = {
            "elevator_recall": await self.recall_elevators(floor=1),
            "fire_dampers": await self.close_fire_dampers(zones=[fire_zone, "common"]),
            "smoke_exhaust": await self.activate_smoke_exhaust(zones=[fire_zone]),
            "emergency_exits": await self.unlock_emergency_exits(),
            "emergency_lighting": await self.activate_emergency_lighting(),
            "timestamp": time.time(),
        }
        all_passed = all(
            isinstance(v, bool) and v for v in results.values()
            if isinstance(v, bool)
        )
        results["all_commands_successful"] = all_passed
        return results

    # ── Serialization ───────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "bacnet_ip": self.bacnet_ip,
            "modbus_host": self.modbus_host,
            "knx_gateway": self.knx_gateway,
            "connected": self._connected,
            "commands_sent": len(self._command_log),
            "mock": self.mock,
        }
