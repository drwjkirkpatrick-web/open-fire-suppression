"""Fault isolation wrapper for all fire detection modules.

# RES-002 — Module Fault Isolation

Ensures that any module failure does not crash or pause the entire
fire detection system. Each module runs in its own exception boundary
with automatic degradation and recovery.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ModuleHealth:
    """Health status for a single module."""
    name: str
    fails: int = 0
    last_ok: float = field(default_factory=time.time)
    degraded: bool = False
    last_error: str | None = None
    total_calls: int = 0
    avg_latency_ms: float = 0.0


class FaultIsolatedExecutor:
    """Wraps any callable so failures are isolated.

    Usage:
        executor = FaultIsolatedExecutor()

        # Wrap a function
        @executor.wrap("mq2_sensor")
        def read_mq2():
            return sensor.read()

        # Wrap an async function
        @executor.wrap_async("lidar_detector")
        async def scan_lidar():
            return await lidar.scan()

        # Check health
        health = executor.get_health()
    """

    def __init__(self, max_failures: int = 3, recovery_interval_sec: float = 300.0) -> None:
        self._max_failures = max_failures
        self._recovery_interval = recovery_interval_sec
        self._modules: dict[str, ModuleHealth] = {}
        self._callbacks: dict[str, list[Callable]] = {}  # On degradation

    def _get_or_create(self, name: str) -> ModuleHealth:
        if name not in self._modules:
            self._modules[name] = ModuleHealth(name=name)
        return self._modules[name]

    def wrap(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T | None]]:
        """Decorator for synchronous functions."""
        def decorator(func: Callable[..., T]) -> Callable[..., T | None]:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> T | None:
                health = self._get_or_create(name)

                # Check if degraded and recovery time passed
                if health.degraded:
                    if time.time() - health.last_ok > self._recovery_interval:
                        logger.info("Module %s attempting recovery", name)
                        health.degraded = False
                        health.fails = 0
                    else:
                        logger.warning("Module %s still degraded, skipping", name)
                        return None

                start = time.time()
                health.total_calls += 1

                try:
                    result = func(*args, **kwargs)
                    health.fails = 0
                    health.last_ok = time.time()
                    health.last_error = None

                    # Update rolling average latency
                    latency_ms = (time.time() - start) * 1000
                    health.avg_latency_ms = (
                        health.avg_latency_ms * 0.9 + latency_ms * 0.1
                    )

                    return result

                except Exception as exc:
                    health.fails += 1
                    health.last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
                    latency_ms = (time.time() - start) * 1000
                    health.avg_latency_ms = (
                        health.avg_latency_ms * 0.9 + latency_ms * 0.1
                    )

                    logger.error(
                        "Module %s failed (%d/%d): %s",
                        name, health.fails, self._max_failures, exc,
                    )

                    if health.fails >= self._max_failures:
                        health.degraded = True
                        logger.critical(
                            "Module %s DEGRADED after %d consecutive failures",
                            name, self._max_failures,
                        )
                        # Notify callbacks
                        for cb in self._callbacks.get(name, []):
                            try:
                                cb(name, health)
                            except Exception:
                                pass

                    return None

            return wrapper
        return decorator

    def wrap_async(
        self, name: str
    ) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T | None]]]:
        """Decorator for async functions."""
        def decorator(
            func: Callable[..., Coroutine[Any, Any, T]]
        ) -> Callable[..., Coroutine[Any, Any, T | None]]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T | None:
                health = self._get_or_create(name)

                # Check if degraded and recovery time passed
                if health.degraded:
                    if time.time() - health.last_ok > self._recovery_interval:
                        logger.info("Module %s attempting recovery", name)
                        health.degraded = False
                        health.fails = 0
                    else:
                        logger.warning("Module %s still degraded, skipping", name)
                        return None

                start = time.time()
                health.total_calls += 1

                try:
                    result = await func(*args, **kwargs)
                    health.fails = 0
                    health.last_ok = time.time()
                    health.last_error = None

                    latency_ms = (time.time() - start) * 1000
                    health.avg_latency_ms = (
                        health.avg_latency_ms * 0.9 + latency_ms * 0.1
                    )

                    return result

                except Exception as exc:
                    health.fails += 1
                    health.last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
                    latency_ms = (time.time() - start) * 1000
                    health.avg_latency_ms = (
                        health.avg_latency_ms * 0.9 + latency_ms * 0.1
                    )

                    logger.error(
                        "Module %s failed (%d/%d): %s",
                        name, health.fails, self._max_failures, exc,
                    )

                    if health.fails >= self._max_failures:
                        health.degraded = True
                        logger.critical(
                            "Module %s DEGRADED after %d consecutive failures",
                            name, self._max_failures,
                        )
                        for cb in self._callbacks.get(name, []):
                            try:
                                if asyncio.iscoroutinefunction(cb):
                                    await cb(name, health)
                                else:
                                    cb(name, health)
                            except Exception:
                                pass

                    return None

            return wrapper
        return decorator

    def on_degraded(self, name: str, callback: Callable) -> None:
        """Register a callback for when a module is degraded."""
        if name not in self._callbacks:
            self._callbacks[name] = []
        self._callbacks[name].append(callback)

    def get_health(self, name: str | None = None) -> dict[str, dict] | dict:
        """Get health status of all or one module."""
        if name:
            h = self._get_or_create(name)
            return {
                "name": h.name,
                "fails": h.fails,
                "degraded": h.degraded,
                "last_ok": h.last_ok,
                "last_error": h.last_error,
                "total_calls": h.total_calls,
                "avg_latency_ms": round(h.avg_latency_ms, 2),
            }
        return {
            name: {
                "name": h.name,
                "fails": h.fails,
                "degraded": h.degraded,
                "last_ok": h.last_ok,
                "last_error": h.last_error,
                "total_calls": h.total_calls,
                "avg_latency_ms": round(h.avg_latency_ms, 2),
            }
            for name, h in self._modules.items()
        }

    def reset_module(self, name: str) -> bool:
        """Manually reset a degraded module."""
        if name in self._modules:
            self._modules[name].degraded = False
            self._modules[name].fails = 0
            self._modules[name].last_error = None
            logger.info("Module %s manually reset", name)
            return True
        return False

    def get_degraded_modules(self) -> list[str]:
        """Return list of currently degraded module names."""
        return [name for name, h in self._modules.items() if h.degraded]

    def to_dict(self) -> dict:
        """Export full health status."""
        return {
            "modules": self.get_health(),
            "degraded_count": len(self.get_degraded_modules()),
            "total_modules": len(self._modules),
        }


# ── Global executor instance ──

_default_executor: FaultIsolatedExecutor | None = None


def get_executor() -> FaultIsolatedExecutor:
    """Get or create the global fault-isolated executor."""
    global _default_executor
    if _default_executor is None:
        _default_executor = FaultIsolatedExecutor()
    return _default_executor


def isolated(name: str):
    """Convenience decorator using global executor.

    Usage:
        @isolated("mq2_sensor")
        def read_smoke():
            return sensor.read()
    """
    return get_executor().wrap(name)


def isolated_async(name: str):
    """Convenience async decorator using global executor.

    Usage:
        @isolated_async("lidar_detector")
        async def scan_lidar():
            return await lidar.scan()
    """
    return get_executor().wrap_async(name)
