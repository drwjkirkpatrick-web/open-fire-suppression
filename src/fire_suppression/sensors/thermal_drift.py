"""Thermal drift compensation for infrared temperature sensors.

# ADD-001 — Thermal Drift Compensation

MLX90614 and MLX90640 sensors drift as their internal thermopile
experiences ambient temperature changes. This module compensates
by tracking the sensor's own die temperature and applying a
correction curve.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ThermalDriftCompensator:
    """Compensates IR sensor readings for thermal drift.

    Usage::

        compensator = ThermalDriftCompensator()
        true_temp = compensator.compensate(
            raw_obj_temp=65.0,
            sensor_die_temp=35.0,
            reference_ambient=25.0,
        )
    """

    def __init__(self, history_size: int = 100) -> None:
        self._history: deque[tuple[float, float, float]] = deque(maxlen=history_size)
        self._coefficient = 0.02  # °C drift per °C die temp delta

    def compensate(
        self,
        raw_obj_temp: float,
        sensor_die_temp: float,
        reference_ambient: float | None = None,
    ) -> float:
        """Apply drift correction to raw object temperature.

        Args:
            raw_obj_temp: Uncorrected object temperature (°C).
            sensor_die_temp: Current sensor die/internal temp (°C).
            reference_ambient: Known ambient at last calibration, or None to use first reading.

        Returns:
            Compensated object temperature.
        """
        if reference_ambient is None:
            if self._history:
                reference_ambient = self._history[0][2]
            else:
                reference_ambient = sensor_die_temp
                self._history.append((raw_obj_temp, sensor_die_temp, reference_ambient))
                return raw_obj_temp

        die_delta = sensor_die_temp - reference_ambient
        correction = die_delta * self._coefficient
        compensated = raw_obj_temp - correction

        self._history.append((raw_obj_temp, sensor_die_temp, reference_ambient))
        logger.debug("Thermal drift: raw=%.2f die=%.2f ref=%.2f corr=%.2f out=%.2f",
                     raw_obj_temp, sensor_die_temp, reference_ambient, correction, compensated)
        return compensated

    def auto_calibrate(self, known_obj_temp: float, raw_obj_temp: float, sensor_die_temp: float) -> None:
        """Calibrate coefficient using a known temperature reference (e.g., boiling water = 100°C).

        Call this at startup with a reference object to establish the baseline.
        """
        # Simple linear fit: find coefficient that makes compensated = known
        die_delta = sensor_die_temp - raw_obj_temp  # approximate
        if abs(die_delta) > 0.1:
            self._coefficient = (raw_obj_temp - known_obj_temp) / die_delta
            logger.info("Thermal drift coefficient calibrated: %.4f", self._coefficient)
        self._history.clear()
        self._history.append((raw_obj_temp, sensor_die_temp, sensor_die_temp))

    def get_stats(self) -> dict:
        if not self._history:
            return {"samples": 0}
        die_temps = [h[1] for h in self._history]
        return {
            "samples": len(self._history),
            "coefficient": self._coefficient,
            "min_die_temp": min(die_temps),
            "max_die_temp": max(die_temps),
        }
