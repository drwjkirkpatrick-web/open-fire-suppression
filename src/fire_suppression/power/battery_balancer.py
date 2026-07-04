"""V7-007 — Smart Battery Load Balancer

Estimates remaining runtime under active fire load and prioritizes actuators
and alerts to extend safe operation during a power outage.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fire_suppression.config import Config

logger = logging.getLogger(__name__)


class PowerMode(Enum):
    NORMAL = "normal"
    CONSERVATION = "conservation"
    EMERGENCY = "emergency"


@dataclass
class LoadEstimate:
    mode: PowerMode
    battery_percent: float
    estimated_minutes: float
    active_load_watts: float
    recommended_actions: list[str]


class SmartBatteryLoadBalancer:
    """Balances load to maximize runtime during fire events on battery."""

    # Approximate power draw in watts per subsystem
    _LOADS: dict[str, float] = {
        "sensors": 3.0,
        "camera": 2.5,
        "detection": 2.0,
        "relay_active": 8.0,
        "buzzer": 2.0,
        "tts": 4.0,
        "cellular": 5.0,
        "wifi": 1.5,
        "led_strip": 6.0,
        "lte": 7.0,
    }

    def __init__(self, config: Config | None = None, mock: bool = False) -> None:
        self.config = config or Config()
        self.mock = mock
        cfg = self.config.section("battery_balancer")
        self.battery_capacity_wh = float(cfg.get("capacity_wh", 60.0))
        self.conservation_threshold = float(cfg.get("conservation_threshold", 50.0))
        self.emergency_threshold = float(cfg.get("emergency_threshold", 20.0))
        self.safe_shutdown_threshold = float(cfg.get("safe_shutdown_threshold", 10.0))

    def estimate(self, battery_percent: float, active_subsystems: list[str]) -> LoadEstimate:
        total_w = sum(self._LOADS.get(s, 1.0) for s in active_subsystems)
        if total_w <= 0:
            total_w = 1.0
        available_wh = self.battery_capacity_wh * (battery_percent / 100.0)
        minutes = (available_wh / total_w) * 60.0

        mode = PowerMode.NORMAL
        actions: list[str] = []
        # Thresholds are expressed as percentages 0..100 in config; compare battery_percent directly
        if battery_percent <= self.safe_shutdown_threshold:
            mode = PowerMode.EMERGENCY
            actions.append("initiate_safe_shutdown")
        elif battery_percent <= self.emergency_threshold:
            mode = PowerMode.EMERGENCY
            actions.extend(["disable_camera", "disable_tts", "disable_led_strip", "keep_relay_priority"])
        elif battery_percent <= self.conservation_threshold:
            mode = PowerMode.CONSERVATION
            actions.extend(["disable_camera", "reduce_tts_volume", "limit_sms_rate"])

        return LoadEstimate(
            mode=mode,
            battery_percent=battery_percent,
            estimated_minutes=round(minutes, 1),
            active_load_watts=round(total_w, 2),
            recommended_actions=actions,
        )

    def prioritize_actuators(self, actuators: list[str], battery_percent: float) -> list[str]:
        """Return actuators in priority order given remaining battery."""
        if battery_percent <= self.emergency_threshold:
            priority = ["relay_0", "buzzer"]
        else:
            priority = ["relay_0", "sprinkler_valve", "buzzer", "led_strip", "tts"]
        return [a for a in priority if a in actuators] + [a for a in actuators if a not in priority]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": "V7-007",
            "healthy": True,
            "capacity_wh": self.battery_capacity_wh,
            "thresholds": {
                "conservation": self.conservation_threshold,
                "emergency": self.emergency_threshold,
                "safe_shutdown": self.safe_shutdown_threshold,
            },
            "mock": self.mock,
        }

    def get_status(self, battery_percent: float = 100.0, active_subsystems: list[str] | None = None) -> dict[str, Any]:
        est = self.estimate(battery_percent, active_subsystems or ["sensors", "detection", "wifi"])
        return {
            "feature_id": "V7-007",
            "mode": est.mode.value,
            "battery_percent": est.battery_percent,
            "estimated_minutes": est.estimated_minutes,
            "active_load_watts": est.active_load_watts,
            "recommended_actions": est.recommended_actions,
            "timestamp": time.time(),
        }
