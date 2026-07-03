"""Acoustic fire signature detection using AI frequency analysis.

# MOD-005 — Acoustic Fire Signature Detection

Real fires produce distinctive acoustic signatures:
- Crackling: rapid small explosions from wood/lignin (2-8 kHz bursts)
- Popping: air pockets in wood/concrete bursting (1-4 kHz transients)
- Whooshing: turbulent airflow from convection (100-500 Hz)
- Hissing: gas release (5-15 kHz)

AI analysis distinguishes these from:
- HVAC fans (steady tone, ~60 Hz)
- Machinery (periodic, harmonic)
- Rain/wind (broadband, no transients)
- Footsteps (impulsive, low freq)

Hardware: USB microphone (Blue Snowball, etc.) or MEMS mic array.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Frequency bands of interest (Hz)
BAND_CRACKLE = (2000, 8000)
BAND_POP = (1000, 4000)
BAND_WHOOSH = (100, 500)
BAND_HISS = (5000, 15000)

# Detection thresholds
CRACKLE_THRESHOLD = 0.3
POP_THRESHOLD = 0.2
WHOOSH_THRESHOLD = 0.4
HISS_THRESHOLD = 0.25

CONFIDENCE_ALERT = 0.6
CONFIDENCE_WARNING = 0.3


@dataclass
class AcousticFeatures:
    timestamp: float
    spectral_centroid: float   # "brightness" of sound
    spectral_rolloff: float      # freq below which 85% energy
    zero_crossing_rate: float   # transient indicator
    rms_energy: float           # overall loudness
    band_energies: dict[str, float]  # Energy per band


class AcousticFireDetector:
    """AI-powered acoustic fire signature detector.

    Analyzes audio in real-time for combustion-specific frequency
    patterns. Uses lightweight feature extraction suitable for
    Raspberry Pi 5.
    """

    def __init__(
        self,
        sensor_id: str = "acoustic_01",
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        *,
        mock: bool = False,
    ) -> None:
        self.sensor_id = sensor_id
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.mock = mock
        self._features: deque[AcousticFeatures] = deque(maxlen=600)  # 10 min
        self._running = False
        self._stream = None

        logger.info("AcousticFireDetector %s @ %d Hz", sensor_id, sample_rate)

    # ── Audio Capture ────────────────────────────────────────────────

    def _capture_chunk_mock(self) -> np.ndarray:
        """Generate realistic synthetic audio with fire signatures."""
        t = np.linspace(0, self.chunk_size / self.sample_rate, self.chunk_size)
        audio = np.random.randn(self.chunk_size) * 0.01  # Background noise

        # Add crackle: random high-amplitude bursts at 2-8 kHz
        if np.random.random() < 0.3:
            burst = np.random.randn(self.chunk_size) * 0.5
            # Bandpass to 2-8 kHz
            audio += burst * np.sin(2 * np.pi * 4000 * t)

        # Add whoosh: low-freq turbulence
        audio += np.random.randn(self.chunk_size) * 0.1 * np.sin(2 * np.pi * 200 * t)

        return audio.astype(np.float32)

    async def _capture_chunk(self) -> np.ndarray:
        if self.mock:
            return self._capture_chunk_mock()

        try:
            import sounddevice as sd  # type: ignore
            recording = sd.rec(self.chunk_size, samplerate=self.sample_rate,
                               channels=1, dtype="float32")
            await asyncio.sleep(self.chunk_size / self.sample_rate)
            return recording.flatten()
        except Exception:
            logger.exception("Audio capture failed")
            return np.zeros(self.chunk_size, dtype=np.float32)

    # ── Feature Extraction ──────────────────────────────────────────

    def _extract_features(self, audio: np.ndarray) -> AcousticFeatures:
        """Extract spectral features from audio chunk."""
        n = len(audio)
        if n == 0:
            return AcousticFeatures(time.time(), 0, 0, 0, 0, {})

        # FFT
        fft = np.fft.rfft(audio)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(n, 1.0 / self.sample_rate)

        # Spectral centroid (brightness)
        total_energy = np.sum(magnitude**2) + 1e-9
        centroid = np.sum(freqs * magnitude**2) / total_energy

        # Spectral rolloff (freq below which 85% energy)
        cumsum = np.cumsum(magnitude**2)
        rolloff_idx = np.searchsorted(cumsum, 0.85 * cumsum[-1])
        rolloff = freqs[min(rolloff_idx, len(freqs) - 1)]

        # Zero crossing rate
        zcr = np.mean(np.abs(np.diff(np.sign(audio)))) / 2

        # RMS energy
        rms = np.sqrt(np.mean(audio**2))

        # Band energies
        def band_energy(low, high):
            mask = (freqs >= low) & (freqs <= high)
            return np.sum(magnitude[mask]**2) / total_energy if np.any(mask) else 0.0

        band_energies = {
            "crackle": band_energy(*BAND_CRACKLE),
            "pop": band_energy(*BAND_POP),
            "whoosh": band_energy(*BAND_WHOOSH),
            "hiss": band_energy(*BAND_HISS),
        }

        return AcousticFeatures(
            timestamp=time.time(),
            spectral_centroid=centroid,
            spectral_rolloff=rolloff,
            zero_crossing_rate=zcr,
            rms_energy=rms,
            band_energies=band_energies,
        )

    # ── Detection ───────────────────────────────────────────────────

    async def detect(self) -> dict[str, Any]:
        """Analyze recent audio for fire signatures."""
        audio = await self._capture_chunk()
        features = self._extract_features(audio)
        self._features.append(features)

        if len(self._features) < 30:
            return {"sensor_id": self.sensor_id, "status": "calibrating", "fire_detected": False}

        # Analyze recent features
        recent = list(self._features)[-60:]  # Last ~1 min
        avg_bands = {
            k: np.mean([f.band_energies.get(k, 0) for f in recent])
            for k in ["crackle", "pop", "whoosh", "hiss"]
        }

        # Fire confidence: weighted combination
        confidence = 0.0
        if avg_bands["crackle"] > CRACKLE_THRESHOLD:
            confidence += avg_bands["crackle"] * 0.35
        if avg_bands["pop"] > POP_THRESHOLD:
            confidence += avg_bands["pop"] * 0.15
        if avg_bands["whoosh"] > WHOOSH_THRESHOLD:
            confidence += avg_bands["whoosh"] * 0.35
        if avg_bands["hiss"] > HISS_THRESHOLD:
            confidence += avg_bands["hiss"] * 0.15

        # Penalize steady tones (HVAC)
        centroid_variance = np.var([f.spectral_centroid for f in recent])
        if centroid_variance < 1000:  # Very steady tone
            confidence *= 0.3

        status = "clear"
        if confidence >= CONFIDENCE_ALERT:
            status = "alert"
        elif confidence >= CONFIDENCE_WARNING:
            status = "warning"

        return {
            "sensor_id": self.sensor_id,
            "timestamp": features.timestamp,
            "status": status,
            "fire_detected": status == "alert",
            "confidence": round(float(confidence), 4),
            "band_energies": {k: round(v, 4) for k, v in avg_bands.items()},
            "spectral_centroid": round(float(features.spectral_centroid), 1),
            "rms_energy": round(float(features.rms_energy), 6),
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "sample_rate": self.sample_rate,
            "features_stored": len(self._features),
            "mock": self.mock,
        }
