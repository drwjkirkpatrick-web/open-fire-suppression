"""TensorFlow Lite fire/smoke detection model runner.

# IMP-001 — TFLite Fire/Smoke Detection Model

Uses an edge-optimized TFLite model for on-device fire and smoke detection.
The model should be trained separately (e.g., using Ultralytics YOLOv8)
and exported to TFLite format for ARM64 inference.

Model format: SSD or YOLO-style object detection with classes:
- class 0: fire
- class 1: smoke
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fire_suppression.config import Config

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = "/var/lib/fire-suppression/models/fire_smoke.tflite"


class TFLiteFireDetector:
    """TFLite-based fire and smoke detector for video frames.

    Usage::

        detector = TFLiteFireDetector()
        result = detector.detect(frame)
        # result = [{"class": "fire", "confidence": 0.92, "bbox": [x1, y1, x2, y2]}, ...]
    """

    def __init__(
        self,
        model_path: str | None = None,
        confidence_threshold: float = 0.5,
        *,
        mock: bool = False,
    ) -> None:
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.confidence_threshold = confidence_threshold
        self.mock = mock
        self._interpreter = None
        self._input_details = None
        self._output_details = None
        self._input_shape: tuple[int, ...] = (1, 640, 640, 3)

        if not mock:
            self._load_model()

    def _load_model(self) -> None:
        """Load the TFLite model from disk."""
        try:
            import tflite_runtime.interpreter as tflite
        except ImportError:
            try:
                import tensorflow.lite as tflite
            except ImportError:
                logger.warning("TFLite not available; falling back to mock mode")
                self.mock = True
                return

        model_file = Path(self.model_path)
        if not model_file.exists():
            logger.warning("TFLite model not found at %s; using mock mode", self.model_path)
            self.mock = True
            return

        try:
            self._interpreter = tflite.Interpreter(
                model_path=str(model_file),
                num_threads=4,  # Pi 5 has 4 cores
            )
            self._interpreter.allocate_tensors()
            self._input_details = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()
            self._input_shape = tuple(self._input_details[0]["shape"])
            logger.info("TFLite model loaded: %s (input shape: %s)", self.model_path, self._input_shape)
        except Exception as exc:
            logger.error("Failed to load TFLite model: %s", exc)
            self.mock = True

    def detect(self, frame: "np.ndarray") -> list[dict]:
        """Run fire/smoke detection on a single video frame.

        Args:
            frame: RGB image array (H×W×3) from picamera2.

        Returns:
            List of detection dicts with ``class``, ``confidence``, and ``bbox`` keys.
        """
        if self.mock:
            return self._mock_detect(frame)

        if self._interpreter is None:
            return []

        try:
            import cv2
            import numpy as np

            # Preprocess: resize to model input shape
            input_h, input_w = self._input_shape[1], self._input_shape[2]
            resized = cv2.resize(frame, (input_w, input_h))
            normalized = resized.astype(np.float32) / 255.0
            input_tensor = np.expand_dims(normalized, axis=0)

            # Run inference
            self._interpreter.set_tensor(self._input_details[0]["index"], input_tensor)
            self._interpreter.invoke()

            # Parse outputs (SSD-style: [boxes, classes, scores, num_detections])
            outputs = []
            for detail in self._output_details:
                tensor = self._interpreter.get_tensor(detail["index"])
                outputs.append(tensor)

            return self._parse_outputs(outputs, frame.shape[:2])

        except Exception as exc:
            logger.error("TFLite inference error: %s", exc)
            return []

    def _mock_detect(self, frame: "np.ndarray") -> list[dict]:
        """Return synthetic detections for development/testing."""
        import numpy as np

        h, w = frame.shape[:2]
        # Find orange/red regions as simulated fire detections
        # Simple HSV-based mock detection
        try:
            import cv2
            hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
            lower_orange = np.array([3, 80, 100])
            upper_orange = np.array([20, 255, 255])
            mask = cv2.inRange(hsv, lower_orange, upper_orange)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            detections = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 500:
                    x, y, bw, bh = cv2.boundingRect(cnt)
                    conf = min(area / 5000, 0.95)
                    detections.append({
                        "class": "fire",
                        "confidence": round(conf, 3),
                        "bbox": [int(x), int(y), int(x + bw), int(y + bh)],
                    })
            return detections
        except Exception:
            # Ultimate fallback: centered box
            return [{
                "class": "fire",
                "confidence": 0.85,
                "bbox": [w//2 - 50, h//2 - 50, w//2 + 50, h//2 + 50],
            }]

    def _parse_outputs(self, outputs: list, original_shape: tuple[int, int]) -> list[dict]:
        """Parse TFLite model outputs into detection dicts.

        Handles both SSD-style and YOLO-style outputs.
        """
        detections = []
        if len(outputs) < 4:
            # YOLO-style: single tensor with [batch, boxes, 6] where 6 = [x, y, w, h, conf, cls]
            if len(outputs) >= 1 and outputs[0].ndim == 3:
                return self._parse_yolo_output(outputs[0], original_shape)
            return detections

        # SSD-style
        boxes = outputs[0][0]      # [num_detections, 4]
        classes = outputs[1][0]    # [num_detections]
        scores = outputs[2][0]      # [num_detections]
        num_detections = int(outputs[3][0])

        h, w = original_shape
        for i in range(num_detections):
            score = float(scores[i])
            if score < self.confidence_threshold:
                continue
            class_id = int(classes[i])
            class_name = "fire" if class_id == 0 else "smoke"
            ymin, xmin, ymax, xmax = boxes[i]
            detections.append({
                "class": class_name,
                "confidence": round(score, 3),
                "bbox": [
                    int(xmin * w), int(ymin * h),
                    int(xmax * w), int(ymax * h),
                ],
            })
        return detections

    def _parse_yolo_output(self, output: "np.ndarray", original_shape: tuple[int, int]) -> list[dict]:
        """Parse YOLOv8 TFLite output tensor."""
        detections = []
        h, w = original_shape
        # output shape: [1, num_boxes, 6] — filter by confidence
        for box in output[0]:
            x, y, bw, bh, conf, cls = box
            if conf < self.confidence_threshold:
                continue
            class_name = "fire" if int(cls) == 0 else "smoke"
            x1 = int((x - bw/2) * w)
            y1 = int((y - bh/2) * h)
            x2 = int((x + bw/2) * w)
            y2 = int((y + bh/2) * h)
            detections.append({
                "class": class_name,
                "confidence": round(float(conf), 3),
                "bbox": [max(0, x1), max(0, y1), min(w, x2), min(h, y2)],
            })
        return detections
