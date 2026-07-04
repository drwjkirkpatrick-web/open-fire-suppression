"""Tests for V7-001 Alert Prioritizer."""
import pytest

from fire_suppression.alerts.alert_prioritizer import Alert, AlertPrioritizer, AlertType, Priority
from fire_suppression.config import Config


@pytest.fixture
def prioritizer(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["alert_prioritizer"] = {
        "occupancy_weight": 0.15,
        "night_boost": 0.15,
        "ack_penalty": -0.10,
        "repeat_decay": 0.05,
    }
    return AlertPrioritizer(cfg)


def test_fire_confirmed_is_critical(prioritizer):
    a = Alert("a1", AlertType.FIRE_CONFIRMED, "Fire!", "critical")
    result = prioritizer.process(a)
    assert result["priority"] == Priority.CRITICAL.name
    assert result["escalate"] is True
    assert "sms" in result["channels"]


def test_occupancy_boosts_score(prioritizer):
    low = Alert("a2", AlertType.FIRE_WARNING, "warn", "warning", occupancy_count=0)
    high = Alert("a3", AlertType.FIRE_WARNING, "warn", "warning", occupancy_count=10)
    assert prioritizer.score(high) > prioritizer.score(low)


def test_night_boost(prioritizer, monkeypatch):
    import time
    # Simulate 02:00 local time by mocking localtime
    class T:
        tm_hour = 2
    monkeypatch.setattr(time, "localtime", lambda ts: T())
    # Use a non-capped alert type so night boost produces a strict difference
    night = Alert("a4", AlertType.SENSOR_OFFLINE, "offline", "warning")
    day = Alert("a5", AlertType.SENSOR_OFFLINE, "offline", "warning")
    # Reset history completely so no repeat decay applies
    prioritizer._history = {}
    # Score day first while mocked to day hour (12) so base is 0.45
    class D:
        tm_hour = 12
    monkeypatch.setattr(time, "localtime", lambda ts: D())
    day_score = prioritizer.score(day)
    # Then mock night and score night
    monkeypatch.setattr(time, "localtime", lambda ts: T())
    prioritizer._history = {}
    night_score = prioritizer.score(night)
    assert night_score > day_score, f"day={day_score} night={night_score}"


def test_acknowledged_lowers_priority(prioritizer):
    unack = Alert("a6", AlertType.SENSOR_OFFLINE, "offline", "warning")
    ack = Alert("a7", AlertType.SENSOR_OFFLINE, "offline", "warning", acknowledged=True)
    assert prioritizer.score(ack) < prioritizer.score(unack)


def test_rank_sorts_descending(prioritizer):
    alerts = [
        Alert("a8", AlertType.INFO, "info", "info"),
        Alert("a9", AlertType.FIRE_CONFIRMED, "fire", "critical"),
    ]
    # process first so score() history side effects are deterministic
    for a in alerts:
        prioritizer.process(a)
    ranked = prioritizer.rank(alerts)
    assert ranked[0][0].id == "a9"
    assert ranked[0][2] == Priority.CRITICAL


def test_to_dict(prioritizer):
    d = prioritizer.to_dict()
    assert d["feature_id"] == "V7-001"
    assert d["healthy"] is True
