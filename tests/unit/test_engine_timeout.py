"""Tests for Detection Engine Timeout (BOT-002).

# BOT-002 — Detection Engine Timeout Tests

Covers decorator usage, class-based runner, fallback behaviour, timeout
statistics, bilingual messages, health check, and serialisation.
"""
import asyncio
import time
from typing import Any

import pytest

from fire_suppression.detection.engine_timeout import (
    DetectionEngineTimeout,
    TimeoutResult,
    TimeoutStats,
    _timeout_msg,
    with_timeout,
)


# ── Helper coroutines ────────────────────────────────────────────────────────

async def _fast_detection(value: float = 0.5) -> str:
    return f"detected_{value}"


async def _slow_detection(delay: float = 10.0, **_kw: Any) -> str:
    await asyncio.sleep(delay)
    return "detected"


def _sync_fallback(value: float = 0.0, **_kw: Any) -> dict[str, Any]:
    return {"state": "fallback", "value": value}


async def _async_fallback(value: float = 0.0, **_kw: Any) -> dict[str, Any]:
    return {"state": "async_fallback", "value": value}


# ── Message helpers ──────────────────────────────────────────────────────────

class TestBilingualMessages:
    """Bilingual EN/SW message generation."""

    def test_english_default(self) -> None:
        msg = _timeout_msg("timeout_occurred", detector="thermal", seconds=5.0)
        assert "TIMEOUT" in msg
        assert "thermal" in msg

    def test_swahili(self) -> None:
        msg = _timeout_msg("timeout_occurred", lang="sw", detector="thermal", seconds=5.0)
        assert "MUDA UMEPITA" in msg
        assert "thermal" in msg


class TestTimeoutStats:
    """Per-detector statistics dataclass."""

    def test_rate_zero_when_no_calls(self) -> None:
        s = TimeoutStats()
        assert s.timeout_rate == 0.0

    def test_rate_computed_correctly(self) -> None:
        s = TimeoutStats(total_calls=10, timeouts=3)
        assert s.timeout_rate == 0.3

    def test_to_dict(self) -> None:
        s = TimeoutStats(total_calls=5, timeouts=1, last_timeout=1_700_000_000.0)
        d = s.to_dict()
        assert d["total_calls"] == 5
        assert d["timeouts"] == 1
        assert d["timeout_rate"] == 0.2
        assert d["last_timeout"] == 1_700_000_000.0


class TestDecorator:
    """@with_timeout decorator behaviour."""

    def test_decorator_returns_result_when_fast(self) -> None:
        @with_timeout(seconds=1.0)
        async def fast() -> str:
            return "ok"

        result = asyncio.run(fast())
        assert result == "ok"

    def test_decorator_raises_on_timeout_without_fallback(self) -> None:
        @with_timeout(seconds=0.1)
        async def slow() -> str:
            await asyncio.sleep(5.0)
            return "ok"

        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(slow())

    def test_decorator_uses_sync_fallback(self) -> None:
        @with_timeout(seconds=0.1, fallback=_sync_fallback)
        async def slow(value: float) -> dict[str, Any]:
            await asyncio.sleep(5.0)
            return {"state": "primary", "value": value}

        result = asyncio.run(slow(42.0))
        assert result["state"] == "fallback"
        assert result["value"] == 42.0

    def test_decorator_uses_async_fallback(self) -> None:
        @with_timeout(seconds=0.1, fallback=_async_fallback)
        async def slow(value: float) -> dict[str, Any]:
            await asyncio.sleep(5.0)
            return {"state": "primary", "value": value}

        result = asyncio.run(slow(7.0))
        assert result["state"] == "async_fallback"
        assert result["value"] == 7.0


