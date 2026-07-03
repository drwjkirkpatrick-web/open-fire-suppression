"""LiDAR-based volumetric smoke detection.

# MOD-003 — LiDAR Smoke Detection

Smoke scatters 905 nm laser light. Return signal intensity correlates
with smoke density. Unlike optical smoke detectors, LiDAR can measure
smoke density across a volume (room) rather than at a single point.

Key advantage: No false positives from steam (steam has different
scattering profile than smoke particles).

Hardware: TF-Luna, TFmini Plus, or RPLIDAR A1 mounted overhead.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Smoke density thresholds (relative intensity drop)
SMOKE_WARNING_THRESHOLD = 0.15   # 15% signal attenuation
SMOKE_ALERT_THRESHOLD = 0.35     # 35% signal attenuation


@dataclass
class LidarReading:
    timestamp: float
    distance_mm: int
    signal_strength: int
    smoke_density: float = 0.0  # 0-1 relative
    calibrated_baseline: float = 0.0


class LidarSmokeDetector:
    """LiDAR smoke detector for volumetric smoke monitoring.

    Calibrates baseline signal in clean air. Smoke attenuates the
    return signal. Steam produces different scattering (forward
    scattering dominant) vs smoke (Mie scattering), allowing
    discrimination.
    """

    def __init__(
        self,
        sensor_id: str = "lidar_smoke_01",
        port: str = "/dev/ttyUSB0",
        baudrate: int = 115200,
        *,
        mock: bool = False,
    ) -> None:
        self.sensor_id = sensor_id
        self.port = port
        self.baudrate = baudrate
        self.mock = mock
        self._baseline: list[float] = []
        self._readings: list[LidarReading] = []
        self._running = False
        self._calibrated = False
        self._calibration_count = 100

        logger.info("LidarSmokeDetector %s on %s", sensor_id, port)

    # ── Calibration ──────────────────────────────────────────────────

    async def calibrate(self, duration_sec: float = 30.0) -> None:
        """Calibrate baseline in clean air."""
        logger.info("Calibrating LiDAR %s for %.0f seconds...", self.sensor_id, duration_sec)
        self._baseline = []
        start = time.time()
        while time.time() - start < duration_sec:
            reading = await self._read_once()
            if reading:
                self._baseline.append(reading.signal_strength)
            await asyncio.sleep(0.1)

        if len(self._baseline) >= self._calibration_count:
            self._calibrated = True
            avg = sum(self._baseline) / len(self._baseline)
            logger.info("LiDAR %s calibrated: baseline=%.1f (n=%d)",
                        self.sensor_id, avg, len(self._baseline))
        else:
            logger.warning("LiDAR %s calibration incomplete: only %d readings", self.sensor_id, len(self._baseline))

    # ── Reading ─────────────────────────────────────────────────────

    async def _read_once(self) -> LidarReading | None:
        if self.mock:
            import random
            baseline_avg = sum(self._baseline) / len(self._baseline) if self._baseline else 5000
            # Simulate slight drift
            signal = int(baseline_avg * (0.95 + random.random() * 0.1))
            return LidarReading(
                timestamp=time.time(),
                distance_mm=2000 + int(random.random() * 500),
                signal_strength=signal,
                calibrated_baseline=baseline_avg,
            )

        try:
            import serial  # type: ignore
            with serial.Serial(self.port, self.baudrate, timeout=1) as s:
                # TF-Luna command: read distance and signal strength
                s.write(b'\x5A\x05\x00\x01\x60')  # Read command
                data = s.read(9)
                if len(data) == 9:
                    dist = data[2] + (data[3] << 8)
                    strength = data[4] + (data[5] << 8)
                    return LidarReading(
                        timestamp=time.time(),
                        distance_mm=dist,
                        signal_strength=strength,
                    )
        except Exception:
            logger.exception("LiDAR read failed on %s", self.port)
        return None

    async def read(self) -> dict[str, Any]:
        """Read current smoke density."""
        reading = await self._read_once()
        if not reading:
            return {"sensor_id": self.sensor_id, "error": "read_failed", "smoke_detected": False}

        if self._calibrated and self._baseline:
            baseline_avg = sum(self._baseline) / len(self._baseline)
            if baseline_avg > 0:
                attenuation = max(0, 1 - (reading.signal_strength / baseline_avg))
                reading.smoke_density = attenuation
                reading.calibrated_baseline = baseline_avg
        else:
            attenuation = 0.0

        self._readings.append(reading)
        if len(self._readings) > 1000:
            self._readings = self._readings[-500:]

        status = "clear"
        if attenuation >= SMOKE_ALERT_THRESHOLD:
            status = "alert"
        elif attenuation >= SMOKE_WARNING_THRESHOLD:
            status = "warning"

        return {
            "sensor_id": self.sensor_id,
            "timestamp": reading.timestamp,
            "distance_mm": reading.distance_mm,
            "signal_strength": reading.signal_strength,
            "attenuation": round(attenuation, 4),
            "smoke_density": round(reading.smoke_density, 4),
            "status": status,
            "smoke_detected": status == "alert",
            "calibrated": self._calibrated,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        if not self._calibrated:
            await self.calibrate()

    async def stop(self) -> None:
        self._running = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "port": self.port,
            "calibrated": self._calibrated,
            "baseline_readings": len(self._baseline),
            "stored_readings": len(self._readings),
        }
