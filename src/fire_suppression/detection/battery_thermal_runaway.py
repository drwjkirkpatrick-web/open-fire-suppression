"""Lithium-ion battery thermal runaway detection.

# MOD-015 — Battery Thermal Runaway Detection

Critical for EV charging stations, battery storage facilities,
and data centers. Li-ion thermal runaway progresses rapidly:

1. Stage 1: Abuse → temperature rise, gas venting
2. Stage 2: Separator breakdown → internal short
3. Stage 3: Thermal runaway → fire/explosion

Detection sensors:
- Temperature: rapid rise (>5°C/min)
- Gas: HF, CO₂, CH₄ venting
- Voltage: sudden drop
- Sound: popping/venting noise

Hardware: Thermocouples on battery pack, BMS voltage monitoring,
gas sensors (same as MOD-006 but focused on battery venting gases).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Thermal runaway thresholds
TEMP_RISE_RATE_C_MIN = 5.0   # °C per minute
TEMP_MAX_C = 80.0            # Absolute max before runaway likely
GAS_HF_THRESHOLD_PPM = 10.0  # HF from electrolyte decomposition
GAS_CO2_THRESHOLD_PPM = 5000.0
VOLTAGE_DROP_THRESHOLD = 0.5  # Volts sudden drop


@dataclass
class BatteryReading:
    timestamp: float
    cell_id: str
    temp_c: float
    voltage_v: float
    gas_hf_ppm: float
    gas_co2_ppm: float
    sound_level_db: float


class BatteryThermalRunawayDetector:
    """Li-ion battery thermal runaway detector.

    Monitors battery temperature, voltage, and venting gas for
    early detection of thermal runaway before fire/explosion.
    """

    def __init__(
        self,
        battery_id: str = "battery_01",
        cell_count: int = 16,
        *,
        mock: bool = False,
    ) -> None:
        self.battery_id = battery_id
        self.cell_count = cell_count
        self.mock = mock
        self._readings: dict[str, deque[BatteryReading]] = {
            f"cell_{i}": deque(maxlen=300) for i in range(cell_count)
        }
        self._running = False

        logger.info("BatteryThermalRunawayDetector %s: %d cells", battery_id, cell_count)

    # ── Reading ─────────────────────────────────────────────────────

    async def _read_cell(self, cell_id: str) -> BatteryReading | None:
        if self.mock:
            import random
            # Simulate approaching thermal runaway
            temp = 35.0 + random.gauss(0, 3)
            if random.random() < 0.1:
                temp += random.uniform(10, 30)  # Rapid rise
            return BatteryReading(
                timestamp=time.time(),
                cell_id=cell_id,
                temp_c=temp,
                voltage_v=3.7 + random.gauss(0, 0.05),
                gas_hf_ppm=max(0, random.gauss(2, 3)),
                gas_co2_ppm=420 + random.gauss(0, 100),
                sound_level_db=random.gauss(40, 5),
            )

        try:
            # Real BMS integration would go here
            # Typically via CAN bus or Modbus
            return BatteryReading(
                timestamp=time.time(),
                cell_id=cell_id,
                temp_c=0.0,
                voltage_v=0.0,
                gas_hf_ppm=0.0,
                gas_co2_ppm=0.0,
                sound_level_db=0.0,
            )
        except Exception:
            logger.exception("Battery read failed for %s", cell_id)
            return None

    # ── Detection ───────────────────────────────────────────────────

    async def detect(self) -> dict[str, Any]:
        """Analyze all cells for thermal runaway indicators."""
        all_cell_results = []
        max_stage = 0
        max_confidence = 0.0

        for cell_id in self._readings:
            reading = await self._read_cell(cell_id)
            if not reading:
                continue

            self._readings[cell_id].append(reading)
            if len(self._readings[cell_id]) < 5:
                continue

            recent = list(self._readings[cell_id])[-10:]
            temps = [r.temp_c for r in recent]
            voltages = [r.voltage_v for r in recent]
            hf_gases = [r.gas_hf_ppm for r in recent]

            # Calculate rise rate
            time_span_min = (recent[-1].timestamp - recent[0].timestamp) / 60.0
            temp_rise = (temps[-1] - temps[0]) / max(time_span_min, 0.1)

            # Stage detection
            stage = 0
            indicators = 0

            if temp_rise >= TEMP_RISE_RATE_C_MIN:
                stage = max(stage, 1)
                indicators += 1
            if temps[-1] >= TEMP_MAX_C:
                stage = max(stage, 2)
                indicators += 2
            if hf_gases[-1] >= GAS_HF_THRESHOLD_PPM:
                stage = max(stage, 1)
                indicators += 1
            if len(voltages) >= 2 and (voltages[-2] - voltages[-1]) >= VOLTAGE_DROP_THRESHOLD:
                stage = max(stage, 2)
                indicators += 2

            confidence = min(1.0, indicators / 6.0)
            max_stage = max(max_stage, stage)
            max_confidence = max(max_confidence, confidence)

            all_cell_results.append({
                "cell_id": cell_id,
                "stage": stage,
                "confidence": round(confidence, 4),
                "temp_c": round(temps[-1], 1),
                "temp_rise_c_min": round(temp_rise, 2),
                "voltage_v": round(voltages[-1], 3),
                "gas_hf_ppm": round(hf_gases[-1], 2),
            })

        status = "clear"
        if max_stage >= 2 or max_confidence >= 0.6:
            status = "alert"
        elif max_stage >= 1 or max_confidence >= 0.3:
            status = "warning"

        # Sort by stage descending
        all_cell_results.sort(key=lambda x: x["stage"], reverse=True)
        worst_cells = [c for c in all_cell_results if c["stage"] >= 1][:5]

        return {
            "battery_id": self.battery_id,
            "timestamp": time.time(),
            "status": status,
            "thermal_runaway_detected": status == "alert",
            "max_stage": max_stage,
            "max_confidence": round(max_confidence, 4),
            "cells_analyzed": len(all_cell_results),
            "cells_in_warning": len([c for c in all_cell_results if c["stage"] == 1]),
            "cells_in_alert": len([c for c in all_cell_results if c["stage"] >= 2]),
            "worst_cells": worst_cells,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "battery_id": self.battery_id,
            "cell_count": self.cell_count,
            "mock": self.mock,
        }
