"""Tests for V7-005 Cloud Situational Awareness Feed."""
import pytest

from fire_suppression.config import Config
from fire_suppression.telemetry.cloud_sitfeed import CloudSituationalAwarenessFeed


@pytest.fixture
def feed(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["cloud_sitfeed"] = {"update_interval_seconds": 0.01, "max_clients": 2}
    return CloudSituationalAwarenessFeed(cfg)


def test_sanitize_removes_sensitive(feed):
    full = {
        "detection": {"state": "alert", "confidence": 0.88},
        "safety": {"state": "armed"},
        "power": {"source": "battery", "battery_percent": 42.0},
        "sensors": {
            "mq2": {"smoke_ppm": 120.0, "raw_adc": 4095, "calibration": "secret"},
        },
    }
    sanitized = feed.sanitize(full)
    assert sanitized["fire_state"] == "alert"
    assert "raw_adc" not in sanitized["sensors"]["mq2"]
    assert "calibration" not in sanitized["sensors"]["mq2"]


def test_ingest_and_to_dict(feed):
    feed.ingest({"detection": {"state": "clear", "confidence": 0.0}})
    d = feed.to_dict()
    assert d["feature_id"] == "V7-005"
    assert d["clients"] == 0
    assert d["last_update"] is not None


def test_max_clients_mock(feed, monkeypatch):
    class FakeWS:
        closed = False
        async def close(self, code=None, reason=None):
            self.closed = True
    ws = FakeWS()
    # Simulate two clients already connected
    feed._clients = [FakeWS(), FakeWS()]
    import asyncio
    asyncio.run(feed.connect(ws))
    assert ws.closed


def test_clients_count(feed):
    assert feed.to_dict()["clients"] == 0
