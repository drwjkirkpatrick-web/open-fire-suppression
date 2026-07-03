"""Predictive maintenance alerts based on sensor drift tracking.

# ADD-008 — Predictive Maintenance Alerts

Tracks sensor response time variance, noise floor, and calibration
drift. Alerts when a sensor drifts outside its known-good envelope
before it fails completely.
"""
from __future__ import annotations

import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class SensorEnvelope:
    """Known-good operating envelope for a sensor metric."""
    metric: str
    mean: float = 0.0
    stdev: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    samples: int = 0
    updated_at: float = 0.0

    def is_within(self, value: float, sigma_multiplier: float = 3.0) -> bool:
        lower = self.mean - sigma_multiplier * self.stdev
        upper = self.mean + sigma_multiplier * self.stdev
        return lower <= value <= upper

    def update(self, values: list[float]) -> None:
        if not values:
            return
        self.mean = statistics.mean(values)
        self.stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        self.min_val = min(values)
        self.max_val = max(values)
        self.samples = len(values)
        self.updated_at = time.time()


class PredictiveMaintenance:
    """Tracks sensor health trends and predicts failures before they occur.

    Usage::

        pm = PredictiveMaintenance()
        pm.record("mq2", "response_time_ms", 45.0)
        alerts = pm.check_all()
        # alerts = [{"sensor": "mq2", "metric": "response_time_ms", ...}]
    """

    def __init__(self, history_size: int = 1000, sigma_threshold: float = 4.0) -> None:
        self.history_size = history_size
        self.sigma_threshold = sigma_threshold
        self._history: dict[str, dict[str, deque[float]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=history_size))
        )
        self._envelopes: dict[str, SensorEnvelope] = {}
        self._alerts: list[dict] = []

    def record(self, sensor_name: str, metric: str, value: float) -> None:
        """Record a sensor metric reading."""
        key = f"{sensor_name}.{metric}"
        self._history[sensor_name][metric].append(value)

        # Auto-update envelope once we have enough samples
        if len(self._history[sensor_name][metric]) >= 100:
            self._update_envelope(key, list(self._history[sensor_name][metric]))

    def _update_envelope(self, key: str, values: list[float]) -> None:
        env = SensorEnvelope(metric=key)
        env.update(values)
        self._envelopes[key] = env

    def check_all(self) -> list[dict]:
        """Check all sensors against their envelopes. Return alerts."""
        alerts = []
        for sensor_name, metrics in self._history.items():
            for metric, values in metrics.items():
                key = f"{sensor_name}.{metric}"
                if key not in self._envelopes:
                    continue
                if not values:
                    continue
                latest = values[-1]
                env = self._envelopes[key]
                if not env.is_within(latest, self.sigma_threshold):
                    alerts.append({
                        "sensor": sensor_name,
                        "metric": metric,
                        "value": latest,
                        "expected_range": [env.mean - self.sigma_threshold * env.stdev,
                                           env.mean + self.sigma_threshold * env.stdev],
                        "severity": "warning" if abs(latest - env.mean) < 6 * env.stdev else "critical",
                        "message": f"{sensor_name} {metric}={latest:.2f} outside envelope "
                                   f"[{env.mean - self.sigma_threshold * env.stdev:.2f}, "
                                   f"{env.mean + self.sigma_threshold * env.stdev:.2f}]",
                    })
        self._alerts = alerts
        return alerts

    def get_envelope(self, sensor_name: str, metric: str) -> SensorEnvelope | None:
        return self._envelopes.get(f"{sensor_name}.{metric}")

    def get_sensor_health_score(self, sensor_name: str) -> float:
        """Return 0–1 health score. 1.0 = perfect, 0.0 = all metrics outside envelope."""
        if sensor_name not in self._history:
            return 0.0
        total = 0
        within = 0
        for metric, values in self._history[sensor_name].items():
            key = f"{sensor_name}.{metric}"
            if key not in self._envelopes or not values:
                continue
            total += 1
            env = self._envelopes[key]
            if env.is_within(values[-1], self.sigma_threshold):
                within += 1
        return within / total if total > 0 else 1.0
