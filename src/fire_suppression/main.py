"""Main application loop for open-fire-suppression.

# I001 — System Startup Sequence
# I002 — Graceful Shutdown
# I003 — End-to-End Fire Detection
# I004 — End-to-End Power Loss
# I005 — Recovery After Restart
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time
from typing import Any

from fire_suppression.actuation.relay import ActuationState, RelayController
from fire_suppression.config import Config
from fire_suppression.detection.engine import FireDetectionEngine, FireState
from fire_suppression.power.manager import PowerManager
from fire_suppression.safety.interlock import SafetyInterlock, SafetyState
from fire_suppression.sensors import SensorManager
from fire_suppression.telemetry.logger import TelemetryLogger
from fire_suppression.web.dashboard import app, update_status_cache

logger = logging.getLogger(__name__)


class FireSuppressionSystem:
    """Main controller for the open-fire-suppression system.

    Orchestrates sensors, detection, safety, actuation, power, and telemetry
    in a single coordinated event loop.
    """

    def __init__(self) -> None:
        self.config = Config()
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Subsystems
        self.sensors = SensorManager(self.config)
        self.detection = FireDetectionEngine(self.config)
        self.safety = SafetyInterlock(self.config)
        self.actuation = RelayController(self.config)
        self.power = PowerManager(self.config)
        self.telemetry = TelemetryLogger(self.config)

        # Status cache for dashboard
        self._status_cache: dict[str, Any] = {
            "sensors": {},
            "detection": {"state": "clear", "confidence": 0.0},
            "safety": {"state": "disarmed", "can_actuate": False},
            "power": {"source": "ac", "battery_percent": 100.0},
            "actuation": {"state": "idle"},
            "events": [],
            "sensor_history": {},
            "timestamp": time.time(),
        }

    async def start(self) -> None:
        """Initialize all subsystems and start the main loop.

        # I001 — System Startup Sequence
        """
        logger.info("=" * 50)
        logger.info("open-fire-suppression v%s starting...", "0.7.0")
        logger.info("Mock mode: %s", self.config.mock_hardware)
        logger.info("=" * 50)

        # 1. Initialize sensors
        await self.sensors.start()
        logger.info("Sensors initialized: %d devices", len(self.sensors))

        # 2. Initialize telemetry
        self.telemetry.log_event("system_start", severity="info", message="System startup complete")

        # 3. Recovery: load last known state
        last_status = self.telemetry.get_latest_status()
        if last_status:
            logger.info("Recovered from previous session: %s", last_status.get("latest_safety", {}).get("state", "unknown"))
            self._status_cache["last_session"] = last_status

        # 4. Enable config hot-reload
        self.config.enable_hot_reload()

        # 5. Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, self._request_shutdown)

        # 6. Start the main loop
        self._running = True
        logger.info("Entering main monitoring loop")
        await self._main_loop()

    async def _main_loop(self) -> None:
        """Core monitoring loop."""
        cycle_count = 0
        last_power_check = 0.0
        last_db_rotate = 0.0

        while self._running and not self._shutdown_event.is_set():
            cycle_start = time.time()
            cycle_count += 1

            try:
                # ── 1. Poll safety inputs ──
                await self.safety.poll_safety_inputs()
                self.telemetry.log_safety_state(self.safety.state.value)

                # ── 2. Read all sensors ──
                readings = await self.sensors.poll_all()
                self._status_cache["sensors"] = {
                    name: {
                        "timestamp": r.timestamp if r else None,
                        "values": r.values if r else None,
                        "unit": r.unit if r else None,
                    }
                    for name, r in readings.items()
                }

                # Log sensor readings
                for name, reading in readings.items():
                    if reading:
                        health = self.sensors.get_sensor(name)
                        health_status = health.health.status.value if health else "unknown"
                        self.telemetry.log_sensor_reading(reading, health_status)

                # ── 3. Run fire detection ──
                detection_result = self.detection.detect(readings)
                self.telemetry.log_detection({
                    "timestamp": detection_result.timestamp,
                    "state": detection_result.state.value,
                    "confidence": detection_result.confidence,
                    "triggered_sensors": detection_result.triggered_sensors,
                    "thermal_hotspots": detection_result.thermal_hotspots,
                    "latency_ms": detection_result.latency_ms,
                    "reason": detection_result.reason,
                })

                self._status_cache["detection"] = {
                    "state": detection_result.state.value,
                    "confidence": detection_result.confidence,
                    "triggered_sensors": detection_result.triggered_sensors,
                    "latency_ms": detection_result.latency_ms,
                    "reason": detection_result.reason,
                }

                # ── 4. Handle detection state ──
                if detection_result.state == FireState.ALERT:
                    logger.critical("FIRE ALERT: confidence=%.2f reason=%s",
                                    detection_result.confidence, detection_result.reason)
                    self.telemetry.log_event("fire_alert", severity="critical",
                                             message=f"Fire detected: {detection_result.reason}",
                                             details={"confidence": detection_result.confidence,
                                                      "sensors": detection_result.triggered_sensors})

                    # Attempt suppression if safety allows
                    if self.safety.can_actuate and self.actuation.is_idle:
                        logger.warning("Initiating suppression sequence")
                        await self.actuation.activate(reason=detection_result.reason)

                elif detection_result.state == FireState.WARNING:
                    logger.warning("FIRE WARNING: %s", detection_result.reason)
                    self.telemetry.log_event("fire_warning", severity="warning",
                                             message=f"Fire warning: {detection_result.reason}")

                # ── 5. Check power status (every 5 seconds) ──
                if time.time() - last_power_check >= self.power.poll_interval:
                    last_power_check = time.time()
                    power_status = await self.power.get_status()
                    self.telemetry.log_power_status({
                        "timestamp": power_status.timestamp,
                        "source": power_status.source.value,
                        "battery_percent": power_status.battery_percent,
                        "battery_voltage": power_status.battery_voltage,
                        "is_charging": power_status.is_charging,
                        "is_low_battery": power_status.is_low_battery,
                        "is_critical_battery": power_status.is_critical_battery,
                    })
                    self._status_cache["power"] = {
                        "source": power_status.source.value,
                        "battery_percent": power_status.battery_percent,
                        "is_charging": power_status.is_charging,
                        "is_low_battery": power_status.is_low_battery,
                        "is_critical_battery": power_status.is_critical_battery,
                    }

                    # Handle low battery
                    action = await self.power.check_and_handle_low_battery()
                    if action == "shutdown":
                        logger.critical("Critical battery — shutting down")
                        self.telemetry.log_event("safe_shutdown", severity="critical",
                                                 message="Critical battery shutdown")
                        await self._graceful_shutdown()
                        await self.power.safe_shutdown()
                        return
                    elif action == "warning":
                        self.telemetry.log_event("low_battery_warning", severity="warning",
                                                 message=f"Battery at {power_status.battery_percent:.0f}%")

                # ── 6. Feed watchdog ──
                self.safety.feed_watchdog()
                watchdog_status = self.safety.check_watchdog()
                if watchdog_status["status"] == "expired":
                    self.telemetry.log_event("watchdog_expired", severity="error",
                                             message="Watchdog timer expired")

                # ── 7. Update dashboard cache ──
                self._status_cache["safety"] = {
                    "state": self.safety.state.value,
                    "can_actuate": self.safety.can_actuate,
                }
                self._status_cache["actuation"] = {
                    "state": self.actuation.state.value,
                }
                self._status_cache["timestamp"] = time.time()
                await update_status_cache(self._status_cache)

                # ── 8. DB rotation check (every 60 seconds) ──
                if time.time() - last_db_rotate >= 60:
                    last_db_rotate = time.time()
                    self.telemetry.check_and_rotate()

            except Exception as exc:
                logger.exception("Main loop error: %s", exc)
                self.telemetry.log_event("main_loop_error", severity="error", message=str(exc))

            # Sleep to maintain ~1 Hz cycle rate
            elapsed = time.time() - cycle_start
            sleep_time = max(0, 1.0 - elapsed)
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=sleep_time)
            except asyncio.TimeoutError:
                pass

        # Shutdown
        await self._graceful_shutdown()

    async def _graceful_shutdown(self) -> None:
        """Clean shutdown: close sensors, sync logs, release relays.

        # I002 — Graceful Shutdown
        """
        logger.info("Graceful shutdown initiated...")
        self._running = False

        # Close sensors
        await self.sensors.stop()

        # Deactivate relays
        await self.actuation.deactivate(reason="system_shutdown")

        # Log shutdown
        self.telemetry.log_event("system_shutdown", severity="info", message="Graceful shutdown complete")
        self.telemetry.close()

        logger.info("Shutdown complete")

    def _request_shutdown(self) -> None:
        """Signal handler for SIGINT/SIGTERM."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()


async def main() -> None:
    """Entry point for the fire suppression system."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    system = FireSuppressionSystem()
    await system.start()


if __name__ == "__main__":
    asyncio.run(main())
