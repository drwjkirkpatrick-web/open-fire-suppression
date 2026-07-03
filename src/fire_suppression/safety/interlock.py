"""Safety interlock system for fire suppression.

# F001 — System Arming
# F002 — Disarm Safety
# F003 — Maintenance Mode
# F004 — Tamper Detection
# F005 — Watchdog Timer
# F006 — Emergency Stop
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from fire_suppression.config import Config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SafetyState(Enum):
    """Overall safety state of the suppression system."""
    DISARMED = "disarmed"       # System safe, no actuation possible
    ARMED = "armed"             # System armed, actuation possible
    MAINTENANCE = "maintenance"  # Maintenance mode, all actuation disabled
    EMERGENCY_STOP = "emergency_stop"  # E-stop pressed, system locked out
    TAMPERED = "tampered"       # Enclosure tampered, system locked out


class SafetyInterlock:
    """Manages all safety interlocks for the fire suppression system.

    The system must be ARMED before any suppression actuation can occur.
    Safety-critical inputs are monitored continuously.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        safety = self.config.section("safety")

        self.arming_required = bool(safety.get("arming_required", True))
        self.disarm_inhibits = bool(safety.get("disarm_inhibits_all", True))
        self.maintenance_pin = int(safety.get("maintenance_pin", 16))
        self.tamper_pin = int(safety.get("tamper_pin", 12))
        self.watchdog_timeout = float(safety.get("watchdog_timeout_seconds", 30))
        self.emergency_stop_pin = int(safety.get("emergency_stop_pin", 7))

        self._state = SafetyState.DISARMED
        self._arm_pin: int | None = None  # Set via arm() or GPIO
        self._watchdog_last_feed = time.time()
        self._watchdog_file = Path(self.config.data_dir) / "watchdog.txt"
        self._tamper_active = False
        self._e_stop_active = False

        self._gpio = None
        if not self.config.mock_hardware:
            self._init_gpio()

    def _init_gpio(self) -> None:
        """Initialize GPIO inputs for safety switches."""
        try:
            from gpiozero import Button

            self._tamper_switch = Button(self.tamper_pin, pull_up=True)
            self._e_stop = Button(self.emergency_stop_pin, pull_up=True)
            self._maintenance_switch = Button(self.maintenance_pin, pull_up=True)

            # Callbacks
            self._tamper_switch.when_pressed = self._on_tamper
            self._e_stop.when_pressed = self._on_emergency_stop
            self._maintenance_switch.when_pressed = self._on_maintenance
            self._maintenance_switch.when_released = self._on_maintenance_release

            logger.info("Safety GPIO initialized: tamper=%d, e-stop=%d, maintenance=%d",
                        self.tamper_pin, self.emergency_stop_pin, self.maintenance_pin)
        except Exception as exc:
            logger.error("Safety GPIO init failed: %s", exc)
            self._tamper_switch = None
            self._e_stop = None
            self._maintenance_switch = None

    # ── State properties ──

    @property
    def state(self) -> SafetyState:
        return self._state

    @property
    def is_armed(self) -> bool:
        return self._state == SafetyState.ARMED

    @property
    def can_actuate(self) -> bool:
        """Return True if suppression actuation is currently permitted."""
        if self._state == SafetyState.EMERGENCY_STOP:
            return False
        if self._state == SafetyState.TAMPERED:
            return False
        if self._state == SafetyState.MAINTENANCE:
            return False
        if self.arming_required and self._state != SafetyState.ARMED:
            return False
        return True

    # ── Arming / Disarming ──

    def arm(self, pin: int | None = None) -> bool:
        """Arm the system (requires PIN or physical key in production).

        Returns True if successfully armed.
        """
        if self._state in (SafetyState.EMERGENCY_STOP, SafetyState.TAMPERED):
            logger.error("Cannot arm: system in %s", self._state.value)
            return False

        if self._state == SafetyState.MAINTENANCE:
            logger.error("Cannot arm: system in maintenance mode")
            return False

        # In production, validate PIN or physical key switch
        if self.arming_required:
            # TODO: implement actual PIN/key validation
            if pin is None and not self.config.mock_hardware:
                logger.error("Arming requires PIN or key switch")
                return False

        self._state = SafetyState.ARMED
        self._arm_pin = pin
        logger.warning("SYSTEM ARMED — suppression is now LIVE")
        return True

    def disarm(self) -> None:
        """Disarm the system. All actuation is immediately inhibited."""
        if self._state == SafetyState.ARMED:
            self._state = SafetyState.DISARMED
            self._arm_pin = None
            logger.info("SYSTEM DISARMED — suppression is SAFE")

    # ── Safety event handlers ──

    def _on_tamper(self) -> None:
        self._tamper_active = True
        self._state = SafetyState.TAMPERED
        logger.critical("TAMPER DETECTED — system locked out")

    def _on_emergency_stop(self) -> None:
        self._e_stop_active = True
        self._state = SafetyState.EMERGENCY_STOP
        logger.critical("EMERGENCY STOP ACTIVATED — all actuation inhibited")

    def _on_maintenance(self) -> None:
        if self._state != SafetyState.EMERGENCY_STOP and self._state != SafetyState.TAMPERED:
            self._state = SafetyState.MAINTENANCE
            logger.info("Maintenance mode activated")

    def _on_maintenance_release(self) -> None:
        if self._state == SafetyState.MAINTENANCE:
            self._state = SafetyState.DISARMED
            logger.info("Maintenance mode released — system DISARMED")

    # ── Watchdog ──

    def feed_watchdog(self) -> None:
        """Call periodically to keep the watchdog alive.

        If not fed within ``watchdog_timeout_seconds``, the system should
        be considered hung and take corrective action (log + optional reboot).
        """
        self._watchdog_last_feed = time.time()
        if self.config.mock_hardware:
            return
        try:
            self._watchdog_file.parent.mkdir(parents=True, exist_ok=True)
            self._watchdog_file.write_text(str(self._watchdog_last_feed))
        except Exception as exc:
            logger.warning("Watchdog file write failed: %s", exc)

    def check_watchdog(self) -> dict[str, float | str]:
        """Check watchdog health and return status.

        Returns dict with ``elapsed_seconds`` and ``status`` ("ok", "warn", "expired").
        """
        elapsed = time.time() - self._watchdog_last_feed
        if elapsed < self.watchdog_timeout * 0.5:
            status = "ok"
        elif elapsed < self.watchdog_timeout:
            status = "warn"
        else:
            status = "expired"
            logger.error("WATCHDOG EXPIRED after %.0f seconds — system may be hung", elapsed)
        return {
            "elapsed_seconds": round(elapsed, 1),
            "timeout_seconds": self.watchdog_timeout,
            "status": status,
        }

    # ── Manual safety checks (for polling when callbacks not available) ──

    async def poll_safety_inputs(self) -> None:
        """Poll all safety inputs and update state accordingly.

        Call this in the main loop when GPIO callbacks are not available.
        """
        if self.config.mock_hardware:
            return

        # Check tamper
        if self._tamper_switch and self._tamper_switch.is_pressed and not self._tamper_active:
            self._on_tamper()

        # Check e-stop
        if self._e_stop and self._e_stop.is_pressed and not self._e_stop_active:
            self._on_emergency_stop()

        # Check maintenance
        if self._maintenance_switch:
            if self._maintenance_switch.is_pressed and self._state not in (
                SafetyState.MAINTENANCE, SafetyState.EMERGENCY_STOP, SafetyState.TAMPERED
            ):
                self._on_maintenance()
            elif not self._maintenance_switch.is_pressed and self._state == SafetyState.MAINTENANCE:
                self._on_maintenance_release()

    # ── Reset ──

    def reset_tamper(self, pin: int | None = None) -> bool:
        """Reset tamper state (requires authorization PIN)."""
        # In production, validate PIN
        if self._tamper_active:
            self._tamper_active = False
            self._state = SafetyState.DISARMED
            logger.info("Tamper state reset")
            return True
        return False

    def reset_emergency_stop(self, pin: int | None = None) -> bool:
        """Reset emergency stop (requires authorization PIN)."""
        if self._e_stop_active:
            self._e_stop_active = False
            self._state = SafetyState.DISARMED
            logger.info("Emergency stop reset")
            return True
        return False

    # ── Cleanup ──

    async def close(self) -> None:
        """Release GPIO resources."""
        self.disarm()
        logger.info("Safety interlock system closed")
