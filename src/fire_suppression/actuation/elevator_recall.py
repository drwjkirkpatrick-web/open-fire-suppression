"""NFPA 72 §21.3 compliant elevator recall system.

# MOD-017 — Elevator Recall

On fire detection, all elevators must:
1. Return to designated floor (typically 1 or lobby)
2. Open doors
3. Disconnect from automatic operation
4. Remain at designated floor with doors open

Prevents occupants from being trapped in burning elevator shaft
or arriving at fire floor.

Hardware: Relay interface to elevator controller fire service input
(FS1/FS2), or BACnet integration via MOD-007.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# NFPA 72 §21.3 timing
RECALL_TIMEOUT_SEC = 60.0  # Maximum time to reach designated floor
DOOR_HOLD_OPEN_SEC = 300.0  # Hold doors open for 5 minutes


class ElevatorState(Enum):
    NORMAL = "normal"
    RECALLING = "recalling"
    AT_DESIGNATED = "at_designated"
    PHASE_II = "phase_ii"  # Firefighter service
    OUT_OF_SERVICE = "out_of_service"


@dataclass
class Elevator:
    elevator_id: str
    designated_floor: int = 1
    current_floor: int = 1
    state: ElevatorState = ElevatorState.NORMAL
    gpio_recall_pin: int | None = None
    gpio_ack_pin: int | None = None  # Acknowledge from elevator
    last_recall_time: float = 0.0


class ElevatorRecall:
    """NFPA 72 compliant elevator recall system.

    Implements Phase I emergency recall operation:
    - Automatic recall to designated floor on fire alarm
    - Disconnect from normal service
    - Doors held open
    - Manual override for firefighter Phase II operation
    """

    def __init__(self, elevators: list[Elevator] | None = None, *, mock: bool = False) -> None:
        self.elevators: dict[str, Elevator] = {}
        self.mock = mock
        self._running = False

        if elevators:
            for elev in elevators:
                self.add_elevator(elev)

        logger.info("ElevatorRecall: %d elevators", len(self.elevators))

    def add_elevator(self, elevator: Elevator) -> None:
        self.elevators[elevator.elevator_id] = elevator

    # ── Recall Command ────────────────────────────────────────────────

    async def recall_all(self, fire_zone: str = "") -> dict[str, Any]:
        """Execute Phase I recall on all elevators.

        Returns results per elevator.
        """
        logger.critical("ELEVATOR RECALL INITIATED — fire zone: %s", fire_zone)
        results = {}

        for elev_id, elev in self.elevators.items():
            if self.mock:
                elev.state = ElevatorState.RECALLING
                await asyncio.sleep(0.2)
                elev.current_floor = elev.designated_floor
                elev.state = ElevatorState.AT_DESIGNATED
                elev.last_recall_time = time.time()
                results[elev_id] = {
                    "success": True,
                    "designated_floor": elev.designated_floor,
                    "arrived": True,
                    "time_sec": 0.2,
                }
                continue

            # Real hardware: activate recall relay
            if elev.gpio_recall_pin is not None:
                try:
                    import RPi.GPIO as GPIO  # type: ignore
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setup(elev.gpio_recall_pin, GPIO.OUT)
                    GPIO.output(elev.gpio_recall_pin, GPIO.HIGH)
                    elev.state = ElevatorState.RECALLING

                    # Wait for acknowledge or timeout
                    ack = False
                    start = time.time()
                    while time.time() - start < RECALL_TIMEOUT_SEC:
                        if elev.gpio_ack_pin is not None:
                            GPIO.setup(elev.gpio_ack_pin, GPIO.IN)
                            if GPIO.input(elev.gpio_ack_pin):
                                ack = True
                                break
                        await asyncio.sleep(0.5)

                    if ack:
                        elev.current_floor = elev.designated_floor
                        elev.state = ElevatorState.AT_DESIGNATED
                        results[elev_id] = {
                            "success": True,
                            "designated_floor": elev.designated_floor,
                            "arrived": True,
                            "time_sec": time.time() - start,
                        }
                    else:
                        results[elev_id] = {
                            "success": False,
                            "error": "timeout",
                            "designated_floor": elev.designated_floor,
                        }

                except Exception:
                    logger.exception("Elevator recall failed for %s", elev_id)
                    results[elev_id] = {"success": False, "error": "hardware_exception"}
            else:
                results[elev_id] = {"success": False, "error": "no_relay_configured"}

        return {
            "fire_zone": fire_zone,
            "elevators_recalled": sum(1 for r in results.values() if r.get("success")),
            "total_elevators": len(self.elevators),
            "results": results,
            "timestamp": time.time(),
        }

    # ── Phase II (Firefighter Service) ──────────────────────────────

    async def enable_phase_ii(self, elevator_id: str) -> bool:
        """Enable Phase II firefighter operation for a specific elevator.

        Allows firefighters to manually control elevator from designated floor.
        """
        elev = self.elevators.get(elevator_id)
        if not elev:
            return False
        elev.state = ElevatorState.PHASE_II
        logger.info("Elevator %s: Phase II firefighter service enabled", elevator_id)
        return True

    async def reset_to_normal(self) -> None:
        """Reset all elevators to normal service after fire is cleared."""
        for elev in self.elevators.values():
            elev.state = ElevatorState.NORMAL
            if not self.mock and elev.gpio_recall_pin is not None:
                try:
                    import RPi.GPIO as GPIO  # type: ignore
                    GPIO.output(elev.gpio_recall_pin, GPIO.LOW)
                except Exception:
                    pass
        logger.info("All elevators reset to normal service")

    # ── Status ──────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "elevator_count": len(self.elevators),
            "elevators": [
                {
                    "id": e.elevator_id,
                    "current_floor": e.current_floor,
                    "designated_floor": e.designated_floor,
                    "state": e.state.value,
                    "last_recall": e.last_recall_time,
                }
                for e in self.elevators.values()
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return self.get_status()
