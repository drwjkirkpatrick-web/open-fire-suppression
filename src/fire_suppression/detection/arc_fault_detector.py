"""Electrical arc fault detection (AFCI) to prevent ignition.

# MOD-014 — Arc Fault Detector

Detects dangerous electrical arc faults before they cause fire:
- Series arcs: loose connections, broken conductors
- Parallel arcs: damaged insulation between hot and neutral/ground

Arc signatures:
- Random current waveform (not periodic like normal loads)
- High frequency noise (>1 MHz)
- Shoulders on current waveform
- Zero-crossing irregularities

Hardware: Non-invasive current transformers (SCT-013) + ADC,
or dedicated arc fault sensor ICs (Texas Instruments AFE).
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

# Arc detection thresholds
ARC_NOISE_THRESHOLD = 0.15  # Relative high-freq noise energy
ARC_CONFIDENCE_WARNING = 0.3
ARC_CONFIDENCE_ALERT = 0.6


@dataclass
class CurrentWaveform:
    timestamp: float
    samples: np.ndarray
    sample_rate: int
    rms_current: float
    zero_crossings: int


class ArcFaultDetector:
    """Electrical arc fault detector.

    Monitors current waveforms for arc fault signatures that
    precede electrical fires.
    """

    def __init__(
        self,
        sensor_id: str = "arc_fault_01",
        circuit_name: str = "main_panel",
        *,
        mock: bool = False,
    ) -> None:
        self.sensor_id = sensor_id
        self.circuit_name = circuit_name
        self.mock = mock
        self._waveforms: deque[CurrentWaveform] = deque(maxlen=300)
        self._running = False
        self._baseline_rms: float = 0.0
        self._calibrated = False

        logger.info("ArcFaultDetector %s on circuit '%s'", sensor_id, circuit_name)

    # ── Current Sampling ───────────────────────────────────────────

    def _generate_arc_waveform(self) -> np.ndarray:
        """Generate realistic arc fault waveform for mock mode."""
        sample_rate = 10000  # 10 kHz
        duration = 0.1  # 100 ms
        t = np.linspace(0, duration, int(sample_rate * duration))
        freq = 60.0

        # Base sine wave
        waveform = np.sin(2 * np.pi * freq * t) * 10.0

        # Add arc signature: random high-frequency bursts
        if np.random.random() < 0.5:
            burst_start = np.random.randint(0, len(t) - 500)
            burst = np.random.randn(500) * 5.0
            waveform[burst_start:burst_start+500] += burst

        # Add shoulder distortion (truncated peaks)
        if np.random.random() < 0.3:
            peaks = np.where(waveform > 8)[0]
            waveform[peaks] = 8 + np.random.randn(len(peaks)) * 0.5

        return waveform

    async def _read_waveform(self) -> CurrentWaveform | None:
        if self.mock:
            await asyncio.sleep(0.01)
            samples = self._generate_arc_waveform()
            return CurrentWaveform(
                timestamp=time.time(),
                samples=samples,
                sample_rate=10000,
                rms_current=np.sqrt(np.mean(samples**2)),
                zero_crossings=np.sum(np.diff(np.sign(samples)) != 0),
            )

        try:
            import board  # type: ignore
            import busio   # type: ignore
            import adafruit_ads1x15.ads1115 as ADS  # type: ignore
            from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore

            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c)
            chan = AnalogIn(ads, ADS.P0)
            samples = np.array([chan.value for _ in range(1000)])
            return CurrentWaveform(
                timestamp=time.time(),
                samples=samples,
                sample_rate=860,  # ADS1115 max
                rms_current=np.sqrt(np.mean(samples**2)),
                zero_crossings=np.sum(np.diff(np.sign(samples)) != 0),
            )
        except Exception:
            logger.exception("Current sampling failed")
            return None

    # ── Arc Signature Analysis ──────────────────────────────────────

    def _analyze_arc_signature(self, waveform: CurrentWaveform) -> dict[str, float]:
        """Analyze current waveform for arc fault signatures."""
        samples = waveform.samples
        n = len(samples)
        if n == 0:
            return {"confidence": 0.0, "noise_ratio": 0.0, "shoulder_score": 0.0}

        # FFT analysis
        fft = np.fft.rfft(samples)
        magnitude = np.abs(fft)
        freqs = np.fft.rfftfreq(n, 1.0 / waveform.sample_rate)

        # High-frequency noise (>1 kHz)
        hf_mask = freqs > 1000
        hf_energy = np.sum(magnitude[hf_mask]**2) if np.any(hf_mask) else 0
        total_energy = np.sum(magnitude**2) + 1e-9
        noise_ratio = hf_energy / total_energy

        # Shoulder detection: truncated peaks
        peak_indices = np.where(np.abs(samples) > np.percentile(np.abs(samples), 95))[0]
        shoulder_score = 0.0
        if len(peak_indices) > 0:
            # Check if peaks are "clipped" (shoulders)
            peak_values = np.abs(samples[peak_indices])
            expected_peak = np.percentile(np.abs(samples), 99)
            clipped = np.sum(peak_values < expected_peak * 0.9) / len(peak_indices)
            shoulder_score = clipped

        # Combine into confidence
        confidence = (noise_ratio * 0.5) + (shoulder_score * 0.3)
        # Zero-crossing irregularity bonus
        expected_zc = 2 * 60 * (n / waveform.sample_rate)
        zc_deviation = abs(waveform.zero_crossings - expected_zc) / expected_zc
        confidence += min(zc_deviation * 0.2, 0.2)

        return {
            "confidence": min(1.0, confidence),
            "noise_ratio": noise_ratio,
            "shoulder_score": shoulder_score,
            "zc_deviation": zc_deviation,
        }

    # ── Detection ─────────────────────────────────────────────────────

    async def detect(self) -> dict[str, Any]:
        """Analyze current for arc fault signatures."""
        waveform = await self._read_waveform()
        if not waveform:
            return {"sensor_id": self.sensor_id, "error": "read_failed", "arc_detected": False}

        self._waveforms.append(waveform)

        if not self._calibrated:
            if len(self._waveforms) >= 10:
                self._baseline_rms = np.mean([w.rms_current for w in self._waveforms])
                self._calibrated = True
            return {"sensor_id": self.sensor_id, "status": "calibrating", "arc_detected": False}

        analysis = self._analyze_arc_signature(waveform)
        confidence = analysis["confidence"]

        status = "clear"
        if confidence >= ARC_CONFIDENCE_ALERT:
            status = "alert"
        elif confidence >= ARC_CONFIDENCE_WARNING:
            status = "warning"

        return {
            "sensor_id": self.sensor_id,
            "timestamp": waveform.timestamp,
            "circuit": self.circuit_name,
            "status": status,
            "arc_detected": status == "alert",
            "confidence": round(confidence, 4),
            "rms_current": round(waveform.rms_current, 3),
            "baseline_rms": round(self._baseline_rms, 3),
            "analysis": {k: round(v, 4) for k, v in analysis.items()},
            "calibrated": self._calibrated,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "circuit": self.circuit_name,
            "calibrated": self._calibrated,
            "waveforms_stored": len(self._waveforms),
            "mock": self.mock,
        }
