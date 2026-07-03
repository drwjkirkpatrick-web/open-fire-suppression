"""WS2812 LED evacuation route guidance system.

# ADD-006 — Evacuation Route LED Guidance

Dynamic LED strips show safe evacuation routes that change based
on fire location. Uses GPIO + SPI or rpi_ws281x library.

Route selection: opposite side of detected fire zone.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EvacuationLEDController:
    """Controls WS2812 LED strips for dynamic evacuation guidance.

    Usage::

        leds = EvacuationLEDController(num_leds=60, pin=18)
        leds.show_route("north")  # Flash north route green
        leds.show_alert()         # All red for fire alert
    """

    def __init__(self, num_leds: int = 60, pin: int = 18, *, mock: bool = False) -> None:
        self.num_leds = num_leds
        self.pin = pin
        self.mock = mock
        self._strip = None

        if not mock:
            try:
                import neopixel
                import board
                self._strip = neopixel.NeoPixel(
                    getattr(board, f"D{pin}"),
                    num_leds,
                    brightness=0.5,
                    auto_write=False,
                )
            except Exception as exc:
                logger.warning("NeoPixel init failed: %s", exc)
                self.mock = True

    def clear(self) -> None:
        if self._strip:
            self._strip.fill((0, 0, 0))
            self._strip.show()

    def show_route(self, direction: str, *, flash: bool = True) -> None:
        """Light up LEDs in the evacuation direction.

        Args:
            direction: "north", "south", "east", "west", or "center"
        """
        color = (0, 255, 0)  # Green
        if self.mock:
            logger.info("[LED] Evacuation route: %s", direction)
            return

        if not self._strip:
            return

        self._strip.fill((0, 0, 0))
        # Light up LEDs in the direction
        segments = {
            "north": range(0, self.num_leds // 4),
            "east": range(self.num_leds // 4, self.num_leds // 2),
            "south": range(self.num_leds // 2, 3 * self.num_leds // 4),
            "west": range(3 * self.num_leds // 4, self.num_leds),
            "center": range(self.num_leds // 3, 2 * self.num_leds // 3),
        }
        for i in segments.get(direction, range(self.num_leds)):
            self._strip[i] = color
        self._strip.show()

        if flash:
            asyncio.create_task(self._flash_direction(direction, color))

    async def _flash_direction(self, direction: str, color: tuple[int, int, int]) -> None:
        for _ in range(10):
            await asyncio.sleep(0.5)
            if self._strip:
                self._strip.fill((0, 0, 0))
                self._strip.show()
                await asyncio.sleep(0.3)
                self.show_route(direction, flash=False)

    def show_alert(self) -> None:
        """All LEDs red — fire detected."""
        if self.mock:
            logger.info("[LED] ALERT — all red")
            return
        if self._strip:
            self._strip.fill((255, 0, 0))
            self._strip.show()

    def show_safe(self) -> None:
        """All LEDs green — system clear."""
        if self.mock:
            logger.info("[LED] SAFE — all green")
            return
        if self._strip:
            self._strip.fill((0, 255, 0))
            self._strip.show()

    def show_zone_fire(self, zone: str) -> None:
        """Show evacuation route away from the fire zone."""
        # Simple mapping: opposite of fire zone
        opposites = {
            "north": "south", "south": "north",
            "east": "west", "west": "east",
        }
        route = opposites.get(zone, "center")
        self.show_route(route)
        logger.info("LED evacuation: fire in %s → route %s", zone, route)
