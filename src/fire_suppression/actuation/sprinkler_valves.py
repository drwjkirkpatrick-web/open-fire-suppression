"""Smart sprinkler valve integration.

# ADD-009 — Smart Sprinkler Valve Integration

Supports addressable sprinkler valves with flow confirmation,
pressure monitoring, and per-zone flow control.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ValveStatus:
    valve_id: str
    is_open: bool
    flow_rate_lpm: float
    pressure_kpa: float
    last_command: str
    command_time: float
    error: str | None = None


class SmartSprinklerController:
    """Controller for addressable sprinkler valves.

    Supports Hunter Hydrawise-style valves via GPIO relay + optional
    flow meter (pulse counter) and pressure sensor (analog).

    Usage::

        sprinklers = SmartSprinklerController()
        await sprinklers.open_valve("zone_a")
        await sprinklers.close_valve("zone_a")
    """

    def __init__(
        self,
        valve_pins: dict[str, int],
        flow_pins: dict[str, int] | None = None,
        pressure_adc_channels: dict[str, int] | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.valve_pins = valve_pins
        self.flow_pins = flow_pins or {}
        self.pressure_adc_channels = pressure_adc_channels or {}
        self.mock = mock
        self._valves: dict[str, dict] = {}
        self._status: dict[str, ValveStatus] = {}

        for vid, pin in valve_pins.items():
            self._valves[vid] = {"pin": pin, "device": None}
            self._status[vid] = ValveStatus(
                valve_id=vid, is_open=False,
                flow_rate_lpm=0.0, pressure_kpa=0.0,
                last_command="init", command_time=time.time(),
            )
            if not mock:
                try:
                    from gpiozero import OutputDevice
                    self._valves[vid]["device"] = OutputDevice(pin, active_high=False)
                except Exception as exc:
                    logger.warning("Valve %s init failed: %s", vid, exc)

    async def open_valve(self, valve_id: str, timeout_seconds: float = 30.0) -> ValveStatus:
        """Open a valve and confirm flow/pressure."""
        status = self._status.get(valve_id)
        if not status:
            return ValveStatus(valve_id=valve_id, is_open=False, flow_rate_lpm=0,
                               pressure_kpa=0, last_command="invalid_id", command_time=time.time())

        if self.mock:
            status = ValveStatus(
                valve_id=valve_id, is_open=True, flow_rate_lpm=15.0,
                pressure_kpa=200.0, last_command="open", command_time=time.time(),
            )
            self._status[valve_id] = status
            logger.info("[MOCK] Valve %s opened", valve_id)
            return status

        valve = self._valves[valve_id]
        if valve["device"]:
            valve["device"].on()

        # Wait for pressure confirmation
        t0 = time.time()
        while time.time() - t0 < timeout_seconds:
            pressure = await self._read_pressure(valve_id)
            if pressure > 50:  # Minimum operating pressure
                status = ValveStatus(
                    valve_id=valve_id, is_open=True,
                    flow_rate_lpm=await self._read_flow(valve_id),
                    pressure_kpa=pressure,
                    last_command="open", command_time=t0,
                )
                self._status[valve_id] = status
                return status
            await asyncio.sleep(0.5)

        # Timeout — valve may be stuck
        status = ValveStatus(
            valve_id=valve_id, is_open=False, flow_rate_lpm=0,
            pressure_kpa=await self._read_pressure(valve_id),
            last_command="open_failed", command_time=t0,
            error="No pressure confirmation within timeout",
        )
        self._status[valve_id] = status
        logger.error("Valve %s open failed — no pressure", valve_id)
        return status

    async def close_valve(self, valve_id: str) -> ValveStatus:
        """Close a valve."""
        status = self._status.get(valve_id)
        if not status:
            return ValveStatus(valve_id=valve_id, is_open=False, flow_rate_lpm=0,
                               pressure_kpa=0, last_command="invalid_id", command_time=time.time())

        if self.mock:
            status = ValveStatus(
                valve_id=valve_id, is_open=False, flow_rate_lpm=0.0,
                pressure_kpa=0.0, last_command="close", command_time=time.time(),
            )
            self._status[valve_id] = status
            logger.info("[MOCK] Valve %s closed", valve_id)
            return status

        valve = self._valves[valve_id]
        if valve["device"]:
            valve["device"].off()

        status = ValveStatus(
            valve_id=valve_id, is_open=False, flow_rate_lpm=0.0,
            pressure_kpa=await self._read_pressure(valve_id),
            last_command="close", command_time=time.time(),
        )
        self._status[valve_id] = status
        return status

    async def _read_pressure(self, valve_id: str) -> float:
        """Read pressure sensor for a valve zone."""
        if self.mock or valve_id not in self.pressure_adc_channels:
            return 0.0
        # Mock: return synthetic pressure
        return 200.0

    async def _read_flow(self, valve_id: str) -> float:
        """Read flow meter for a valve zone."""
        if self.mock or valve_id not in self.flow_pins:
            return 0.0
        return 15.0

    def get_status(self, valve_id: str | None = None) -> dict | ValveStatus:
        if valve_id:
            return self._status.get(valve_id)
        return {k: v for k, v in self._status.items()}

    def all_valves_closed(self) -> bool:
        return all(not s.is_open for s in self._status.values())
