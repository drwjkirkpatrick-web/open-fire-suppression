"""Tests for V7-008 Sensor Drift Auto-Calibration."""
import pytest

from fire_suppression.config import Config
from fire_suppression.sensors.drift_calibration import SensorDriftAutoCalibration


@pytest.fixture
def calibrator(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["drift_calibration"] = {
        "window_size": 50,
        "drift_threshold": 0.10,
        "maintenance_threshold": 0.25,
    }
    return SensorDriftAutoCalibration(cfg)


def test_baseline_learning(calibrator):
    result = None
    for i in range(20):
        result = calibrator.feed("mq2", 100.0 + i * 0.01, "clear")
    assert result is not None
    assert result["learned"] is True
    assert result["baseline"] > 0


def test_auto_calibration_applies_offset(calibrator):
    for _ in range(30):
        calibrator.feed("mq2", 100.0, "clear")
    # Now simulate 12% drift
    drift = calibrator.feed("mq2", 112.0, "clear")
    assert drift["status"] == "ok"
    assert drift["offset"] != 0


def test_maintenance_required(calibrator):
    result = None
    for _ in range(30):
        result = calibrator.feed("sht40", 25.0, "clear")
    assert result is not None
    result = calibrator.feed("sht40", 35.0, "clear")
    assert result["status"] == "maintenance_required"


def test_no_learning_during_fire(calibrator):
    for _ in range(10):
        result = calibrator.feed("mq2", 100.0, "alert")
    assert result["learned"] is False


def test_to_dict(calibrator):
    calibrator.feed("mq2", 100.0, "clear")
    d = calibrator.to_dict()
    assert d["feature_id"] == "V7-008"
    assert "mq2" in d["tracked_sensors"]
    assert d["healthy"] is True
