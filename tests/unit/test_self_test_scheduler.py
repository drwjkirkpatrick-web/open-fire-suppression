"""Tests for V7-003 Self-Test Scheduler."""
import pytest

from fire_suppression.config import Config
from fire_suppression.diagnostics.self_test_scheduler import SelfTestScheduler, TestResult


@pytest.fixture
def scheduler(monkeypatch):
    Config._instance = None
    cfg = Config()
    cfg._data["self_test_scheduler"] = {"enabled": True}
    return SelfTestScheduler(cfg)


def test_default_tests_present(scheduler):
    assert "sensor_comm" in scheduler._tests
    assert "relay_dry_run" in scheduler._tests


def test_run_test_passes(scheduler):
    result = scheduler.run_test("sensor_comm")
    assert result["result"] == "pass"
    assert scheduler._tests["sensor_comm"].next_due is not None


def test_run_test_mock_result(scheduler):
    result = scheduler.run_test("sensor_comm", TestResult.FAIL)
    assert result["result"] == "fail"


def test_disabled_scheduler_skips(scheduler):
    scheduler.enabled = False
    result = scheduler.run_test("sensor_comm")
    assert result["result"] == "skipped"


def test_due_tests_empty_initially(scheduler):
    assert all(t.next_due is None for t in scheduler._tests.values())
    assert len(scheduler.due_tests()) == len(scheduler._tests)


def test_generate_report(scheduler):
    scheduler.run_all_due()
    report = scheduler.generate_report()
    assert report["feature_id"] == "V7-003"
    assert report["summary"]["total"] == len(scheduler._tests)
    assert report["summary"]["pass"] >= 1


def test_to_dict(scheduler):
    assert scheduler.to_dict()["feature_id"] == "V7-003"
    assert scheduler.to_dict()["enabled"] is True
