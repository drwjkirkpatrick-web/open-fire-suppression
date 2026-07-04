"""Tests for V7-002 Multi-Building Command Console."""
import pytest

from fire_suppression.config import Config
from fire_suppression.web.multi_building_console import MultiBuildingConsole


@pytest.fixture
def console(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["multi_building_console"] = {"unit_timeout_seconds": 30.0}
    return MultiBuildingConsole(cfg)


def test_register_and_status(console):
    console.register_unit("unit-a", "Building A", "Floor 1")
    status = console.unit_status("unit-a")
    assert status["building"] == "Building A"
    assert status["online"] is True


def test_heartbeat_updates_status(console):
    console.register_unit("unit-b", "Building B")
    console.heartbeat({
        "unit_id": "unit-b",
        "fire_state": "alert",
        "battery_percent": 45.0,
        "sensors_online": 6,
    })
    status = console.unit_status("unit-b")
    assert status["fire_state"] == "alert"
    assert status["battery_percent"] == 45.0
    assert status["sensors_online"] == 6


def test_offline_after_timeout(console, monkeypatch):
    import time
    console.register_unit("unit-c", "Building C")
    console.units["unit-c"].last_seen = time.time() - 40
    monkeypatch.setattr(console, "timeout_seconds", 30.0)
    assert console.unit_status("unit-c")["online"] is False


def test_command_broadcast(console):
    console.register_unit("unit-d", "Building D")
    console.register_unit("unit-e", "Building D")
    result = console.issue_command(None, "test", {"mode": "silent"})
    assert result["count"] == 2
    assert len(console.pending_commands("unit-d")) == 1


def test_unknown_unit_command(console):
    result = console.issue_command("missing", "test")
    assert result["count"] == 1
    assert result["issued"][0]["error"] == "unknown unit"


def test_all_status_alert_count(console):
    console.register_unit("unit-f", "Building F")
    console.heartbeat({"unit_id": "unit-f", "fire_state": "alert"})
    all_status = console.all_status()
    assert all_status["alerting_count"] == 1
    assert all_status["online_count"] == 1


def test_to_dict(console):
    console.register_unit("unit-g", "Building G")
    assert console.to_dict()["feature_id"] == "V7-002"