class TestDetectionEngineTimeout:
    """DetectionEngineTimeout class tests."""

    def setup_method(self) -> None:
        self.engine = DetectionEngineTimeout(default_timeout=5.0, mock=True)

    def teardown_method(self) -> None:
        self.engine.reset_stats()

    # ── Constructor ──

    def test_init_sets_defaults(self) -> None:
        assert self.engine.default_timeout == 5.0
        assert self.engine.mock is True
        assert self.engine.FEATURE_ID == "BOT-002"

    # ── Threshold helpers ──

    def test_set_and_get_threshold(self) -> None:
        self.engine.set_threshold("thermal", 60.0)
        assert self.engine.get_threshold("thermal") == 60.0
        assert self.engine.get_threshold("missing") == 0.0

    def test_simple_threshold_fallback(self) -> None:
        self.engine.set_threshold("smoke", 300.0)
        result = self.engine._simple_threshold_fallback("smoke", sensor_value=350.0)
        assert result["state"] == "alert"
        assert result["triggered"] is True

        result2 = self.engine._simple_threshold_fallback("smoke", sensor_value=100.0)
        assert result2["state"] == "clear"
        assert result2["triggered"] is False

    # ── Runner (asyncio.run for non-async test methods) ──

    def test_run_fast_call_no_timeout(self) -> None:
        tr: TimeoutResult = asyncio.run(
            self.engine.run("thermal", _fast_detection, value=0.9)
        )
        assert tr.timed_out is False
        assert tr.fallback_used is False
        assert tr.result == "detected_0.9"
        assert tr.detector_id == "thermal"

    def test_run_timeout_with_builtin_fallback(self) -> None:
        self.engine.set_threshold("thermal", 50.0)
        tr: TimeoutResult = asyncio.run(
            self.engine.run("thermal", _slow_detection, delay=1.0, sensor_value=75.0)
        )
        assert tr.timed_out is True
        assert tr.fallback_used is True
        assert tr.result["state"] == "alert"
        assert tr.result["triggered"] is True

    def test_run_timeout_with_custom_fallback(self) -> None:
        tr: TimeoutResult = asyncio.run(
            self.engine.run(
                "thermal",
                _slow_detection,
                delay=1.0,
                fallback=_sync_fallback,
                value=99.0,
            )
        )
        assert tr.timed_out is True
        assert tr.fallback_used is True
        assert tr.result["state"] == "fallback"
        assert tr.result["value"] == 99.0

    def test_run_timeout_raises_when_no_fallback(self) -> None:
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(
                self.engine.run("thermal", _slow_detection, delay=1.0)
            )

    # ── Statistics ──

    def test_stats_tracked_per_detector(self) -> None:
        asyncio.run(self.engine.run("det_a", _fast_detection, value=1.0))
        asyncio.run(
            self.engine.run(
                "det_a", _slow_detection, delay=1.0, fallback=_sync_fallback, value=0.0
            )
        )
        stats = self.engine.get_stats("det_a")
        assert stats["total_calls"] == 2
        assert stats["timeouts"] == 1
        assert stats["timeout_rate"] == 0.5
        assert stats["consecutive_timeouts"] == 1

    def test_reset_stats_single_detector(self) -> None:
        asyncio.run(self.engine.run("det_a", _fast_detection, value=1.0))
        self.engine.reset_stats("det_a")
        assert self.engine.get_stats("det_a")["total_calls"] == 0

    def test_reset_stats_all_detectors(self) -> None:
        asyncio.run(self.engine.run("det_a", _fast_detection, value=1.0))
        asyncio.run(self.engine.run("det_b", _fast_detection, value=2.0))
        self.engine.reset_stats()
        assert self.engine.get_stats() == {}

    # ── Health check ──

    def test_health_check_healthy(self) -> None:
        asyncio.run(self.engine.run("det_a", _fast_detection, value=1.0))
        health = self.engine.health_check()
        assert health["healthy"] is True
        assert health["total_calls"] == 1
        assert health["total_timeouts"] == 0
        assert health["mock"] is True

    def test_health_check_unhealthy_high_rate(self) -> None:
        self.engine.set_threshold("slow", 1.0)
        for _ in range(5):
            asyncio.run(
                self.engine.run("slow", _slow_detection, delay=1.0, sensor_value=2.0)
            )
        health = self.engine.health_check()
        assert health["healthy"] is False
        assert len(health["unhealthy_detectors"]) == 1
        assert health["unhealthy_detectors"][0]["detector_id"] == "slow"

    # ── Feature overview / serialisation ──

    def test_get_feature_overview(self) -> None:
        overview = self.engine.get_feature_overview()
        assert overview["feature_id"] == "BOT-002"
        assert overview["feature_name"] == "Detection Engine Timeout"
        assert "async_timeout" in overview["supports"]

    def test_to_dict(self) -> None:
        asyncio.run(self.engine.run("det_a", _fast_detection, value=1.0))
        d = self.engine.to_dict()
        assert d["feature_id"] == "BOT-002"
        assert "stats" in d
        assert d["stats"]["det_a"]["total_calls"] == 1
        assert "thresholds" in d

    def test_timeout_result_to_dict(self) -> None:
        tr = TimeoutResult(
            result="ok",
            timed_out=False,
            detector_id="det_x",
            elapsed_ms=12.34,
            fallback_used=False,
        )
        d = tr.to_dict()
        assert d["result"] == "ok"
        assert d["timed_out"] is False
        assert d["detector_id"] == "det_x"
        assert d["elapsed_ms"] == 12.34
