"""Tests for V7-009 Occupancy-Aware Risk Map."""
import pytest

from fire_suppression.config import Config
from fire_suppression.detection.occupancy_risk_map import OccupancyAwareRiskMap


@pytest.fixture
def risk_map(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["risk_map"] = {
        "fire_weight": 0.5,
        "occupancy_weight": 0.2,
        "smoke_weight": 0.15,
        "heat_weight": 0.15,
    }
    return OccupancyAwareRiskMap(cfg)


def test_clear_zone_low_risk(risk_map):
    z = risk_map.update_zone("zone-1", occupancy=0, fire_state="clear", smoke_ppm=0.0, heat_c=20.0)
    assert z["risk"] == 0.0


def test_fire_with_occupancy_high_risk(risk_map):
    z = risk_map.update_zone("zone-1", occupancy=5, fire_state="confirmed", smoke_ppm=400.0, heat_c=85.0)
    assert z["risk"] >= 0.9


def test_safest_exit(risk_map):
    risk_map.update_zone("zone-1", exits=["exit-a", "exit-b"])
    risk_map.update_zone("exit-a", fire_state="clear", smoke_ppm=0.0, heat_c=20.0)
    risk_map.update_zone("exit-b", fire_state="warning", smoke_ppm=100.0, heat_c=50.0)
    assert risk_map.safest_exit("zone-1") == "exit-a"


def test_global_risk(risk_map):
    risk_map.update_zone("z1", fire_state="confirmed", occupancy=10)
    risk_map.update_zone("z2", fire_state="clear")
    assert risk_map.global_risk() > 0.5


def test_risk_report_sorts_descending(risk_map):
    risk_map.update_zone("low", fire_state="clear")
    risk_map.update_zone("high", fire_state="confirmed")
    report = risk_map.risk_report()
    assert report["zones"][0]["zone_id"] == "high"


def test_to_dict(risk_map):
    assert risk_map.to_dict()["feature_id"] == "V7-009"
    assert risk_map.to_dict()["zone_count"] == 0
