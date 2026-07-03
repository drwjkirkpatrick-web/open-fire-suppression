"""Tests for multi-zone architecture.

# IMP-004 — Multi-Zone Architecture
"""
import pytest

from fire_suppression.config import Config
from fire_suppression.detection.zones import ZoneConfig, ZoneManager
from fire_suppression.sensors.base import SensorReading


class TestZoneManager:
    """# IMP-004 — Multi-Zone Architecture"""

    def setup_method(self) -> None:
        Config._instance = None

    def test_add_zone(self) -> None:
        zm = ZoneManager()
        zm.add_zone(ZoneConfig(name="kitchen", sensors=["mq2", "sht40"], relay_indices=[0]))
        assert "kitchen" in zm.list_zones()

    def test_zone_isolation(self) -> None:
        zm = ZoneManager()
        zm.add_zone(ZoneConfig(name="kitchen", sensors=["mq2"], relay_indices=[0]))
        zm.add_zone(ZoneConfig(name="garage", sensors=["mq2"], relay_indices=[1]))

        readings = {
            "mq2": SensorReading("mq2", 0, {"smoke_ppm": 200}),
            "sht40": SensorReading("sht40", 0, {"temperature_c": 35}),
        }
        results = zm.detect_all(readings)
        assert "kitchen" in results
        assert "garage" in results

    def test_disabled_zone_not_detected(self) -> None:
        zm = ZoneManager()
        zm.add_zone(ZoneConfig(name="offline", sensors=["mq2"], enabled=False))
        readings = {"mq2": SensorReading("mq2", 0, {"smoke_ppm": 200})}
        result = zm.detect_zone("offline", readings)
        assert result.reason == "zone_disabled"

    def test_relay_indices(self) -> None:
        zm = ZoneManager()
        zm.add_zone(ZoneConfig(name="server", sensors=["mq2"], relay_indices=[2, 3]))
        assert zm.get_zone_relay_indices("server") == [2, 3]
