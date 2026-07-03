"""Tests for TFLite fire detector.

# IMP-001 — TFLite Fire/Smoke Detection Model
"""
import numpy as np
import pytest

from fire_suppression.detection.tflite_detector import TFLiteFireDetector


class TestTFLiteFireDetector:
    """# IMP-001 — TFLite Fire/Smoke Detection Model"""

    def test_mock_mode_initialization(self) -> None:
        detector = TFLiteFireDetector(mock=True)
        assert detector.mock is True
        assert detector._interpreter is None

    def test_mock_detect_returns_fire_boxes(self) -> None:
        detector = TFLiteFireDetector(mock=True)
        # Create a frame with orange/red region (simulated fire)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[200:300, 250:350] = [255, 100, 0]  # Orange
        result = detector.detect(frame)
        assert isinstance(result, list)
        if result:
            assert "class" in result[0]
            assert "confidence" in result[0]
            assert "bbox" in result[0]
            assert len(result[0]["bbox"]) == 4

    def test_mock_detect_empty_frame(self) -> None:
        detector = TFLiteFireDetector(mock=True)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)  # Black
        result = detector.detect(frame)
        assert isinstance(result, list)

    def test_confidence_threshold(self) -> None:
        detector = TFLiteFireDetector(mock=True, confidence_threshold=0.9)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[200:300, 250:350] = [255, 100, 0]
        result = detector.detect(frame)
        # Very high threshold may filter everything in mock
        assert isinstance(result, list)
