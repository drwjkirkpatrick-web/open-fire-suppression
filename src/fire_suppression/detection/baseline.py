"""Environmental baseline learning for adaptive thresholds.

# IMP-007 — Environmental Baseline Learning

Learns normal min/max/average sensor values over a configurable period,
then computes adaptive thresholds with configurable safety margins.
"""
from __future__ import annotations

import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import json

from fire_suppression.config import Config

if TYPE_CHECKING:
    from fire_suppression.sensors.base import SensorReading

logger = logging.getLogger(__name__)

DEFAULT_BASELINE_DAYS = 2
DEFAULT_MARGIN_MULTIPLIER = 2.0
DEFAULT_SAFETY_OFFSET = {
    "temperature_c": 15.0,
    "smoke_ppm": 100.0,
    "tvoc_ppb": 200.0,
    "gas_resistance_ohm": -2000.0,  # Lower = more VOCs (negative offset)
    "humidity_percent": -10.0,       # Fire drops humidity
}


@dataclass
class BaselineStats:
    """Statistics for a single sensor metric over the baseline period."""
    min_value: float = 0.0
    max_value: float = 0.0
    mean: float = 0.0
    stdev: float = 0.0
    count: int = 0
    computed_at: float = 0.0

    def compute(self, values: list[float]) -> None:
        if not values:
            return
        self.min_value = min(values)
        self.max_value = max(values)
        self.mean = statistics.mean(values)
        self.stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        self.count = len(values)
        self.computed_at = time.time()


class BaselineLearner:
    """Learns environmental baselines and computes adaptive thresholds.

    Usage::

        learner = BaselineLearner(config)
        learner.start_learning()
        # ... collect readings for 48 hours ...
        learner.compute_baselines()
        thresholds = learner.get_thresholds()
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.baseline_days = self.config.get("baseline", "days", default=DEFAULT_BASELINE_DAYS)
        self.margin_multiplier = self.config.get("baseline", "margin_multiplier", default=DEFAULT_MARGIN_MULTIPLIER)
        self.safety_offset = self.config.get("baseline", "safety_offset", default=DEFAULT_SAFETY_OFFSET)

        self._learning = False
        self._history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=10000))
        self._baselines: dict[str, BaselineStats] = {}
        self._baseline_file = self.config.data_dir / "baselines.json"

    def start_learning(self) -> None:
        """Start collecting sensor data for baseline learning."""
        self._learning = True
        self._history.clear()
        logger.info("Baseline learning started (target: %d days)", self.baseline_days)

    def stop_learning(self) -> None:
        """Stop collecting baseline data."""
        self._learning = False
        logger.info("Baseline learning stopped")

    def record(self, sensor_name: str, reading: SensorReading) -> None:
        """Record a sensor reading for baseline computation."""
        if not self._learning:
            return
        for key, value in reading.values.items():
            if isinstance(value, (int, float)):
                metric_key = f"{sensor_name}.{key}"
                self._history[metric_key].append(float(value))

    def compute_baselines(self) -> dict[str, BaselineStats]:
        """Compute baseline statistics from collected history."""
        self._baselines = {}
        for metric_key, values in self._history.items():
            stats = BaselineStats()
            stats.compute(list(values))
            self._baselines[metric_key] = stats
            logger.info("Baseline for %s: min=%.1f max=%.1f mean=%.1f std=%.1f (n=%d)",
                        metric_key, stats.min_value, stats.max_value,
                        stats.mean, stats.stdev, stats.count)
        self._save_baselines()
        return self._baselines

    def get_thresholds(self) -> dict[str, float]:
        """Compute adaptive thresholds from baselines.

        Threshold = baseline_max + (margin_multiplier * stdev) + safety_offset
        """
        thresholds = {}
        for metric_key, stats in self._baselines.items():
            # Extract the value key (e.g., "mq2.smoke_ppm" → "smoke_ppm")
            value_key = metric_key.split(".")[-1]
            offset = self.safety_offset.get(value_key, 0.0)
            threshold = stats.max_value + (self.margin_multiplier * stats.stdev) + offset
            thresholds[metric_key] = round(threshold, 2)
        return thresholds

    def get_threshold(self, sensor_name: str, value_key: str) -> float | None:
        """Get the adaptive threshold for a specific sensor metric."""
        metric_key = f"{sensor_name}.{value_key}"
        if metric_key in self._baselines:
            stats = self._baselines[metric_key]
            offset = self.safety_offset.get(value_key, 0.0)
            return round(stats.max_value + (self.margin_multiplier * stats.stdev) + offset, 2)
        return None

    def _save_baselines(self) -> None:
        """Persist baselines to disk."""
        try:
            self._baseline_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                key: {
                    "min": stats.min_value,
                    "max": stats.max_value,
                    "mean": stats.mean,
                    "stdev": stats.stdev,
                    "count": stats.count,
                    "computed_at": stats.computed_at,
                }
                for key, stats in self._baselines.items()
            }
            with open(self._baseline_file, "w") as fh:
                json.dump(data, fh, indent=2)
        except Exception as exc:
            logger.warning("Failed to save baselines: %s", exc)

    def load_baselines(self) -> bool:
        """Load previously computed baselines from disk."""
        if not self._baseline_file.exists():
            return False
        try:
            with open(self._baseline_file, "r") as fh:
                data = json.load(fh)
            self._baselines = {}
            for key, vals in data.items():
                stats = BaselineStats(
                    min_value=vals["min"],
                    max_value=vals["max"],
                    mean=vals["mean"],
                    stdev=vals["stdev"],
                    count=vals["count"],
                    computed_at=vals["computed_at"],
                )
                self._baselines[key] = stats
            logger.info("Loaded %d baselines from %s", len(self._baselines), self._baseline_file)
            return True
        except Exception as exc:
            logger.warning("Failed to load baselines: %s", exc)
            return False

    @property
    def is_learning(self) -> bool:
        return self._learning

    @property
    def has_baselines(self) -> bool:
        return len(self._baselines) > 0
