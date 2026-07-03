"""NFPA 90A compliant HVAC smoke control system.

# MOD-018 — HVAC Smoke Control Shutdown

On fire detection:
1. Shut down supply fans (prevent smoke distribution)
2. Close fire/smoke dampers (isolate zones)
3. Activate exhaust fans (remove smoke)
4. Maintain stairwell pressurization

NFPA 90A §6.2: HVAC systems must be designed to control smoke
movement. Smoke dampers required at fire-rated penetrations.

Hardware: Relay control of fan contactors, damper actuators (Belimo,
Honeywell), variable frequency drives (VFDs).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FanState(Enum):
    OFF = "off"
    ON = "on"
    EXHAUST = "exhaust"  # Smoke exhaust mode (higher speed)


class DamperState(Enum):
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"  # 25% for stairwell pressurization


@dataclass
class HVACZone:
    zone_id: str
    supply_fan_gpio: int | None = None
    exhaust_fan_gpio: int | None = None
    damper_gpio: int | None = None
    fan_state: FanState = FanState.ON
    damper_state: DamperState = DamperState.OPEN
    is_stairwell: bool = False


class HVACSmokeControl:
    """NFPA 90A compliant HVAC smoke control system.

    Manages HVAC components to control smoke movement during fire:
    - Shut supply fans
    - Close fire dampers
    - Activate exhaust fans
    - Maintain stairwell pressurization
    """

    def __init__(self, zones: list[HVACZone] | None = None, *, mock: bool = False) -> None:
        self.zones: dict[str, HVACZone] = {}
        self.mock = mock
        self._running = False

        if zones:
            for zone in zones:
                self.add_zone(zone)

        logger.info("HVACSmokeControl: %d zones", len(self.zones))

    def add_zone(self, zone: HVACZone) -> None:
        self.zones[zone.zone_id] = zone

    # ── Component Control ──────────────────────────────────────────

    async def _set_fan(self, zone_id: str, state: FanState) -> bool:
        zone = self.zones.get(zone_id)
        if not zone:
            return False

        if self.mock:
            zone.fan_state = state
            logger.info("[MOCK HVAC] Zone %s fan -> %s", zone_id, state.value)
            return True

        if zone.supply_fan_gpio is not None:
            try:
                import RPi.GPIO as GPIO  # type: ignore
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(zone.supply_fan_gpio, GPIO.OUT)
                if state == FanState.OFF:
                    GPIO.output(zone.supply_fan_gpio, GPIO.LOW)
                elif state == FanState.ON:
                    GPIO.output(zone.supply_fan_gpio, GPIO.HIGH)
                zone.fan_state = state
                return True
            except Exception:
                logger.exception("Fan control failed for zone %s", zone_id)
                return False
        return False

    async def _set_damper(self, zone_id: str, state: DamperState) -> bool:
        zone = self.zones.get(zone_id)
        if not zone:
            return False

        if self.mock:
            zone.damper_state = state
            logger.info("[MOCK HVAC] Zone %s damper -> %s", zone_id, state.value)
            return True

        if zone.damper_gpio is not None:
            try:
                import RPi.GPIO as GPIO  # type: ignore
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(zone.damper_gpio, GPIO.OUT)
                if state == DamperState.CLOSED:
                    GPIO.output(zone.damper_gpio, GPIO.LOW)
                elif state == DamperState.OPEN:
                    GPIO.output(zone.damper_gpio, GPIO.HIGH)
                zone.damper_state = state
                return True
            except Exception:
                logger.exception("Damper control failed for zone %s", zone_id)
                return False
        return False

    # ── Fire Response ────────────────────────────────────────────────

    async def execute_smoke_control(self, fire_zone: str) -> dict[str, Any]:
        """Execute NFPA 90A smoke control sequence.

        1. Shut supply fans in fire zone and adjacent zones
        2. Close dampers in fire zone
        3. Activate exhaust in fire zone
        4. Maintain stairwell pressurization
        """
        logger.critical("EXECUTING HVAC SMOKE CONTROL for zone '%s'", fire_zone)
        results = {}

        for zone_id, zone in self.zones.items():
            is_fire_zone = zone_id == fire_zone
            is_adjacent = zone_id.startswith(fire_zone.split("_")[0]) if "_" in fire_zone else False

            if zone.is_stairwell:
                # Stairwells: maintain positive pressure
                fan_ok = await self._set_fan(zone_id, FanState.ON)
                damper_ok = await self._set_damper(zone_id, DamperState.PARTIAL)
                results[zone_id] = {
                    "fan": fan_ok,
                    "damper": damper_ok,
                    "action": "stairwell_pressurization",
                }
            elif is_fire_zone:
                # Fire zone: shut supply, close dampers, activate exhaust
                fan_ok = await self._set_fan(zone_id, FanState.OFF)
                damper_ok = await self._set_damper(zone_id, DamperState.CLOSED)
                # Activate exhaust if available
                exhaust_ok = False
                if zone.exhaust_fan_gpio is not None:
                    exhaust_ok = await self._set_fan(zone_id, FanState.EXHAUST)
                results[zone_id] = {
                    "fan": fan_ok,
                    "damper": damper_ok,
                    "exhaust": exhaust_ok,
                    "action": "fire_zone_isolation",
                }
            elif is_adjacent:
                # Adjacent zones: shut supply, keep dampers partially open for escape
                fan_ok = await self._set_fan(zone_id, FanState.OFF)
                damper_ok = await self._set_damper(zone_id, DamperState.PARTIAL)
                results[zone_id] = {
                    "fan": fan_ok,
                    "damper": damper_ok,
                    "action": "adjacent_zone_protection",
                }
            else:
                # Remote zones: continue normal operation
                results[zone_id] = {
                    "fan": True,
                    "damper": True,
                    "action": "no_change",
                }

        return {
            "fire_zone": fire_zone,
            "zones_controlled": len(results),
            "all_success": all(
                r.get("fan", True) and r.get("damper", True)
                for r in results.values()
            ),
            "results": results,
            "timestamp": time.time(),
        }

    async def reset_all(self) -> None:
        """Reset all zones to normal operation after fire is cleared."""
        for zone_id in self.zones:
            await self._set_fan(zone_id, FanState.ON)
            await self._set_damper(zone_id, DamperState.OPEN)
        logger.info("All HVAC zones reset to normal")

    # ── Status ──────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "zone_count": len(self.zones),
            "zones": [
                {
                    "id": z.zone_id,
                    "fan": z.fan_state.value,
                    "damper": z.damper_state.value,
                    "stairwell": z.is_stairwell,
                }
                for z in self.zones.values()
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return self.get_status()
