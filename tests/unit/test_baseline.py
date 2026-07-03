"""Tests for baseline learning.

# IMP-007 — Environmental Baseline Learning
"""
import pytest
from pathlib import Path

from fire_suppression.config import Config
from fire_suppression.detection.baseline import BaselineLearner
from fire_suppression.sensors.base import SensorReading


class TestBaselineLearner:
    """# IMP-007 — Environmental Baseline Learning"""

    def setup_method(self) -> None:
        Config._instance = None

    def test_start_stop_learning(self) -> None:
        learner = BaselineLearner()
        assert learner.is_learning is False
        learner.start_learning()
        assert learner.is_learning is True
        learner.stop_learning()
        assert learner.is_learning is False

    def test_record_adds_to_history(self) -> None:
        learner = BaselineLearner()
        learner.start_learning()
        reading = SensorReading("mq2", 0, {"smoke_ppm": 50})
        learner.record("mq2", reading)
        assert "mq2.smoke_ppm" in learner._history
        assert len(learner._history["mq2.smoke_ppm"]) == 1

    def test_compute_baselines(self) -> None:
        learner = BaselineLearner()
        learner.start_learning()
        for val in [20, 22, 21, 23, 24]:
            learner.record("mq2", SensorReading("mq2", 0, {"smoke_ppm": val}))
        baselines = learner.compute_baselines()
        assert "mq2.smoke_ppm" in baselines
        assert baselines["mq2.smoke_ppm"].mean == pytest.approx(22.0, abs=0.5)

    def test_get_thresholds(self) -> None:
        learner = BaselineLearner()
        learner.start_learning()
        for val in [20, 22, 21, 23, 24]:
            learner.record("mq2", SensorReading("mq2", 0, {"smoke_ppm": val}))
        learner.compute_baselines()
        thresholds = learner.get_thresholds()
        assert "mq2.smoke_ppm" in thresholds
        # Threshold should be above max(24) + margin
        assert thresholds["mq2.smoke_ppm"] > 24

    def test_load_save_baselines(self, tmp_path) -> None:
        Config._instance = None
        # Patch baseline file to point to tmp_path
        import fire_suppression.detection.baseline as baseline_module
        orig_default = baseline_module.DEFAULT_BASELINE_DAYS

        learner = BaselineLearner()
        learner._baseline_file = tmp_path / "test_baselines.json"
        learner.start_learning()
        for val in [20, 22, 21]:
            learner.record("mq2", SensorReading("mq2", 0, {"smoke_ppm": val}))
        learner.compute_baselines()

        # Create new learner pointing to same file
        learner2 = BaselineLearner()
        learner2._baseline_file = tmp_path / "test_baselines.json"
        loaded = learner2.load_baselines()
        assert loaded is True
        assert learner2.has_baselines
        assert "mq2.smoke_ppm" in learner2._baselines
        Config._instance = None
