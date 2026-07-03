"""Kalman filter for multi-sensor fire intensity estimation.

# IMP-002 — Kalman Filter Sensor Fusion

Estimates a latent "fire intensity" state from noisy sensor observations.
The filter smooths transient noise and tracks trend direction, providing
a more robust detection signal than raw threshold comparisons.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class KalmanState:
    """Current state of the Kalman filter."""
    fire_intensity: float = 0.0      # Estimated fire intensity (0–1)
    temp_trend: float = 0.0          # Temperature change rate (°C/s)
    smoke_trend: float = 0.0         # Smoke change rate (ppm/s)
    covariance: np.ndarray | None = None


class FireIntensityKalmanFilter:
    """Unscented Kalman Filter (UKF) for fire intensity estimation.

    For simplicity on Pi 5, we use a linear Kalman filter with:
    - State: [fire_intensity, temp_trend, smoke_trend]
    - Observations: normalized sensor readings [temp_norm, smoke_norm, gas_norm]
    """

    def __init__(
        self,
        process_noise: float = 0.01,
        measurement_noise: float = 0.1,
        initial_state: list[float] | None = None,
    ) -> None:
        self.n_states = 3  # [fire_intensity, temp_trend, smoke_trend]
        self.n_obs = 3     # [temp_norm, smoke_norm, gas_norm]

        # State transition matrix (simple integrator model)
        self.F = np.array([
            [1.0, 0.1, 0.1],   # fire_intensity += 0.1*temp_trend + 0.1*smoke_trend
            [0.0, 0.9, 0.0],   # temp_trend decays
            [0.0, 0.0, 0.9],   # smoke_trend decays
        ])

        # Observation matrix (we observe weighted combinations)
        self.H = np.array([
            [0.5, 0.3, 0.0],   # temp_norm ≈ 0.5*fire + 0.3*temp_trend
            [0.4, 0.0, 0.3],   # smoke_norm ≈ 0.4*fire + 0.3*smoke_trend
            [0.3, 0.2, 0.2],   # gas_norm ≈ 0.3*fire + 0.2*temp_trend + 0.2*smoke_trend
        ])

        # Process noise covariance
        self.Q = np.eye(self.n_states) * process_noise

        # Measurement noise covariance
        self.R = np.eye(self.n_obs) * measurement_noise

        # Initial state
        self.x = np.array(initial_state or [0.0, 0.0, 0.0])

        # Initial covariance
        self.P = np.eye(self.n_states) * 1.0

        self._initialized = False

    def predict(self) -> KalmanState:
        """Predict step: advance state estimate."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self._to_state()

    def update(self, observations: dict[str, float]) -> KalmanState:
        """Update step: incorporate sensor observations.

        Args:
            observations: Dict of normalized sensor readings, e.g.::

                {"temp_norm": 0.7, "smoke_norm": 0.3, "gas_norm": 0.5}
        """
        z = self._observations_to_vector(observations)

        # Innovation
        y = z - self.H @ self.x

        # Innovation covariance
        S = self.H @ self.P @ self.H.T + self.R

        # Kalman gain
        K = self.P @ self.H.T @ np.linalg.inv(S)

        # State update
        self.x = self.x + K @ y

        # Covariance update (Joseph form for numerical stability)
        I_KH = np.eye(self.n_states) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ self.R @ K.T

        # Clamp fire_intensity to [0, 1]
        self.x[0] = max(0.0, min(1.0, self.x[0]))

        return self._to_state()

    def step(self, observations: dict[str, float]) -> KalmanState:
        """Run one full predict-update cycle."""
        self.predict()
        return self.update(observations)

    def _observations_to_vector(self, obs: dict[str, float]) -> np.ndarray:
        """Convert observation dict to numpy vector."""
        return np.array([
            obs.get("temp_norm", 0.0),
            obs.get("smoke_norm", 0.0),
            obs.get("gas_norm", 0.0),
        ])

    def _to_state(self) -> KalmanState:
        return KalmanState(
            fire_intensity=float(self.x[0]),
            temp_trend=float(self.x[1]),
            smoke_trend=float(self.x[2]),
            covariance=self.P.copy(),
        )

    @property
    def confidence(self) -> float:
        """Return current fire intensity estimate as confidence score."""
        return float(self.x[0])

    def reset(self) -> None:
        """Reset filter to initial state."""
        self.x = np.array([0.0, 0.0, 0.0])
        self.P = np.eye(self.n_states) * 1.0
        self._initialized = False
