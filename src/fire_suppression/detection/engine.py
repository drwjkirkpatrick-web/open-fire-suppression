"""Fire detection engine with multi-sensor fusion and confidence scoring.

# D001 — Single-Sensor Threshold Fire Detection
# D002 — Multi-Sensor Fusion Fire Detection
# D003 — False Positive Suppression
# D004 — Thermal Hotspot Detection
# D005 — Flame Flicker Detection
# D006 — Smoke Plume Detection
# D007 — Fire Spread Direction
# D008 — Confidence Scoring
# D009 — Detection Latency
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from fire_suppression.config import Config

if TYPE_CHECKING:
    from fire_suppression.sensors.base import SensorReading

logger = logging.getLogger(__name__)


class FireState(Enum):
    """Overall fire detection state."""
    CLEAR = "clear"
    WARNING = "warning"      # Single sensor threshold exceeded
    ALERT = "alert"          # Multi-sensor fusion confirms fire
    CONFIRMED = "confirmed"  # Suppression activated


@dataclass
class DetectionResult:
    """Result of a fire detection cycle."""
    state: FireState
    confidence: float         # 0.0–1.0
    triggered_sensors: list[str] = field(default_factory=list)
    thermal_hotspots: list[dict] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    reason: str = ""


class FireDetectionEngine:
    """Multi-sensor fire detection with fusion, confidence scoring, and video analysis.

    Detection strategy:
    1. Single-sensor threshold check → WARNING
    2. Multi-sensor correlation within time window → ALERT
    3. Video analysis (color + motion) boosts confidence
    4. Thermal hotspot detection for precise localization
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        det = self.config.section("detection")

        self.enabled = det.get("enabled", True)
        self.single_thresholds = det.get("single_sensor_threshold", {})
        self.fusion_min_sensors = int(det.get("fusion_min_sensors", 2))
        self.fusion_window = float(det.get("fusion_time_window_seconds", 5.0))
        self.confidence_weights = {
            "smoke": float(det.get("confidence_smoke_weight", 0.3)),
            "temp": float(det.get("confidence_temp_weight", 0.3)),
            "gas": float(det.get("confidence_gas_weight", 0.2)),
            "video": float(det.get("confidence_video_weight", 0.2)),
        }
        self.thermal_hotspot_min_c = float(det.get("thermal_hotspot_min_c", 60.0))
        self.thermal_hotspot_min_pixels = int(det.get("thermal_hotspot_min_pixels", 4))
        self.flicker_min_hz = float(det.get("flicker_min_hz", 1.0))
        self.flicker_max_hz = float(det.get("flicker_max_hz", 12.0))

        # Rolling window of sensor activations for fusion
        self._activation_history: deque[dict] = deque()
        self._last_alert_time = 0.0

        # Thermal frame history for spread detection
        self._thermal_history: deque[dict] = deque(maxlen=60)

        # Video analysis state
        self._frame_buffer: deque[dict] = deque(maxlen=30)  # ~3 seconds at 10 FPS

    def detect(self, readings: dict[str, SensorReading | None]) -> DetectionResult:
        """Run detection cycle on current sensor readings.

        Args:
            readings: Mapping of sensor_name → SensorReading (or None on failure).

        Returns:
            DetectionResult with state, confidence, and metadata.
        """
        if not self.enabled:
            return DetectionResult(state=FireState.CLEAR, confidence=0.0, reason="detection_disabled")

        t0 = time.time()

        triggered: list[str] = []
        sensor_confidences: dict[str, float] = {}

        # ── Single-sensor threshold checks ──
        for sensor_name, reading in readings.items():
            if reading is None:
                continue
            conf = self._check_sensor_threshold(sensor_name, reading)
            if conf > 0:
                triggered.append(sensor_name)
                sensor_confidences[sensor_name] = conf
                logger.debug("Sensor %s triggered: confidence=%.2f", sensor_name, conf)

        # ── Thermal hotspot detection ──
        thermal_hotspots = []
        if "amg8833" in readings and readings["amg8833"] is not None:
            hotspots = self._detect_thermal_hotspots(readings["amg8833"])
            thermal_hotspots.extend(hotspots)
            if hotspots:
                triggered.append("amg8833_hotspot")
                sensor_confidences["amg8833_hotspot"] = min(len(hotspots) * 0.2, 1.0)

        if "mlx90640" in readings and readings["mlx90640"] is not None:
            hotspots = self._detect_thermal_hotspots(readings["mlx90640"])
            thermal_hotspots.extend(hotspots)
            if hotspots:
                triggered.append("mlx90640_hotspot")
                sensor_confidences["mlx90640_hotspot"] = min(len(hotspots) * 0.1, 1.0)

        # ── Video analysis (if available) ──
        video_conf = 0.0
        if "picamera" in readings and readings["picamera"] is not None:
            video_conf = self._analyze_video_frame(readings["picamera"])
            if video_conf > 0.3:
                triggered.append("picamera")
                sensor_confidences["picamera"] = video_conf

        # ── Multi-sensor fusion ──
        now = time.time()
        if triggered:
            self._activation_history.append({
                "time": now,
                "sensors": set(triggered),
                "confidences": dict(sensor_confidences),
            })

        # Trim old activations outside fusion window
        while self._activation_history and (now - self._activation_history[0]["time"] > self.fusion_window):
            self._activation_history.popleft()

        # Count unique sensors that triggered within the window
        all_triggered_sensors = set()
        all_confidences: dict[str, float] = {}
        for entry in self._activation_history:
            all_triggered_sensors.update(entry["sensors"])
            all_confidences.update(entry["confidences"])

        # ── Compute overall confidence ──
        confidence = self._compute_confidence(all_triggered_sensors, all_confidences, video_conf)

        # ── Determine state ──
        if len(all_triggered_sensors) >= self.fusion_min_sensors and confidence >= 0.6:
            state = FireState.ALERT
            reason = f"multi_sensor_fusion:{len(all_triggered_sensors)}_sensors_conf_{confidence:.2f}"
            self._last_alert_time = now
        elif len(all_triggered_sensors) >= 1:
            state = FireState.WARNING
            reason = f"single_sensor_trigger:{all_triggered_sensors}"
        else:
            state = FireState.CLEAR
            reason = "no_thresholds_exceeded"

        latency_ms = (time.time() - t0) * 1000

        return DetectionResult(
            state=state,
            confidence=round(confidence, 3),
            triggered_sensors=list(all_triggered_sensors),
            thermal_hotspots=thermal_hotspots,
            timestamp=now,
            latency_ms=round(latency_ms, 2),
            reason=reason,
        )

    # ── Sensor-specific threshold checks ──

    def _check_sensor_threshold(self, sensor_name: str, reading: SensorReading) -> float:
        """Return confidence (0.0–1.0) based on how much a sensor exceeds its threshold."""
        values = reading.values
        conf = 0.0

        if sensor_name == "mq2":
            threshold = self.single_thresholds.get("mq2_smoke_ppm", 300)
            smoke = values.get("smoke_ppm", 0)
            if smoke > threshold:
                conf = min((smoke - threshold) / threshold, 1.0)

        elif sensor_name == "mlx90614":
            threshold = self.single_thresholds.get("mlx90614_temp_c", 80.0)
            temp = values.get("object_temperature_c", 0)
            if temp > threshold:
                conf = min((temp - threshold) / threshold, 1.0)

        elif sensor_name == "sht40":
            threshold = self.single_thresholds.get("sht40_temp_c", 60.0)
            temp = values.get("temperature_c", 0)
            if temp > threshold:
                conf = min((temp - threshold) / threshold, 1.0)

        elif sensor_name == "bme680":
            # Lower gas resistance = more VOCs
            threshold = self.single_thresholds.get("bme680_gas_resistance", 5000)
            gas = values.get("gas_resistance_ohm", 999999)
            if gas < threshold:
                conf = min((threshold - gas) / threshold, 1.0)

        elif sensor_name == "ens160":
            threshold = self.single_thresholds.get("ens160_tvoc_ppb", 500)
            tvoc = values.get("tvoc_ppb", 0)
            if tvoc > threshold:
                conf = min((tvoc - threshold) / threshold, 1.0)

        elif sensor_name == "ds18b20":
            threshold = self.single_thresholds.get("ds18b20_temp_c", 70.0)
            temp = values.get("temperature_c", 0)
            if temp > threshold:
                conf = min((temp - threshold) / threshold, 1.0)

        return conf

    # ── Thermal hotspot detection ──

    def _detect_thermal_hotspots(self, reading: SensorReading) -> list[dict]:
        """Find contiguous regions of pixels ≥ threshold temperature."""
        hotspots = []
        values = reading.values

        # Extract pixel temperatures
        pixels: list[float] = []
        pixel_keys = sorted([k for k in values if k.startswith("pixel_")])
        for k in pixel_keys:
            pixels.append(float(values[k]))

        if not pixels:
            return hotspots

        # Determine grid dimensions from pixel count
        if len(pixels) == 64:  # AMG8833: 8×8
            rows, cols = 8, 8
        elif len(pixels) == 768:  # MLX90640: 32×24
            rows, cols = 24, 32
        else:
            return hotspots

        # Find pixels above threshold
        hot_pixels = set()
        for i, temp in enumerate(pixels):
            if temp >= self.thermal_hotspot_min_c:
                hot_pixels.add(i)

        # Find contiguous regions (simple clustering)
        visited = set()
        for start in hot_pixels:
            if start in visited:
                continue
            cluster = self._flood_fill(start, hot_pixels, rows, cols)
            if len(cluster) >= self.thermal_hotspot_min_pixels:
                temps = [pixels[i] for i in cluster]
                avg_temp = sum(temps) / len(temps)
                max_temp = max(temps)
                # Calculate centroid
                row_sum = sum(i // cols for i in cluster)
                col_sum = sum(i % cols for i in cluster)
                hotspots.append({
                    "size": len(cluster),
                    "avg_temp_c": round(avg_temp, 1),
                    "max_temp_c": round(max_temp, 1),
                    "centroid_row": round(row_sum / len(cluster), 1),
                    "centroid_col": round(col_sum / len(cluster), 1),
                })
            visited.update(cluster)

        return hotspots

    @staticmethod
    def _flood_fill(start: int, hot_pixels: set[int], rows: int, cols: int) -> set[int]:
        """Find all connected hot pixels using 4-way flood fill."""
        cluster = set()
        stack = [start]
        while stack:
            pixel = stack.pop()
            if pixel in cluster:
                continue
            cluster.add(pixel)
            r, c = pixel // cols, pixel % cols
            # Neighbors: up, down, left, right
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    nidx = nr * cols + nc
                    if nidx in hot_pixels and nidx not in cluster:
                        stack.append(nidx)
        return cluster

    # ── Video analysis (simplified) ──

    def _analyze_video_frame(self, reading: SensorReading) -> float:
        """Analyze a video frame for fire/smoke signatures.

        Returns confidence (0.0–1.0). In a full implementation, this would use
        OpenCV color thresholding + background subtraction + optional YOLO model.
        """
        frame = reading.raw
        if frame is None:
            return 0.0

        try:
            import numpy as np

            if not isinstance(frame, np.ndarray):
                return 0.0

            # Simplified analysis: count flame-colored pixels (orange/red in HSV)
            hsv = self._rgb_to_hsv(frame)

            # Flame colors in HSV: orange/red = hue ~5–25° (in OpenCV 0-179 scale: ~3-12)
            # Lower saturation/value thresholds to avoid noise
            h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
            flame_mask = (
                (h >= 3) & (h <= 20)  # Orange-red hue
                & (s >= 80)          # High saturation
                & (v >= 100)         # Reasonable brightness
            )

            flame_pixels = np.count_nonzero(flame_mask)
            total_pixels = frame.shape[0] * frame.shape[1]
            flame_ratio = flame_pixels / total_pixels

            # Confidence based on flame pixel ratio
            # 1% of frame = moderate confidence, 5% = high confidence
            confidence = min(flame_ratio * 20, 1.0)

            # Smoke detection: gray/white regions with low saturation, high value
            smoke_mask = (
                (s <= 30)
                & (v >= 150)
                & (v <= 220)
            )
            smoke_pixels = np.count_nonzero(smoke_mask)
            smoke_ratio = smoke_pixels / total_pixels
            smoke_conf = min(smoke_ratio * 15, 0.5)  # Smoke is less confident

            combined = max(confidence, smoke_conf)

            # Store frame for flicker detection
            self._frame_buffer.append({
                "time": time.time(),
                "flame_ratio": flame_ratio,
                "smoke_ratio": smoke_ratio,
            })

            # Flicker detection: check for oscillation in flame_ratio
            if len(self._frame_buffer) >= 10:
                recent = list(self._frame_buffer)[-10:]
                ratios = [f["flame_ratio"] for f in recent]
                if len(ratios) >= 5:
                    # Simple zero-crossing-like detection for flicker
                    sign_changes = sum(
                        1 for i in range(1, len(ratios))
                        if (ratios[i] - ratios[i-1]) * (ratios[i-1] - ratios[i-2]) < 0
                    ) if len(ratios) >= 3 else 0
                    flicker_hz = sign_changes / 1.0  # approximate over ~1 second window
                    if self.flicker_min_hz <= flicker_hz <= self.flicker_max_hz:
                        combined = min(combined + 0.2, 1.0)

            return round(combined, 3)

        except Exception as exc:
            logger.debug("Video analysis error: %s", exc)
            return 0.0

    @staticmethod
    def _rgb_to_hsv(rgb: "np.ndarray") -> "np.ndarray":
        """Convert RGB image to HSV (OpenCV-style)."""
        try:
            import cv2
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        except ImportError:
            import numpy as np
            # Minimal RGB→HSV for when OpenCV not available (mock mode)
            r, g, b = rgb[..., 0] / 255.0, rgb[..., 1] / 255.0, rgb[..., 2] / 255.0
            max_c = np.maximum(np.maximum(r, g), b)
            min_c = np.minimum(np.minimum(r, g), b)
            diff = max_c - min_c
            h = np.zeros_like(max_c)
            s = np.zeros_like(max_c)
            v = max_c
            mask = diff != 0
            # Hue calculation
            h_mask = mask & (max_c == r)
            h = np.where(h_mask, (60 * ((g - b) / diff) + 360) % 360, h)
            h_mask = mask & (max_c == g)
            h = np.where(h_mask, (60 * ((b - r) / diff) + 120), h)
            h_mask = mask & (max_c == b)
            h = np.where(h_mask, (60 * ((r - g) / diff) + 240), h)
            h = h / 2  # OpenCV uses 0-179
            s = np.where(mask, diff / max_c * 255, 0)
            return np.stack([h, s, v * 255], axis=-1).astype(np.uint8)

    # ── Confidence scoring ──

    def _compute_confidence(
        self,
        triggered_sensors: set[str],
        sensor_confidences: dict[str, float],
        video_conf: float,
    ) -> float:
        """Compute overall fire confidence from weighted sensor contributions.

        Weights:
        - smoke sensors: mq2, mq135
        - temp sensors: mlx90614, sht40, ds18b20, bme680_temp
        - gas sensors: bme680_gas, ens160
        - video: picamera
        """
        smoke_conf = 0.0
        temp_conf = 0.0
        gas_conf = 0.0

        for sensor, conf in sensor_confidences.items():
            if sensor in ("mq2", "mq135"):
                smoke_conf = max(smoke_conf, conf)
            elif sensor in ("mlx90614", "sht40", "ds18b20", "bme680", "amg8833_hotspot", "mlx90640_hotspot"):
                temp_conf = max(temp_conf, conf)
            elif sensor in ("bme680_gas", "ens160"):
                gas_conf = max(gas_conf, conf)

        # Only count video if we have actual frame analysis
        video_weight = self.confidence_weights["video"] if video_conf > 0 else 0.0
        # Redistribute unused video weight to other categories
        total_weight = (
            self.confidence_weights["smoke"]
            + self.confidence_weights["temp"]
            + self.confidence_weights["gas"]
            + video_weight
        )
        if total_weight == 0:
            return 0.0

        w_smoke = self.confidence_weights["smoke"] / total_weight
        w_temp = self.confidence_weights["temp"] / total_weight
        w_gas = self.confidence_weights["gas"] / total_weight
        w_video = video_weight / total_weight

        confidence = (
            w_smoke * smoke_conf
            + w_temp * temp_conf
            + w_gas * gas_conf
            + w_video * video_conf
        )

        # Boost confidence for multi-sensor agreement
        sensor_categories = set()
        if smoke_conf > 0:
            sensor_categories.add("smoke")
        if temp_conf > 0:
            sensor_categories.add("temp")
        if gas_conf > 0:
            sensor_categories.add("gas")
        if video_conf > 0.3:
            sensor_categories.add("video")

        # +0.1 per additional category beyond first
        category_boost = max(0, len(sensor_categories) - 1) * 0.1
        confidence = min(confidence + category_boost, 1.0)

        return confidence

    def _detect_fire_spread(self) -> dict | None:
        """Analyze thermal history to estimate fire spread direction.

        # D007 — Fire Spread Direction
        """
        if len(self._thermal_history) < 2:
            return None

        # Compare first and last thermal frames
        first = self._thermal_history[0]
        last = self._thermal_history[-1]

        if "hotspots" not in first or "hotspots" not in last:
            return None

        first_hotspots = first["hotspots"]
        last_hotspots = last["hotspots"]

        if not first_hotspots or not last_hotspots:
            return None

        # Simple: track centroid movement of largest hotspot
        first_centroid = first_hotspots[0]
        last_centroid = last_hotspots[0]

        dx = last_centroid["centroid_col"] - first_centroid["centroid_col"]
        dy = last_centroid["centroid_row"] - first_centroid["centroid_row"]

        return {
            "direction_degrees": round((dx, dy)),
            "dx": round(dx, 1),
            "dy": round(dy, 1),
            "speed_pixels_per_frame": round((dx**2 + dy**2)**0.5, 1),
        }

    def reset(self) -> None:
        """Clear all detection state."""
        self._activation_history.clear()
        self._thermal_history.clear()
        self._frame_buffer.clear()
        self._last_alert_time = 0.0
        logger.info("Detection engine reset")
