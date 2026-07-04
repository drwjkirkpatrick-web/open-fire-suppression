"""V7-008 — Sensor Drift Auto-Calibration

Tracks long-term sensor baselines and drift. When a sensor's raw signal drifts
away from its learned baseline but no fire is confirmed, the module issues a
calibration offset or a maintenance alert before drift causes missed detections.
"""
from __future__ import annotations

import logging
import statistics
import time
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class SensorDriftAutoCalibration:
    """Learns sensor baselines and compensates for slow drift."""

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        cfg = self.config.section("drift_calibration")
        self.window_size = int(cfg.get("window_size", 1000))
        self.drift_threshold = float(cfg.get("drift_threshold", 0.10))  # 10% of baseline
        self.maintenance_threshold = float(cfg.get("maintenance_threshold", 0.25))
        self._baselines: dict[str, list[float]] = {}
        self._offsets: dict[str, float] = {}
        self._last_maintenance_alert: dict[str, float] = {}

    def feed(self, sensor_id: str, value: float, fire_state: str = "clear") -> dict[str, Any]:
        """Feed a reading. Only learn baseline when fire_state is clear."""
        if fire_state not in ("clear", "idle"):
            return {"sensor_id": sensor_id, "learned": False, "reason": "fire_state_active"}

        window = self._baselines.setdefault(sensor_id, [])
        window.append(value)
        if len(window) > self.window_size:
            window.pop(0)

        if len(window) < 10:
            return {"sensor_id": sensor_id, "learned": False, "reason": "insufficient_data"}

        baseline = statistics.median(window)
        raw_drift = (value - baseline) / baseline if baseline else 0.0
        offset = self._offsets.get(sensor_id, 0.0)
        calibrated = value - offset
        calibrated_drift = (calibrated - baseline) / baseline if baseline else 0.0

        # Apply auto-offset if drift crosses threshold but not maintenance level
        if abs(calibrated_drift) > self.drift_threshold and abs(calibrated_drift) < self.maintenance_threshold:
            offset += baseline - calibrated
            self._offsets[sensor_id] = offset
            calibrated = value - offset
            logger.info("Auto-calibrated %s offset %.3f", sensor_id, offset)

        status = "ok"
        if abs(calibrated_drift) >= self.maintenance_threshold:
            status = "maintenance_required"
            now = time.time()
            if now - self._last_maintenance_alert.get(sensor_id, 0) > 3600:
                self._last_maintenance_alert[sensor_id] = now
                logger.warning("Sensor %s drift exceeds maintenance threshold", sensor_id)

        return {
            "sensor_id": sensor_id,
            "learned": True,
            "baseline": round(baseline, 4),
            "raw_value": round(value, 4),
            "offset": round(offset, 4),
            "calibrated_value": round(calibrated, 4),
            "drift_ratio": round(calibrated_drift, 4),
            "status": status,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-008",
            "healthy": True,
            "window_size": self.window_size,
            "drift_threshold": self.drift_threshold,
            "maintenance_threshold": self.maintenance_threshold,
            "tracked_sensors": list(self._baselines.keys()),
            "offsets": self._offsets,
            "mock": self.mock,
        }
