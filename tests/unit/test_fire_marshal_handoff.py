"""Tests for V7-004 Fire Marshal Digital Handoff."""
import pytest

from fire_suppression.config import Config
from fire_suppression.telemetry.fire_marshal_handoff import FireMarshalHandoff


@pytest.fixture
def handoff(monkeypatch):
    Config._instance = None
    return FireMarshalHandoff(Config())


def test_create_brief(handoff):
    incident = {
        "incident_id": "INC-2026-001",
        "incident_type": "fire",
        "location": "Main Campus",
        "zone": "Server Room",
        "fire_state": "confirmed",
        "confidence": 0.97,
        "triggered_sensors": ["mq2", "mlx90614"],
        "actions_taken": ["relay_0_on", "elevator_recall"],
        "operator_name": "Safety Officer",
    }
    brief = handoff.create_brief(incident)
    assert brief["brief_id"] == "INC-2026-001"
    assert brief["manifest_hash"]
    assert brief["qr_payload"].startswith("firehandoff:")
    assert brief["share_url"]


def test_package_for_export(handoff):
    brief = handoff.create_brief({"incident_type": "fire", "location": "Lab"})
    pkg = handoff.package_for_export(brief)
    assert pkg["package_id"].startswith("PKG-")
    assert "json" in pkg["formats"]
    assert pkg["verification"]["algorithm"] == "SHA-256"


def test_to_dict(handoff):
    assert handoff.to_dict()["feature_id"] == "V7-004"
    assert handoff.to_dict()["healthy"] is True
