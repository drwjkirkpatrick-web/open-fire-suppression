"""open-fire-suppression detection improvements."""
from fire_suppression.detection.tflite_detector import TFLiteFireDetector
from fire_suppression.detection.kalman_fusion import FireIntensityKalmanFilter, KalmanState
from fire_suppression.detection.zones import ZoneConfig, ZoneManager
from fire_suppression.detection.baseline import BaselineLearner, BaselineStats

__all__ = [
    "TFLiteFireDetector",
    "FireIntensityKalmanFilter",
    "KalmanState",
    "ZoneManager",
    "ZoneConfig",
    "BaselineLearner",
    "BaselineStats",
]
