"""V9-004 — Sensor Drift Widget

Exposes per-sensor baseline, last-calibration timestamp, drift ratio, and status
for the dashboard. The underlying auto-calibrator already learns baselines;
this module surfaces that data in a tidy API format.

Personality: *Graphites* — the trifle-conscious perfectionist. Tiny drift is
noticed, logged, and gently corrected before it becomes a missed detection.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fire_suppression.sensors.drift_calibration import SensorDriftAutoCalibration

logger = logging.getLogger(__name__)


class SensorDriftWidget:
    """Readable drift summary for dashboard and API consumers."""

    def __init__(
        self,
        calibrator: SensorDriftAutoCalibration | None = None,
        personality: str = "Graphites",
    ) -> None:
        self.calibrator = calibrator or SensorDriftAutoCalibration()
        self.personality = personality

    def status_color(self, drift_ratio: float) -> str:
        """Map drift ratio to a dashboard color."""
        if abs(drift_ratio) >= self.calibrator.maintenance_threshold:
            return "red"
        if abs(drift_ratio) >= self.calibrator.drift_threshold:
            return "yellow"
        return "green"

    def snapshot(self) -> dict[str, Any]:
        """Return a complete drift snapshot for every tracked sensor."""
        baselines = getattr(self.calibrator, "_baselines", {})
        offsets = getattr(self.calibrator, "_offsets", {})
        last_alert = getattr(self.calibrator, "_last_maintenance_alert", {})

        sensors = []
        for sensor_id in sorted(baselines.keys()):
            window = baselines[sensor_id]
            baseline = sum(window) / len(window) if window else 0.0
            offset = offsets.get(sensor_id, 0.0)
            # A live drift estimate is not stored, so compute a placeholder
            # from baseline vs. offset; real drift comes from feed() output.
            drift_ratio = offset / baseline if baseline else 0.0
            status = self.status_color(drift_ratio)
            sensors.append(
                {
                    "sensor_id": sensor_id,
                    "baseline": round(baseline, 4),
                    "offset": round(offset, 4),
                    "drift_ratio": round(drift_ratio, 4),
                    "status": status,
                    "last_maintenance_alert": last_alert.get(sensor_id, 0),
                    "window_size": len(window),
                    "threshold": self.calibrator.drift_threshold,
                    "maintenance_threshold": self.calibrator.maintenance_threshold,
                }
            )

        # If no baselines exist yet, return a friendly empty state with defaults.
        if not sensors:
            sensors = [
                {
                    "sensor_id": "mq2",
                    "baseline": None,
                    "offset": 0.0,
                    "drift_ratio": 0.0,
                    "status": "gray",
                    "message": "Collecting baseline data; check back after a few minutes.",
                }
            ]

        return {
            "personality": self.personality,
            "generated_at": time.time(),
            "sensor_count": len(sensors),
            "sensors": sensors,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.snapshot()
