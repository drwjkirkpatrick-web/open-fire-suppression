"""Miniaturized gas chromatograph for ultra-precise combustion gas analysis.

# MOD-006 — Gas Chromatograph Fire Detection

Separates combustion gases (CO, CO₂, H₂, CH₄, C₂H₄) by retention time.
Highest accuracy but highest cost. Used for reference calibration of
other sensors and for high-risk environments (battery factories,
chemical plants).

Hardware: Emerging MEMS GC devices (e.g., Owlstone Panorama).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Gas detection thresholds (ppm)
CO_WARNING = 50     # OSHA 8-hr TWA = 50 ppm
CO_ALERT = 200      # IDLH = 1200 ppm
CO2_WARNING = 5000  # OSHA PEL = 5000 ppm
CO2_ALERT = 40000   # Immediately dangerous
H2_WARNING = 1000   # LEL = 4% = 40,000 ppm
CH4_WARNING = 1000  # LEL = 5% = 50,000 ppm
C2H4_WARNING = 500  # Ethylene (plant stress indicator)


@dataclass
class GCReading:
    timestamp: float
    retention_times: dict[str, float]   # Gas -> retention time (s)
    concentrations: dict[str, float]    # Gas -> concentration (ppm)
    carrier_flow: float                 # mL/min
    column_temp: float                  # °C
    cycle_time: float                   # seconds per analysis


class GasChromatographDetector:
    """Miniaturized gas chromatograph fire detector.

    Separates and quantifies individual combustion gases to provide
    definitive fire detection and characterization.
    """

    def __init__(
        self,
        sensor_id: str = "gc_01",
        port: str = "/dev/ttyUSB1",
        *,
        mock: bool = False,
    ) -> None:
        self.sensor_id = sensor_id
        self.port = port
        self.mock = mock
        self._readings: list[GCReading] = []
        self._running = False
        self._calibrated = False
        self._baseline: dict[str, float] = {}

        logger.info("GasChromatographDetector %s on %s", sensor_id, port)

    # ── Calibration ─────────────────────────────────────────────────

    async def calibrate(self) -> None:
        """Calibrate baseline in clean air."""
        logger.info("Calibrating GC %s...", self.sensor_id)
        if self.mock:
            self._baseline = {
                "CO": 2.0, "CO2": 420.0, "H2": 0.5,
                "CH4": 1.8, "C2H4": 0.1,
            }
            self._calibrated = True
            await asyncio.sleep(0.1)
            return

        # Real calibration: run clean air sample
        try:
            import serial
            with serial.Serial(self.port, 9600, timeout=5) as s:
                s.write(b"CALIBRATE\n")
                response = s.readline().decode().strip()
                if response.startswith("OK"):
                    self._calibrated = True
        except Exception:
            logger.exception("GC calibration failed")

    # ── Reading ─────────────────────────────────────────────────────

    async def _read_analysis(self) -> GCReading | None:
        if self.mock:
            await asyncio.sleep(0.1)
            import random
            # Simulate elevated combustion gases
            return GCReading(
                timestamp=time.time(),
                retention_times={"CO": 45.2, "CO2": 28.1, "H2": 12.5, "CH4": 38.7, "C2H4": 52.3},
                concentrations={
                    "CO": 85.0 + random.gauss(0, 10),
                    "CO2": 800.0 + random.gauss(0, 50),
                    "H2": 5.0 + random.gauss(0, 2),
                    "CH4": 12.0 + random.gauss(0, 3),
                    "C2H4": 1.5 + random.gauss(0, 0.5),
                },
                carrier_flow=1.5,
                column_temp=45.0,
                cycle_time=60.0,
            )

        try:
            import serial
            with serial.Serial(self.port, 9600, timeout=5) as s:
                s.write(b"READ\n")
                data = s.readline().decode().strip()
                if data.startswith("DATA"):
                    parts = data.split(",")
                    return GCReading(
                        timestamp=time.time(),
                        retention_times={parts[i]: float(parts[i+1]) for i in range(1, len(parts), 2)},
                        concentrations={parts[i]: float(parts[i+1]) for i in range(1, len(parts), 2)},
                        carrier_flow=1.5,
                        column_temp=45.0,
                        cycle_time=60.0,
                    )
        except Exception:
            logger.exception("GC read failed")
        return None

    # ── Detection ─────────────────────────────────────────────────────

    async def detect(self) -> dict[str, Any]:
        """Analyze gas concentrations for fire signatures."""
        reading = await self._read_analysis()
        if not reading:
            return {"sensor_id": self.sensor_id, "error": "read_failed", "fire_detected": False}

        self._readings.append(reading)
        if len(self._readings) > 100:
            self._readings = self._readings[-50:]

        if not self._calibrated:
            return {"sensor_id": self.sensor_id, "status": "calibrating", "fire_detected": False}

        # Check each gas against thresholds
        alerts = {}
        warnings = {}
        fire_indicators = 0

        for gas, ppm in reading.concentrations.items():
            if gas == "CO":
                if ppm >= CO_ALERT:
                    alerts["CO"] = ppm
                    fire_indicators += 2
                elif ppm >= CO_WARNING:
                    warnings["CO"] = ppm
                    fire_indicators += 1
            elif gas == "CO2":
                if ppm >= CO2_ALERT:
                    alerts["CO2"] = ppm
                    fire_indicators += 1
                elif ppm >= CO2_WARNING:
                    warnings["CO2"] = ppm

            elif gas == "H2" and ppm >= H2_WARNING:
                warnings["H2"] = ppm
                fire_indicators += 1
            elif gas == "CH4" and ppm >= CH4_WARNING:
                warnings["CH4"] = ppm
                fire_indicators += 1
            elif gas == "C2H4" and ppm >= C2H4_WARNING:
                warnings["C2H4"] = ppm
                fire_indicators += 1

        # Fire signature: CO elevated + CO2 elevated + H2 present
        confidence = min(1.0, fire_indicators / 5.0)

        status = "clear"
        if confidence >= 0.6 or len(alerts) >= 2:
            status = "alert"
        elif confidence >= 0.3 or len(warnings) >= 2:
            status = "warning"

        return {
            "sensor_id": self.sensor_id,
            "timestamp": reading.timestamp,
            "status": status,
            "fire_detected": status == "alert",
            "confidence": round(confidence, 4),
            "concentrations_ppm": {k: round(v, 2) for k, v in reading.concentrations.items()},
            "alerts": alerts,
            "warnings": warnings,
            "cycle_time_sec": reading.cycle_time,
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
            "readings_stored": len(self._readings),
            "mock": self.mock,
        }
