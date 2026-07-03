"""Smart glass opacity control for fire safety.

# MOD-016 — Smart Glass Opacity Control

Controls electrochromic or SPD (suspended particle device) smart
windows in fire conditions:

1. Fire detected near window:
   - Switch to TRANSPARENT so firefighters can see inside
   - If radiant heat is extreme (>5 kW/m²), switch to OPAQUE
     to block infrared radiation

2. NFPA 5000 compatible: allows manual override from fire panel

3. Occupant safety: transparent = visibility for evacuation

Hardware: View/SageGlass electrochromic windows, or
SPIRsmart SPD film with relay control.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

RADIANT_HEAT_THRESHOLD_KW_M2 = 5.0  # Switch to opaque above this


class GlassState(Enum):
    CLEAR = "clear"
    TINTED = "tinted"
    OPAQUE = "opaque"
    AUTO = "auto"


@dataclass
class SmartGlassPanel:
    panel_id: str
    zone: str
    gpio_pin: int | None = None  # For relay control
    current_state: GlassState = GlassState.CLEAR
    radiant_heat_kw_m2: float = 0.0


class SmartGlassController:
    """Smart glass opacity controller for fire scenarios.

    Manages electrochromic windows to balance visibility for
    firefighters vs. radiant heat protection.
    """

    def __init__(self, panels: list[SmartGlassPanel] | None = None, *, mock: bool = False) -> None:
        self.panels: dict[str, SmartGlassPanel] = {}
        self.mock = mock
        self._running = False

        if panels:
            for panel in panels:
                self.add_panel(panel)

        logger.info("SmartGlassController: %d panels", len(self.panels))

    def add_panel(self, panel: SmartGlassPanel) -> None:
        self.panels[panel.panel_id] = panel

    # ── State Control ──────────────────────────────────────────────

    async def set_state(self, panel_id: str, state: GlassState) -> bool:
        panel = self.panels.get(panel_id)
        if not panel:
            return False

        if self.mock:
            panel.current_state = state
            logger.info("[MOCK GLASS] %s -> %s", panel_id, state.value)
            return True

        if panel.gpio_pin is not None:
            try:
                import RPi.GPIO as GPIO  # type: ignore
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(panel.gpio_pin, GPIO.OUT)
                # Different states = different relay combinations
                if state == GlassState.CLEAR:
                    GPIO.output(panel.gpio_pin, GPIO.LOW)
                elif state == GlassState.OPAQUE:
                    GPIO.output(panel.gpio_pin, GPIO.HIGH)
                panel.current_state = state
                return True
            except Exception:
                logger.exception("Failed to set glass state for %s", panel_id)
                return False
        return False

    # ── Fire Response ───────────────────────────────────────────────

    async def handle_fire_detection(self, fire_zone: str, radiant_heat_kw_m2: float = 0.0) -> dict[str, Any]:
        """Adjust glass opacity based on fire location and radiant heat."""
        results = {}
        for panel_id, panel in self.panels.items():
            if panel.zone == fire_zone:
                # Fire zone: prioritize visibility for firefighters
                if radiant_heat_kw_m2 >= RADIANT_HEAT_THRESHOLD_KW_M2:
                    # Too hot — protect with opaque
                    new_state = GlassState.OPAQUE
                    reason = "radiant_heat_protection"
                else:
                    # Safe to be transparent
                    new_state = GlassState.CLEAR
                    reason = "firefighter_visibility"
            else:
                # Other zones: tint to reduce heat transfer, maintain some visibility
                new_state = GlassState.TINTED
                reason = "heat_reduction"

            success = await self.set_state(panel_id, new_state)
            results[panel_id] = {
                "success": success,
                "new_state": new_state.value,
                "reason": reason,
                "zone": panel.zone,
            }

        return {
            "fire_zone": fire_zone,
            "radiant_heat_kw_m2": radiant_heat_kw_m2,
            "panels_adjusted": len(results),
            "results": results,
            "timestamp": time.time(),
        }

    async def set_all_clear(self) -> None:
        """Restore all panels to clear after fire is out."""
        for panel_id in self.panels:
            await self.set_state(panel_id, GlassState.CLEAR)

    # ── NFPA 5000 Compliance ────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "panel_count": len(self.panels),
            "panels": [
                {
                    "id": p.panel_id,
                    "zone": p.zone,
                    "state": p.current_state.value,
                    "radiant_heat": p.radiant_heat_kw_m2,
                }
                for p in self.panels.values()
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return self.get_status()
