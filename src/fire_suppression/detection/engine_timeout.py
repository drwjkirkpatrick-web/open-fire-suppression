"""Detection engine timeout wrapper with fallback to simple threshold mode.

# BOT-002 — Detection Engine Timeout

Wraps any detection computation in ``asyncio.wait_for`` with a configurable
timeout.  When the computation exceeds the limit the module falls back to a
simple threshold mode, tracks the frequency of timeouts per detector, and logs
bilingual (English / Swahili) safety messages.

Usage::

    from fire_suppression.detection.engine_timeout import (
        DetectionEngineTimeout,
        with_timeout,
    )

    # As a decorator
    @with_timeout(seconds=5.0, fallback=my_fallback)
    async def detect_fire(sensor_readings):
        ...

    # As a class wrapper
    wrapper = DetectionEngineTimeout(default_timeout=5.0, mock=True)
    result = await wrapper.run("thermal_detector", detect_fire, readings)
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

# ── Bilingual messages ──────────────────────────────────────────────────────
_TIMEOUT_MSGS = {
    "timeout_occurred": {
        "en": "TIMEOUT: Detector '{detector}' exceeded {seconds}s — falling back to threshold mode.",
        "sw": "MUDA UMEPITA: Kipambazuko '{detector}' kimezidi {seconds}s — kurudi kwa hali ya kizingo.",
    },
    "timeout_cleared": {
        "en": "Detector '{detector}' has recovered after {count} timeout(s).",
        "sw": "Kipambazuko '{detector}' kimerudi baada ya timeout {count}.",
    },
    "fallback_triggered": {
        "en": "FALLBACK: Simple threshold mode activated for '{detector}'.",
        "sw": "KURUDI: Hali ya kizingo rahisi imewashwa kwa '{detector}'.",
    },
    "health_warning": {
        "en": "High timeout rate detected for '{detector}' ({rate:.1%}).",
        "sw": "Kiwango cha juu cha timeout kimewachunguzwa kwa '{detector}' ({rate:.1%}).",
    },
}


def _timeout_msg(key: str, lang: str = "en", **kwargs: Any) -> str:
    m = _TIMEOUT_MSGS.get(key, {})
    return m.get(lang, m.get("en", key)).format(**kwargs)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class TimeoutStats:
    """Per-detector timeout statistics."""
    total_calls: int = 0
    timeouts: int = 0
    last_timeout: float = 0.0
    consecutive_timeouts: int = 0
    max_consecutive: int = 0

    @property
    def timeout_rate(self) -> float:
        return self.timeouts / self.total_calls if self.total_calls > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "timeouts": self.timeouts,
            "timeout_rate": round(self.timeout_rate, 4),
            "last_timeout": self.last_timeout,
            "consecutive_timeouts": self.consecutive_timeouts,
            "max_consecutive": self.max_consecutive,
        }


@dataclass
class TimeoutResult:
    """Result of a wrapped detection call."""
    result: Any = None
    timed_out: bool = False
    detector_id: str = ""
    elapsed_ms: float = 0.0
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result if isinstance(self.result, (dict, list, str, int, float, bool, type(None))) else repr(self.result),
            "timed_out": self.timed_out,
            "detector_id": self.detector_id,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "fallback_used": self.fallback_used,
        }


# ── Decorator ───────────────────────────────────────────────────────────────

T = TypeVar("T")


def with_timeout(
    seconds: float = 5.0,
    fallback: Optional[Callable[..., Any]] = None,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """Decorator that wraps an async detection function with a timeout.

    Args:
        seconds: Maximum allowed execution time (default 5.0).
        fallback: Optional callable invoked when the wrapped function times out.
            Must accept the same positional / keyword arguments as the wrapped
            function.  If *None* a :class:`TimeoutError` is raised.

    Returns:
        A coroutine that either returns the wrapped function's result or the
        fallback's result.

    Example::

        @with_timeout(seconds=3.0, fallback=simple_threshold)
        async def detect_fire(readings: dict) -> DetectionResult:
            ...
    """
    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]]
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            t0 = time.time()
            try:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
                return result
            except asyncio.TimeoutError:
                elapsed = time.time() - t0
                detector_id = func.__name__
                logger.warning(
                    _timeout_msg("timeout_occurred", detector=detector_id, seconds=seconds)
                )
                logger.warning(
                    _timeout_msg("timeout_occurred", lang="sw", detector=detector_id, seconds=seconds)
                )
                if fallback is not None:
                    logger.info(
                        _timeout_msg("fallback_triggered", detector=detector_id)
                    )
                    logger.info(
                        _timeout_msg("fallback_triggered", lang="sw", detector=detector_id)
                    )
                    if inspect.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    return fallback(*args, **kwargs)
                raise
        return wrapper
    return decorator


# ── Main wrapper class ────────────────────────────────────────────────────────

class DetectionEngineTimeout:
    """Timeout-aware wrapper for detection computations.

    Wraps arbitrary detection coroutines in ``asyncio.wait_for`` and falls
    back to a simple threshold evaluator when a call exceeds its deadline.
    Timeout frequency is tracked per detector for health monitoring.

    Args:
        default_timeout: Default timeout in seconds (default 5.0).
        mock: When ``True``, disables real I/O and uses synthetic timing.
    """

    FEATURE_ID = "BOT-002"
    FEATURE_NAME = "Detection Engine Timeout"

    def __init__(
        self,
        default_timeout: float = 5.0,
        *,
        mock: bool = False,
    ) -> None:
        self.default_timeout = max(0.1, float(default_timeout))
        self.mock = mock
        self._stats: Dict[str, TimeoutStats] = defaultdict(TimeoutStats)
        self._thresholds: Dict[str, float] = {}

        logger.info(
            "DetectionEngineTimeout initialised — timeout=%.1fs mock=%s",
            self.default_timeout,
            self.mock,
        )

    # ── Threshold helpers ────────────────────────────────────────────────────

    def set_threshold(self, detector_id: str, threshold: float) -> None:
        """Register a simple numeric threshold for a detector.

        Used by the built-in fallback when the primary computation times out.
        """
        self._thresholds[detector_id] = threshold

    def get_threshold(self, detector_id: str) -> float:
        """Return the registered threshold for *detector_id* (or 0.0)."""
        return self._thresholds.get(detector_id, 0.0)

    def _simple_threshold_fallback(
        self,
        detector_id: str,
        sensor_value: float,
        **_kw: Any,
    ) -> Dict[str, Any]:
        """Built-in fallback: compare *sensor_value* against threshold.

        Returns a dict compatible with DetectionResult conventions.
        """
        threshold = self.get_threshold(detector_id)
        triggered = sensor_value >= threshold if threshold > 0 else False
        return {
            "state": "alert" if triggered else "clear",
            "confidence": 0.5 if triggered else 0.0,
            "triggered": triggered,
            "sensor_value": sensor_value,
            "threshold": threshold,
            "reason": "timeout_fallback_threshold",
        }

    # ── Core runner ──────────────────────────────────────────────────────────

    async def run(
        self,
        detector_id: str,
        coro: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        fallback: Optional[Callable[..., Any]] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> TimeoutResult:
        """Execute *coro* under timeout, falling back on deadline exceeded.

        Args:
            detector_id: Logical name of the detector (used for stats).
            coro: Async callable to execute.
            *args: Positional arguments forwarded to *coro*.
            fallback: Optional sync/async fallback callable.  Defaults to the
                built-in threshold fallback when a threshold is registered.
            timeout: Override the instance default timeout (seconds).
            **kwargs: Keyword arguments forwarded to *coro*.

        Returns:
            :class:`TimeoutResult` containing the actual result and metadata.
        """
        stats = self._stats[detector_id]
        stats.total_calls += 1

        effective_timeout = timeout if timeout is not None else self.default_timeout
        if self.mock:
            effective_timeout = 0.01  # Accelerated for unit tests

        t0 = time.time()
        timed_out = False
        fallback_used = False
        result: Any = None

        try:
            if inspect.iscoroutinefunction(coro):
                result = await asyncio.wait_for(coro(*args, **kwargs), timeout=effective_timeout)
            else:
                # Run synchronous callable in thread pool so wait_for works
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, functools.partial(coro, *args, **kwargs)),
                    timeout=effective_timeout,
                )
            stats.consecutive_timeouts = 0
        except asyncio.TimeoutError:
            timed_out = True
            fallback_used = True
            stats.timeouts += 1
            stats.last_timeout = time.time()
            stats.consecutive_timeouts += 1
            if stats.consecutive_timeouts > stats.max_consecutive:
                stats.max_consecutive = stats.consecutive_timeouts

            logger.warning(
                _timeout_msg("timeout_occurred", detector=detector_id, seconds=effective_timeout)
            )
            logger.warning(
                _timeout_msg("timeout_occurred", lang="sw", detector=detector_id, seconds=effective_timeout)
            )

            # Resolve fallback
            fb = fallback
            if fb is None and detector_id in self._thresholds:
                # Use built-in threshold fallback with the sensor value
                sensor_value = kwargs.get("sensor_value", args[0] if args else 0.0)
                fb = functools.partial(self._simple_threshold_fallback, detector_id, sensor_value)

            if fb is not None:
                logger.info(
                    _timeout_msg("fallback_triggered", detector=detector_id)
                )
                logger.info(
                    _timeout_msg("fallback_triggered", lang="sw", detector=detector_id)
                )
                # Built-in partial already has args bound; custom fallback needs original args
                if isinstance(fb, functools.partial):
                    result = fb()
                elif inspect.iscoroutinefunction(fb):
                    result = await fb(*args, **kwargs)
                elif callable(fb):
                    result = fb(*args, **kwargs)
                else:
                    result = fb
            else:
                raise

        elapsed = (time.time() - t0) * 1000.0
        return TimeoutResult(
            result=result,
            timed_out=timed_out,
            detector_id=detector_id,
            elapsed_ms=elapsed,
            fallback_used=fallback_used,
        )

    # ── Statistics ───────────────────────────────────────────────────────────

    def get_stats(self, detector_id: Optional[str] = None) -> Dict[str, Any]:
        """Return timeout statistics.

        If *detector_id* is given, returns that detector's stats only;
        otherwise returns a mapping of all detectors.
        """
        if detector_id is not None:
            return self._stats[detector_id].to_dict()
        return {k: v.to_dict() for k, v in self._stats.items()}

    def reset_stats(self, detector_id: Optional[str] = None) -> None:
        """Reset timeout statistics for *detector_id* or all detectors."""
        if detector_id is not None:
            self._stats[detector_id] = TimeoutStats()
        else:
            self._stats.clear()

    # ── Health & introspection ───────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Return a health snapshot of the timeout wrapper."""
        total_calls = sum(s.total_calls for s in self._stats.values())
        total_timeouts = sum(s.timeouts for s in self._stats.values())
        overall_rate = total_timeouts / total_calls if total_calls > 0 else 0.0

        unhealthy_detectors = [
            {
                "detector_id": did,
                "timeout_rate": round(s.timeout_rate, 4),
                "consecutive_timeouts": s.consecutive_timeouts,
            }
            for did, s in self._stats.items()
            if s.timeout_rate > 0.2 or s.consecutive_timeouts >= 3
        ]

        return {
            "healthy": overall_rate < 0.2 and not any(
                s.consecutive_timeouts >= 3 for s in self._stats.values()
            ),
            "overall_timeout_rate": round(overall_rate, 4),
            "total_calls": total_calls,
            "total_timeouts": total_timeouts,
            "detectors_tracked": len(self._stats),
            "unhealthy_detectors": unhealthy_detectors,
            "mock": self.mock,
        }

    def get_feature_overview(self) -> Dict[str, Any]:
        return {
            "feature_id": self.FEATURE_ID,
            "feature_name": self.FEATURE_NAME,
            "mock": self.mock,
            "supports": [
                "async_timeout",
                "sync_timeout",
                "threshold_fallback",
                "per_detector_stats",
                "bilingual_logging",
            ],
            "default_timeout_seconds": self.default_timeout,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.health_check(),
            "feature_id": self.FEATURE_ID,
            "feature_name": self.FEATURE_NAME,
            "stats": self.get_stats(),
            "thresholds": dict(self._thresholds),
        }
