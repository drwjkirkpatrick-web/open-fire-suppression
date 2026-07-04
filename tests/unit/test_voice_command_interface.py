"""Tests for V7-006 Voice Command Interface."""
import pytest

from fire_suppression.alerts.voice_command_interface import VoiceCommand, VoiceCommandInterface
from fire_suppression.config import Config


@pytest.fixture
def vci(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["voice_command"] = {"confidence_threshold": 0.6}
    return VoiceCommandInterface(cfg)


def test_has_wake_word(vci):
    assert vci.has_wake_word("Hey firebot, status please") is True
    assert vci.has_wake_word("what is the status") is False


def test_parse_status(vci):
    result = vci.parse("firebot status")
    assert result.command == VoiceCommand.STATUS
    assert result.requires_auth is False


def test_parse_evacuate_requires_auth(vci):
    result = vci.parse("firebot evacuate now")
    assert result.command == VoiceCommand.EVACUATE
    assert result.requires_auth is True


def test_parse_swahili(vci):
    result = vci.process("mfumo hali", lang="sw")
    assert result["recognized"] is True
    assert result["command"] == "status"
    assert result["lang"] == "sw"


def test_low_confidence_rejected(vci):
    result = vci.process("firebot gibberish")
    assert result["recognized"] is False
    assert result["reason"] == "low_confidence"


def test_no_wake_word(vci):
    result = vci.process("status now")
    assert result["recognized"] is False
    assert result["reason"] == "no_wake_word"


def test_to_dict(vci):
    assert vci.to_dict()["feature_id"] == "V7-006"
    assert vci.to_dict()["healthy"] is True
