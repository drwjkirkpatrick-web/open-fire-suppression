"""Multi-zone fire detection and suppression architecture.

# IMP-004 — Multi-Zone Architecture

Each zone has its own sensors, thresholds, and actuation relays.
Zones operate independently but report to a unified dashboard.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fire_suppression.config import Config
from fire_suppression.detection.engine import DetectionResult, FireDetectionEngine, FireState
from fire_suppression.safety.interlock import SafetyInterlock

if TYPE_CHECKING:
    from fire_suppression.sensors.base import SensorReading

logger = logging.getLogger(__name__)


@dataclass
class ZoneConfig:
    """Configuration for a single detection/suppression zone."""
    name: str
    sensors: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    relay_indices: list[int] = field(default_factory=list)
    enabled: bool = True


class ZoneManager:
    """Manages multiple independently configured fire detection zones.

    Usage::

        zones = ZoneManager(config)
        zones.add_zone(ZoneConfig(name="kitchen", sensors=["mq2", "sht40"], relay_indices=[0]))
        result = zones.detect_zone("kitchen", readings)
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._zones: dict[str, ZoneConfig] = {}
        self._engines: dict[str, FireDetectionEngine] = {}
        self._safety = SafetyInterlock(self.config)
        self._load_from_config()

    def _load_from_config(self) -> None:
        """Load zone definitions from config if present."""
        zones_cfg = self.config.raw.get("zones", {})
        for name, zone_data in zones_cfg.items():
            self.add_zone(ZoneConfig(
                name=name,
                sensors=zone_data.get("sensors", []),
                thresholds=zone_data.get("thresholds", {}),
                relay_indices=zone_data.get("relay_indices", []),
                enabled=zone_data.get("enabled", True),
            ))

    def add_zone(self, zone: ZoneConfig) -> None:
        """Add a new zone."""
        self._zones[zone.name] = zone
        # Create a per-zone detection engine with zone-specific thresholds
        engine = FireDetectionEngine(self.config)
        if zone.thresholds:
            # Override engine thresholds with zone-specific values
            engine.single_thresholds.update(zone.thresholds)
        self._engines[zone.name] = engine
        logger.info("Zone added: %s (sensors: %s, relays: %s)",
                    zone.name, zone.sensors, zone.relay_indices)

    def detect_zone(self, zone_name: str, readings: dict[str, SensorReading | None]) -> DetectionResult:
        """Run fire detection for a specific zone using only its configured sensors."""
        if zone_name not in self._zones:
            logger.warning("Unknown zone: %s", zone_name)
            return DetectionResult(state=FireState.CLEAR, confidence=0.0, reason="unknown_zone")

        zone = self._zones[zone_name]
        if not zone.enabled:
            return DetectionResult(state=FireState.CLEAR, confidence=0.0, reason="zone_disabled")

        # Filter readings to only zone sensors
        zone_readings = {
            name: reading for name, reading in readings.items()
            if name in zone.sensors or name.startswith("picamera")  # Camera shared across zones
        }

        engine = self._engines[zone_name]
        return engine.detect(zone_readings)

    def detect_all(self, readings: dict[str, SensorReading | None]) -> dict[str, DetectionResult]:
        """Run detection for all enabled zones and return results."""
        results = {}
        for name, zone in self._zones.items():
            if zone.enabled:
                results[name] = self.detect_zone(name, readings)
        return results

    def get_zone_relay_indices(self, zone_name: str) -> list[int]:
        """Get relay indices for a zone's suppression actuators."""
        zone = self._zones.get(zone_name)
        return zone.relay_indices if zone else []

    def list_zones(self) -> list[str]:
        """Return list of all zone names."""
        return list(self._zones.keys())

    def get_zone_status(self, zone_name: str) -> dict:
        """Return current status summary for a zone."""
        zone = self._zones.get(zone_name)
        if not zone:
            return {}
        engine = self._engines.get(zone_name)
        return {
            "name": zone.name,
            "enabled": zone.enabled,
            "sensors": zone.sensors,
            "relay_indices": zone.relay_indices,
            "thresholds": zone.thresholds,
            "detection_state": engine.detect({}).state.value if engine else "unknown",
        }
