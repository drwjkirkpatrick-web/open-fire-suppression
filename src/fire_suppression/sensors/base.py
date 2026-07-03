"""Base sensor abstraction for open-fire-suppression.

Provides a uniform interface for all hardware sensors with mock support,
health tracking, and async polling.

# S012 — Sensor Health Monitoring
"""
from __future__ import annotations

import abc
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SensorStatus(Enum):
    """Health status of a sensor over a rolling window."""
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class SensorReading:
    """A single sensor reading with metadata."""
    sensor_name: str
    timestamp: float
    values: dict[str, float | int | str | None]
    raw: Any = None
    unit: str = ""


@dataclass
class SensorHealth:
    """Rolling health statistics for a sensor."""
    total_reads: int = 0
    successful_reads: int = 0
    failed_reads: int = 0
    last_success_time: float = 0.0
    last_error: str = ""
    status: SensorStatus = SensorStatus.UNKNOWN

    @property
    def success_rate(self) -> float:
        if self.total_reads == 0:
            return 0.0
        return self.successful_reads / self.total_reads


class BaseSensor(abc.ABC):
    """Abstract base for all fire-suppression sensors.

    Subclasses must implement ``read()`` and ``close()``.
    The ``mock`` flag allows running the full system on non-Pi hardware.
    """

    def __init__(self, name: str, *, mock: bool = False, health_window: int = 10) -> None:
        self.name = name
        self.mock = mock
        self.health = SensorHealth()
        self._health_window = health_window
        self._recent_results: list[bool] = []
        self._closed = False

    # ── Abstract interface ──

    @abc.abstractmethod
    async def read(self) -> SensorReading:
        """Return a single reading. Must not block the event loop."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Release hardware resources. Safe to call multiple times."""
        ...

    # ── Health tracking ──

    async def read_with_health(self) -> SensorReading | None:
        """Wrap ``read()`` with success/failure tracking.

        On failure returns ``None`` and records the error.
        """
        try:
            reading = await self.read()
            self._record_success()
            return reading
        except Exception as exc:
            self._record_failure(str(exc))
            logger.warning("Sensor %s read failed: %s", self.name, exc)
            return None

    def _record_success(self) -> None:
        self.health.total_reads += 1
        self.health.successful_reads += 1
        self.health.last_success_time = time.monotonic()
        self._recent_results.append(True)
        self._trim_window()
        self._update_status()

    def _record_failure(self, msg: str) -> None:
        self.health.total_reads += 1
        self.health.failed_reads += 1
        self.health.last_error = msg
        self._recent_results.append(False)
        self._trim_window()
        self._update_status()

    def _trim_window(self) -> None:
        while len(self._recent_results) > self._health_window:
            old = self._recent_results.pop(0)
            if old:
                self.health.successful_reads -= 1
            else:
                self.health.failed_reads -= 1

    def _update_status(self) -> None:
        if self.health.total_reads == 0:
            self.health.status = SensorStatus.UNKNOWN
            return
        rate = self.health.success_rate
        if rate >= 0.8:
            self.health.status = SensorStatus.OK
        elif rate >= 0.5:
            self.health.status = SensorStatus.WARN
        else:
            self.health.status = SensorStatus.ERROR

    # ── Helpers ──

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} mock={self.mock} status={self.health.status.value}>"


class MockSensor(BaseSensor):
    """A sensor that returns pre-configured synthetic values for testing.

    # M001 — Mock Hardware Layer
    # M002 — Simulated Fire Scenarios
    """

    def __init__(
        self,
        name: str,
        *,
        mock: bool = True,
        initial_values: dict[str, float] | None = None,
        scenario: str | None = None,
    ) -> None:
        super().__init__(name, mock=mock)
        self._values = dict(initial_values or {})
        self._scenario = scenario
        self._scenario_step = 0

    async def read(self) -> SensorReading:
        if self._scenario:
            values = self._apply_scenario()
        else:
            values = dict(self._values)
        return SensorReading(
            sensor_name=self.name,
            timestamp=time.time(),
            values=values,
            raw=values,
        )

    async def close(self) -> None:
        self._closed = True

    def set_values(self, values: dict[str, float]) -> None:
        """Update the synthetic values returned by ``read()``."""
        self._values.update(values)

    def set_scenario(self, scenario: str) -> None:
        """Select a built-in fire scenario: ``smoldering``, ``flashover``, ``false_alarm``."""
        self._scenario = scenario
        self._scenario_step = 0

    def _apply_scenario(self) -> dict[str, float]:
        """Generate values that follow a fire profile over time steps."""
        step = self._scenario_step
        self._scenario_step += 1

        if self._scenario == "smoldering":
            # Slow temperature rise, low smoke, high CO/VOC
            return {
                "temperature_c": 25.0 + min(step * 0.5, 35.0),
                "humidity_percent": 50.0 - min(step * 0.3, 20.0),
                "smoke_ppm": 50.0 + min(step * 5.0, 400.0),
                "tvoc_ppb": 200.0 + min(step * 10.0, 800.0),
                "co2_ppm": 400.0 + min(step * 2.0, 600.0),
            }

        if self._scenario == "flashover":
            # Rapid spike in temperature and smoke
            return {
                "temperature_c": 25.0 + min(step * 8.0, 300.0),
                "humidity_percent": 50.0 - min(step * 1.0, 30.0),
                "smoke_ppm": 50.0 + min(step * 50.0, 2000.0),
                "tvoc_ppb": 200.0 + min(step * 100.0, 3000.0),
                "co2_ppm": 400.0 + min(step * 20.0, 3000.0),
            }

        if self._scenario == "false_alarm":
            # High temp but no smoke/gas (e.g., cooking, sunny day)
            return {
                "temperature_c": 25.0 + min(step * 1.0, 65.0),
                "humidity_percent": 50.0,
                "smoke_ppm": 10.0,
                "tvoc_ppb": 50.0,
                "co2_ppm": 400.0,
            }

        return dict(self._values)
