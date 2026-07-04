"""Tests for V7-007 Smart Battery Load Balancer."""
import pytest

from fire_suppression.config import Config
from fire_suppression.power.battery_balancer import SmartBatteryLoadBalancer, PowerMode


@pytest.fixture
def balancer(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["battery_balancer"] = {
        "capacity_wh": 60.0,
        "conservation_threshold": 50.0,
        "emergency_threshold": 20.0,
        "safe_shutdown_threshold": 10.0,
    }
    return SmartBatteryLoadBalancer(cfg)


def test_estimate_normal(balancer):
    est = balancer.estimate(80.0, ["sensors", "detection", "wifi"])
    assert est.mode == PowerMode.NORMAL
    assert est.estimated_minutes > 0


def test_estimate_conservation(balancer):
    est = balancer.estimate(40.0, ["sensors", "camera", "detection", "wifi"])
    assert est.mode == PowerMode.CONSERVATION
    assert "disable_camera" in est.recommended_actions


def test_estimate_emergency(balancer):
    est = balancer.estimate(15.0, ["sensors", "camera", "relay_active", "buzzer"])
    assert est.mode == PowerMode.EMERGENCY
    assert "keep_relay_priority" in est.recommended_actions


def test_safe_shutdown(balancer):
    est = balancer.estimate(8.0, ["sensors"])
    assert est.mode == PowerMode.EMERGENCY
    assert "initiate_safe_shutdown" in est.recommended_actions


def test_prioritize_actuators_emergency(balancer):
    acts = ["relay_0", "led_strip", "tts", "buzzer", "sprinkler_valve"]
    ordered = balancer.prioritize_actuators(acts, 15.0)
    assert ordered[0] == "relay_0"
    assert ordered[1] == "buzzer"
    assert "led_strip" not in ordered[:2]


def test_to_dict(balancer):
    assert balancer.to_dict()["feature_id"] == "V7-007"
    assert balancer.to_dict()["capacity_wh"] == 60.0


def test_get_status(balancer):
    status = balancer.get_status(70.0, ["sensors", "wifi"])
    assert status["feature_id"] == "V7-007"
    assert status["mode"] == PowerMode.NORMAL.value
