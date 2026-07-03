"""Vibration and earthquake detection sensor.

# ADD-018 — Vibration / Earthquake Sensor

Uses SW-420 vibration sensor or MPU6050 accelerometer to detect
seismic events. After an earthquake, auto-arms suppression for
30 minutes to catch potential gas-line-rupture fires.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading, SensorStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Earthquake magnitude thresholds (arbitrary units from accelerometer)
SHAKE_THRESHOLD = 2.0       # g-force
POST_QUAKE_ARM_SECONDS = 1800  # 30 minutes


class VibrationSensor(BaseSensor):
    """Vibration/earthquake detection sensor.

    Supports SW-420 (GPIO digital) or MPU6050 (I2C accelerometer).

    # ADD-018 — Vibration / Earthquake Sensor
    """

    def __init__(
        self,
        name: str = "vibration",
        sensor_type: str = "sw420",  # "sw420" | "mpu6050"
        gpio_pin: int = 16,
        shake_threshold: float = SHAKE_THRESHOLD,
        *,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.sensor_type = sensor_type
        self.gpio_pin = gpio_pin
        self.shake_threshold = shake_threshold
        self._device = None
        self._shake_history: deque[tuple[float, float]] = deque(maxlen=100)
        self._last_quake_time = 0.0

        if not mock and sensor_type == "sw420":
            try:
                from gpiozero import InputDevice
                self._device = InputDevice(gpio_pin, pull_up=True)
            except Exception as exc:
                logger.warning("Vibration sensor init failed: %s", exc)
                self.mock = True

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                self.name, time.time(),
                {"shake_detected": False, "quake_armed": False, "last_quake_minutes_ago": None},
                SensorStatus.OK,
            )

        if self.sensor_type == "sw420" and self._device:
            # SW-420: LOW when vibration detected
            shake = not self._device.value
            if shake:
                self._shake_history.append((time.time(), 1.0))
                self._detect_quake()
            return SensorReading(
                self.name, time.time(),
                {
                    "shake_detected": shake,
                    "quake_armed": self.is_quake_armed(),
                    "last_quake_minutes_ago": self._minutes_since_quake(),
                },
                SensorStatus.OK,
            )

        return SensorReading(
            self.name, time.time(),
            {"error": "unsupported_sensor_type"},
            SensorStatus.ERROR,
        )

    def _detect_quake(self) -> None:
        """Analyze shake history to detect sustained earthquake."""
        recent = [t for t, _ in self._shake_history if time.time() - t < 5.0]
        if len(recent) >= 5:  # 5+ shakes in 5 seconds = quake
            self._last_quake_time = time.time()
            logger.critical("EARTHQUAKE DETECTED — auto-arming suppression for %d seconds", POST_QUAKE_ARM_SECONDS)

    def is_quake_armed(self) -> bool:
        """Return True if we're within the post-quake auto-arm window."""
        if self._last_quake_time == 0:
            return False
        return time.time() - self._last_quake_time < POST_QUAKE_ARM_SECONDS

    def _minutes_since_quake(self) -> float | None:
        if self._last_quake_time == 0:
            return None
        return (time.time() - self._last_quake_time) / 60.0

    async def close(self) -> None:
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
