"""Tests for Kalman filter sensor fusion.

# IMP-002 — Kalman Filter Sensor Fusion
"""
import numpy as np
import pytest

from fire_suppression.detection.kalman_fusion import FireIntensityKalmanFilter, KalmanState


class TestKalmanFilter:
    """# IMP-002 — Kalman Filter Sensor Fusion"""

    def test_initial_state_is_zero(self) -> None:
        kf = FireIntensityKalmanFilter()
        assert kf.confidence == 0.0

    def test_predict_does_not_crash(self) -> None:
        kf = FireIntensityKalmanFilter()
        state = kf.predict()
        assert isinstance(state, KalmanState)
        assert state.fire_intensity == pytest.approx(0.0, abs=0.01)

    def test_update_increases_fire_estimate(self) -> None:
        kf = FireIntensityKalmanFilter()
        kf.predict()
        state = kf.update({"temp_norm": 0.8, "smoke_norm": 0.7, "gas_norm": 0.6})
        assert state.fire_intensity > 0.0
        assert state.fire_intensity <= 1.0

    def test_step_returns_state(self) -> None:
        kf = FireIntensityKalmanFilter()
        state = kf.step({"temp_norm": 0.5, "smoke_norm": 0.5, "gas_norm": 0.5})
        assert isinstance(state, KalmanState)

    def test_multiple_updates_converge(self) -> None:
        kf = FireIntensityKalmanFilter()
        obs = {"temp_norm": 0.9, "smoke_norm": 0.9, "gas_norm": 0.9}
        for _ in range(10):
            kf.step(obs)
        assert kf.confidence > 0.5

    def test_reset_clears_state(self) -> None:
        kf = FireIntensityKalmanFilter()
        kf.step({"temp_norm": 0.9, "smoke_norm": 0.9, "gas_norm": 0.9})
        kf.reset()
        assert kf.confidence == 0.0

    def test_clamping_to_one(self) -> None:
        kf = FireIntensityKalmanFilter()
        obs = {"temp_norm": 1.0, "smoke_norm": 1.0, "gas_norm": 1.0}
        for _ in range(20):
            kf.step(obs)
        assert kf.confidence <= 1.0
        assert kf.confidence >= 0.0
