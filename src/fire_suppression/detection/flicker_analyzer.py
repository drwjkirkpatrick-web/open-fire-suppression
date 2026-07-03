"""Infrared flame flicker analysis for fire confirmation.

# ADD-003 — IR Flame Flicker Analysis

Real flames flicker at 1–12 Hz due to combustion turbulence.
Static hot objects (heaters, engines, sun-heated metal) do not
flicker at these frequencies. This module uses FFT on IR time-series
to distinguish flames from steady heat sources.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

FLAME_FREQ_MIN = 1.0   # Hz
FLAME_FREQ_MAX = 12.0  # Hz
HISTORY_SECONDS = 2.0  # Window for FFT


class FlameFlickerAnalyzer:
    """Analyzes IR temperature time-series for flame flicker signature.

    Usage::

        analyzer = FlameFlickerAnalyzer(sample_rate_hz=10)
        for reading in ir_sensor_stream:
            score = analyzer.add_reading(reading)
            if score > 0.7:
                logger.info("Flame flicker detected — likely real fire")
    """

    def __init__(self, sample_rate_hz: float = 10.0) -> None:
        self.sample_rate = sample_rate_hz
        self._samples: deque[float] = deque(maxlen=int(HISTORY_SECONDS * sample_rate_hz))
        self._timestamps: deque[float] = deque(maxlen=int(HISTORY_SECONDS * sample_rate_hz))

    def add_reading(self, ir_temperature: float) -> float:
        """Add an IR temperature reading and return flicker confidence (0–1).

        Args:
            ir_temperature: Object temperature in °C from IR sensor.

        Returns:
            Confidence score that this is a flickering flame (not static heat).
        """
        self._samples.append(ir_temperature)
        self._timestamps.append(time.time())

        if len(self._samples) < self._samples.maxlen // 2:
            return 0.0  # Not enough data yet

        return self._compute_flicker_score()

    def _compute_flicker_score(self) -> float:
        """Compute flame flicker score using FFT."""
        try:
            data = np.array(self._samples, dtype=np.float64)
            n = len(data)

            # Detrend (remove DC offset)
            data = data - np.mean(data)

            # Window function to reduce spectral leakage
            window = np.hanning(n)
            data_windowed = data * window

            # FFT
            fft_result = np.fft.rfft(data_windowed)
            magnitude = np.abs(fft_result)
            frequencies = np.fft.rfftfreq(n, d=1.0 / self.sample_rate)

            # Find peak in flame frequency band
            flame_mask = (frequencies >= FLAME_FREQ_MIN) & (frequencies <= FLAME_FREQ_MAX)
            if not np.any(flame_mask):
                return 0.0

            flame_power = np.sum(magnitude[flame_mask])
            total_power = np.sum(magnitude[1:])  # Exclude DC

            if total_power == 0:
                return 0.0

            score = flame_power / total_power
            # Clamp and shape to useful range
            score = min(1.0, score * 2.0)

            logger.debug("Flicker score: %.3f (peak freq: %.1f Hz)",
                        score, frequencies[np.argmax(magnitude)] if len(frequencies) > 0 else 0)
            return float(score)

        except Exception as exc:
            logger.warning("Flicker analysis failed: %s", exc)
            return 0.0

    def reset(self) -> None:
        self._samples.clear()
        self._timestamps.clear()

    def get_buffer_stats(self) -> dict:
        return {
            "samples": len(self._samples),
            "duration_seconds": self._timestamps[-1] - self._timestamps[0] if len(self._timestamps) > 1 else 0,
        }
