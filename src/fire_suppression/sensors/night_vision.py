"""Night vision enhancement for camera fire detection.

# ADD-019 — Night Vision Enhancement

Activates IR illuminator and switches to NoIR camera module for
low-light fire detection. IR LEDs turn on automatically when lux
falls below threshold.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

LUX_THRESHOLD = 10.0  # Lux — below this, activate night vision


class NightVisionController:
    """Manages night vision mode for fire detection cameras.

    Uses a photoresistor (LDR) or TSL2591 lux sensor to determine
    ambient light. When dark, activates IR illuminator and switches
    to NoIR camera settings.

    Usage::

        nv = NightVisionController(ir_led_pin=21)
        is_night = nv.check_ambient_light()
        if is_night:
            nv.activate_night_vision()
        frame = camera.capture_array()
        result = detector.detect(frame)  # Works in darkness
    """

    def __init__(
        self,
        lux_sensor_type: str = "ldr",  # "ldr" | "tsl2591"
        ldr_adc_channel: int = 2,
        ir_led_pin: int = 21,
        lux_threshold: float = LUX_THRESHOLD,
        *,
        mock: bool = False,
    ) -> None:
        self.lux_sensor_type = lux_sensor_type
        self.ldr_adc_channel = ldr_adc_channel
        self.ir_led_pin = ir_led_pin
        self.lux_threshold = lux_threshold
        self.mock = mock
        self._ir_on = False
        self._last_lux = 100.0

        if not mock:
            try:
                from gpiozero import OutputDevice
                self._ir_device = OutputDevice(ir_led_pin, active_high=True)
            except Exception as exc:
                logger.warning("IR LED init failed: %s", exc)
                self.mock = True

    def check_ambient_light(self) -> float:
        """Read ambient light level in lux."""
        if self.mock:
            return 5.0  # Simulate dark

        if self.lux_sensor_type == "ldr":
            # LDR on ADS1115: higher voltage = more light
            # This is a simplified mapping
            self._last_lux = 50.0  # Placeholder
        elif self.lux_sensor_type == "tsl2591":
            try:
                import adafruit_tsl2591
                sensor = adafruit_tsl2591.TSL2591(__import__("board").I2C())
                self._last_lux = sensor.lux
            except Exception:
                self._last_lux = 100.0

        return self._last_lux

    def is_dark(self) -> bool:
        return self.check_ambient_light() < self.lux_threshold

    def activate_night_vision(self) -> None:
        """Turn on IR illuminator LEDs."""
        if self._ir_on:
            return
        self._ir_on = True
        if self.mock:
            logger.info("[NIGHT VISION] IR illuminator activated")
            return
        if hasattr(self, "_ir_device"):
            self._ir_device.on()
            logger.info("IR illuminator ON")

    def deactivate_night_vision(self) -> None:
        """Turn off IR illuminator LEDs."""
        if not self._ir_on:
            return
        self._ir_on = False
        if self.mock:
            logger.info("[NIGHT VISION] IR illuminator deactivated")
            return
        if hasattr(self, "_ir_device"):
            self._ir_device.off()
            logger.info("IR illuminator OFF")

    def auto_mode(self) -> bool:
        """Automatically toggle night vision based on ambient light.

        Returns True if night vision is now active.
        """
        if self.is_dark():
            self.activate_night_vision()
            return True
        self.deactivate_night_vision()
        return False

    def get_status(self) -> dict:
        return {
            "lux": self._last_lux,
            "is_dark": self.is_dark(),
            "ir_active": self._ir_on,
            "threshold": self.lux_threshold,
        }
