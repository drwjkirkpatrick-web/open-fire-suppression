"""On-device ML false-positive suppression using Random Forest.

# ADD-004 — ML False Positive Suppression

Learns local patterns to distinguish real fires from cooking,
welding, vehicle exhaust, and other false-positive sources.
Uses scikit-learn's RandomForest for lightweight on-device inference.
"""
from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = "/var/lib/fire-suppression/models/fp_classifier.pkl"
FEATURES = [
    "temp_delta_1min",
    "smoke_ppm",
    "humidity_percent",
    "gas_resistance",
    "ir_temp",
    "flicker_score",
    "time_of_day",  # 0–24
    "day_of_week",  # 0–6
]


class FalsePositiveClassifier:
    """Random Forest classifier for false-positive suppression.

    Usage::

        clf = FalsePositiveClassifier()
        # During normal operation, collect samples
        clf.record_normal(reading)
        # When fire detected, check if it's likely a false positive
        is_false_positive = clf.predict(features)
    """

    def __init__(self, model_path: str | Path = MODEL_PATH, *, mock: bool = False) -> None:
        self.model_path = Path(model_path)
        self.mock = mock
        self._model = None
        self._normal_samples: list[list[float]] = []
        self._max_normal_samples = 1000
        self._load()

    def _load(self) -> None:
        if self.mock or not self.model_path.exists():
            return
        try:
            with open(self.model_path, "rb") as fh:
                self._model = pickle.load(fh)
            logger.info("Loaded FP classifier from %s", self.model_path)
        except Exception as exc:
            logger.warning("Failed to load FP classifier: %s", exc)

    def save(self) -> None:
        if self._model is None or self.mock:
            return
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.model_path, "wb") as fh:
                pickle.dump(self._model, fh)
        except Exception as exc:
            logger.warning("Failed to save FP classifier: %s", exc)

    def record_normal(self, features: dict[str, float]) -> None:
        """Record a normal (non-fire) sample for future training."""
        vec = self._features_to_vector(features)
        self._normal_samples.append(vec)
        if len(self._normal_samples) > self._max_normal_samples:
            self._normal_samples = self._normal_samples[-self._max_normal_samples:]

    def predict(self, features: dict[str, float]) -> tuple[bool, float]:
        """Predict whether this detection is a false positive.

        Returns:
            (is_false_positive, confidence)
        """
        if self.mock or self._model is None:
            # Rule-based fallback
            return self._rule_based_predict(features)

        try:
            import numpy as np
            vec = np.array(self._features_to_vector(features)).reshape(1, -1)
            proba = self._model.predict_proba(vec)[0]
            # Class 0 = real fire, Class 1 = false positive
            fp_confidence = proba[1]
            is_fp = fp_confidence > 0.7
            return is_fp, float(fp_confidence)
        except Exception as exc:
            logger.warning("FP classifier prediction failed: %s", exc)
            return self._rule_based_predict(features)

    def _rule_based_predict(self, features: dict[str, float]) -> tuple[bool, float]:
        """Fallback heuristic: cooking often has high temp but stable humidity."""
        temp = features.get("temp_delta_1min", 0)
        humidity = features.get("humidity_percent", 50)
        flicker = features.get("flicker_score", 0)

        # Cooking: high temp, stable humidity, no flicker
        if temp > 10 and humidity > 30 and flicker < 0.2:
            return True, 0.6
        return False, 0.3

    def train(self) -> None:
        """Train the classifier on collected normal samples + synthetic fire samples.

        Call this periodically (e.g., weekly) or after accumulating enough data.
        """
        if len(self._normal_samples) < 50:
            logger.warning("Not enough normal samples to train (%d)", len(self._normal_samples))
            return

        try:
            import numpy as np
            from sklearn.ensemble import RandomForestClassifier

            # Normal samples = class 1 (false positive)
            X_normal = np.array(self._normal_samples)
            y_normal = np.ones(len(X_normal))

            # Synthetic fire samples = class 0 (real fire)
            # Generate by amplifying temp, dropping humidity, adding flicker
            X_fire = X_normal.copy()
            X_fire[:, 0] *= 3.0   # temp_delta
            X_fire[:, 1] *= 5.0   # smoke
            X_fire[:, 2] *= 0.5   # humidity (fire is dry)
            X_fire[:, 5] = np.clip(X_fire[:, 5] + 0.5, 0, 1)  # flicker
            y_fire = np.zeros(len(X_fire))

            X = np.vstack([X_normal, X_fire])
            y = np.hstack([y_normal, y_fire])

            self._model = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42)
            self._model.fit(X, y)
            self.save()
            logger.info("FP classifier trained on %d samples", len(X))
        except ImportError:
            logger.warning("scikit-learn not installed — cannot train FP classifier")
        except Exception as exc:
            logger.error("FP classifier training failed: %s", exc)

    def _features_to_vector(self, features: dict[str, float]) -> list[float]:
        return [float(features.get(k, 0.0)) for k in FEATURES]

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    @property
    def normal_sample_count(self) -> int:
        return len(self._normal_samples)
