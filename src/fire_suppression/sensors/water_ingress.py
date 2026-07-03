"""Water ingress detection for outdoor enclosures.

# ADD-002 — Rain / Water Ingress Detection

Uses a simple conductivity strip or water contact sensor to detect
moisture inside the electronics enclosure before damage occurs.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class WaterIngressSensor:
    """Water ingress detector using GPIO conductivity probe.

    Hardware: Two exposed copper traces on PCB connected to GPIO
    with a pull-up. When water bridges the traces, GPIO reads LOW.
    """

    def __init__(self, gpio_pin: int = 26, *, mock: bool = False) -> None:
        self.gpio_pin = gpio_pin
        self.mock = mock
        self._device = None
        self._last_read = 0.0

        if not mock:
            try:
                from gpiozero import InputDevice
                self._device = InputDevice(gpio_pin, pull_up=True)
            except Exception as exc:
                logger.warning("Water ingress sensor init failed: %s", exc)
                self.mock = True

    def read(self) -> dict:
        """Read water ingress status.

        Returns:
            Dict with ``wet`` (bool) and ``confidence`` (float).
        """
        if self.mock:
            return {"wet": False, "confidence": 1.0}

        try:
            # LOW = water detected (pull-up bridged)
            is_wet = not self._device.value  # type: ignore[union-attr]
            self._last_read = time.time()
            return {
                "wet": is_wet,
                "confidence": 1.0,
                "timestamp": self._last_read,
            }
        except Exception as exc:
            logger.error("Water ingress read failed: %s", exc)
            return {"wet": False, "confidence": 0.0, "error": str(exc)}

    def is_dry(self) -> bool:
        return not self.read()["wet"]

    async def monitor_loop(self, callback: callable, interval: float = 5.0) -> None:
        """Continuously monitor and call callback when water detected."""
        import asyncio
        was_wet = False
        while True:
            result = self.read()
            is_wet = result["wet"]
            if is_wet and not was_wet:
                callback(result)
            was_wet = is_wet
            await asyncio.sleep(interval)
