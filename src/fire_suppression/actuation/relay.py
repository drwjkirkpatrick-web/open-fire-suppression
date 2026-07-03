"""Suppression actuation control with relay management.

# A001 — Relay Control
# A002 — Pre-Activation Warning
# A003 — Suppression Activation
# A004 — Suppression Feedback
# A005 — Manual Override
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from fire_suppression.config import Config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ActuationState(Enum):
    """State of the suppression actuation system."""
    IDLE = "idle"
    PRE_ACTIVATION = "pre_activation"  # Warning countdown running
    ACTIVE = "active"                     # Suppression relays engaged
    COOLDOWN = "cooldown"                 # After suppression, before re-arm
    ERROR = "error"                       # Flow sensor reported failure


@dataclass
class ActuationEvent:
    """Record of a suppression actuation event."""
    event_type: str       # "warning_start", "activated", "deactivated", "flow_confirmed", "flow_failed"
    timestamp: float
    duration: float = 0.0
    reason: str = ""


class RelayController:
    """Manages relay outputs for suppression system actuation.

    Supports configurable active-high/low logic, pre-activation warnings,
    and flow sensor feedback confirmation.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        act = self.config.section("actuation")

        self.enabled = act.get("enabled", True)
        self.relay_count = int(act.get("relay_count", 4))
        self.relay_pins = list(act.get("relay_pins", [5, 6, 13, 19]))
        self.active_high = bool(act.get("relay_active_high", False))
        self.pre_activation_seconds = float(act.get("pre_activation_seconds", 10))
        self.suppression_duration = float(act.get("suppression_duration_seconds", 60))
        self.flow_sensor_pin = int(act.get("flow_sensor_pin", 26))
        self.manual_button_pin = int(act.get("manual_button_pin", 21))
        self.buzzer_pin = int(act.get("buzzer_pin", 20))

        self._state = ActuationState.IDLE
        self._relays_active = [False] * self.relay_count
        self._events: list[ActuationEvent] = []
        self._gpio = None
        self._buttons = {}
        self._flow_sensor = None

        if not self.config.mock_hardware:
            self._init_gpio()

    def _init_gpio(self) -> None:
        """Initialize gpiozero relay and button pins."""
        try:
            from gpiozero import Button, OutputDevice

            self._relays = [
                OutputDevice(pin, active_high=self.active_high, initial_value=False)
                for pin in self.relay_pins[:self.relay_count]
            ]
            self._buzzer = OutputDevice(self.buzzer_pin, active_high=True, initial_value=False)
            self._flow_sensor = Button(self.flow_sensor_pin, pull_up=True)
            self._manual_button = Button(self.manual_button_pin, pull_up=True)
            logger.info("GPIO initialized: %d relays, buzzer, flow sensor, manual button", self.relay_count)
        except Exception as exc:
            logger.error("GPIO init failed: %s", exc)
            self._relays = []
            self._buzzer = None
            self._flow_sensor = None
            self._manual_button = None

    # ── State properties ──

    @property
    def state(self) -> ActuationState:
        return self._state

    @property
    def is_idle(self) -> bool:
        return self._state == ActuationState.IDLE

    @property
    def is_active(self) -> bool:
        return self._state == ActuationState.ACTIVE

    # ── Core actuation ──

    async def activate(self, reason: str = "fire_detected") -> ActuationEvent:
        """Activate suppression after pre-activation warning.

        Returns the activation event. Does nothing if not enabled or not idle.
        """
        if not self.enabled:
            logger.warning("Actuation disabled; suppression not activated")
            return ActuationEvent("blocked", time.time(), reason="actuation_disabled")

        if self._state != ActuationState.IDLE:
            logger.warning("Cannot activate: state is %s", self._state.value)
            return ActuationEvent("blocked", time.time(), reason=f"state_{self._state.value}")

        # ── Pre-activation warning ──
        self._state = ActuationState.PRE_ACTIVATION
        warning_event = ActuationEvent("warning_start", time.time(), reason=reason)
        self._events.append(warning_event)
        logger.warning("PRE-ACTIVATION WARNING: suppression in %.0f seconds!", self.pre_activation_seconds)

        await self._sound_buzzer(pattern="warning", duration=self.pre_activation_seconds)

        # Check if state was cancelled during warning (manual override or disarm)
        if self._state != ActuationState.PRE_ACTIVATION:
            logger.info("Pre-activation cancelled")
            return ActuationEvent("cancelled", time.time(), reason="manual_cancel")

        # ── Activate relays ──
        self._state = ActuationState.ACTIVE
        for i, relay in enumerate(self._relays):
            try:
                relay.on()
                self._relays_active[i] = True
                logger.info("Relay %d (GPIO %d) ACTIVATED", i, self.relay_pins[i])
            except Exception as exc:
                logger.error("Relay %d activation failed: %s", i, exc)

        activation_event = ActuationEvent("activated", time.time(), reason=reason)
        self._events.append(activation_event)
        logger.critical("SUPPRESSION ACTIVATED: %s", reason)

        # ── Run for configured duration ──
        start = time.time()
        while time.time() - start < self.suppression_duration:
            await asyncio.sleep(0.5)
            # Check flow sensor
            if self._check_flow_sensor():
                flow_event = ActuationEvent("flow_confirmed", time.time(), reason="flow_detected")
                self._events.append(flow_event)
                logger.info("Suppression flow confirmed")
                break
            # Check for manual cancel
            if self._check_manual_button():
                logger.info("Manual cancel during suppression")
                break

        # ── Deactivate ──
        await self.deactivate(reason="duration_complete")
        return activation_event

    async def deactivate(self, reason: str = "manual") -> ActuationEvent:
        """Deactivate all relays immediately."""
        for i, relay in enumerate(self._relays):
            try:
                relay.off()
                self._relays_active[i] = False
            except Exception:
                pass

        self._state = ActuationState.COOLDOWN
        event = ActuationEvent("deactivated", time.time(), reason=reason)
        self._events.append(event)
        logger.info("SUPPRESSION DEACTIVATED: %s", reason)

        # Cooldown period before returning to IDLE
        await asyncio.sleep(5.0)
        self._state = ActuationState.IDLE
        logger.info("Actuation system ready (IDLE)")

        return event

    async def cancel_pre_activation(self) -> None:
        """Cancel an in-progress pre-activation warning."""
        if self._state == ActuationState.PRE_ACTIVATION:
            self._state = ActuationState.IDLE
            self._events.append(ActuationEvent("warning_cancelled", time.time()))
            await self._sound_buzzer(pattern="off")
            logger.info("Pre-activation warning cancelled")

    # ── Buzzer control ──

    async def _sound_buzzer(self, pattern: str, duration: float = 0.0) -> None:
        """Play buzzer patterns: ``warning`` (alternating), ``alarm`` (continuous), ``off``."""
        if self.config.mock_hardware or self._buzzer is None:
            return

        if pattern == "off":
            self._buzzer.off()
            return

        if pattern == "warning":
            # Alternating beep during countdown
            end = time.time() + duration
            while time.time() < end and self._state == ActuationState.PRE_ACTIVATION:
                self._buzzer.on()
                await asyncio.sleep(0.5)
                self._buzzer.off()
                await asyncio.sleep(0.5)
            self._buzzer.off()

        elif pattern == "alarm":
            self._buzzer.on()

    # ── Sensor checks ──

    def _check_flow_sensor(self) -> bool:
        """Check if suppression flow/pressure is confirmed."""
        if self.config.mock_hardware or self._flow_sensor is None:
            return True  # Assume flow in mock mode
        return self._flow_sensor.is_pressed

    def _check_manual_button(self) -> bool:
        """Check if manual override button is pressed."""
        if self.config.mock_hardware or self._manual_button is None:
            return False
        return self._manual_button.is_pressed

    # ── Individual relay control ──

    def set_relay(self, index: int, state: bool) -> None:
        """Set a single relay by index (0-based)."""
        if 0 <= index < len(self._relays):
            relay = self._relays[index]
            if state:
                relay.on()
            else:
                relay.off()
            self._relays_active[index] = state

    def get_relay_states(self) -> list[bool]:
        """Return current states of all relays."""
        return list(self._relays_active)

    # ── Event history ──

    def get_events(self, limit: int = 100) -> list[ActuationEvent]:
        """Return recent actuation events."""
        return self._events[-limit:]

    # ── Cleanup ──

    async def close(self) -> None:
        """Deactivate all relays and release GPIO."""
        for relay in self._relays:
            try:
                relay.off()
            except Exception:
                pass
        if self._buzzer:
            try:
                self._buzzer.off()
            except Exception:
                pass
        logger.info("Relay controller closed")
