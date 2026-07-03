"""Sensor manager for open-fire-suppression.

Orchestrates multiple sensors, polls them, tracks health, and aggregates readings.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fire_suppression.config import Config
from fire_suppression.sensors.ads1115 import ADS1115Sensor
from fire_suppression.sensors.amg8833 import AMG8833Sensor
from fire_suppression.sensors.base import BaseSensor, MockSensor, SensorReading
from fire_suppression.sensors.bme680 import BME680Sensor
from fire_suppression.sensors.ds18b20 import DS18B20Sensor
from fire_suppression.sensors.ens160 import ENS160Sensor
from fire_suppression.sensors.mlx90614 import MLX90614Sensor
from fire_suppression.sensors.mlx90640 import MLX90640Sensor
from fire_suppression.sensors.mq2 import MQ2Sensor
from fire_suppression.sensors.picamera import PiCameraSensor
from fire_suppression.sensors.sht40 import SHT40Sensor

logger = logging.getLogger(__name__)


class SensorManager:
    """Manages all sensors, polls them, and tracks health."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._sensors: dict[str, BaseSensor] = {}
        self._running = False

    async def start(self) -> None:
        """Initialize all configured sensors."""
        sensors_cfg = self.config.section("sensors")
        mock = self.config.mock_hardware

        if sensors_cfg.get("mq2", {}).get("enabled", True):
            self._sensors["mq2"] = MQ2Sensor("mq2", mock=mock)
        if sensors_cfg.get("sht40", {}).get("enabled", True):
            self._sensors["sht40"] = SHT40Sensor("sht40", mock=mock)
        if sensors_cfg.get("mlx90614", {}).get("enabled", True):
            self._sensors["mlx90614"] = MLX90614Sensor("mlx90614", mock=mock)
        if sensors_cfg.get("bme680", {}).get("enabled", True):
            self._sensors["bme680"] = BME680Sensor("bme680", mock=mock)
        if sensors_cfg.get("ens160", {}).get("enabled", True):
            self._sensors["ens160"] = ENS160Sensor("ens160", mock=mock)
        if sensors_cfg.get("amg8833", {}).get("enabled", True):
            self._sensors["amg8833"] = AMG8833Sensor("amg8833", mock=mock)
        if sensors_cfg.get("mlx90640", {}).get("enabled", False):
            self._sensors["mlx90640"] = MLX90640Sensor("mlx90640", mock=mock)
        if sensors_cfg.get("ds18b20", {}).get("enabled", True):
            self._sensors["ds18b20"] = DS18B20Sensor("ds18b20", mock=mock)
        if sensors_cfg.get("picamera", {}).get("enabled", True):
            self._sensors["picamera"] = PiCameraSensor("picamera", mock=mock)
        if sensors_cfg.get("ads1115", {}).get("enabled", True):
            self._sensors["ads1115"] = ADS1115Sensor("ads1115", mock=mock)

        self._running = True
        logger.info("SensorManager started with %d sensor(s)", len(self._sensors))

    async def stop(self) -> None:
        """Close all sensors and release resources."""
        for sensor in self._sensors.values():
            try:
                await sensor.close()
            except Exception as exc:
                logger.warning("Error closing sensor %s: %s", sensor.name, exc)
        self._sensors.clear()
        self._running = False
        logger.info("SensorManager stopped")

    async def poll_all(self) -> dict[str, SensorReading | None]:
        """Poll all sensors and return readings.

        Returns a mapping of sensor_name -> SensorReading or None on failure.
        """
        readings: dict[str, SensorReading | None] = {}
        tasks = []
        names = []
        for name, sensor in self._sensors.items():
            names.append(name)
            tasks.append(sensor.read_with_health())
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                logger.warning("Sensor %s poll failed: %s", name, result)
                readings[name] = None
            else:
                readings[name] = result  # type: ignore[assignment]
        return readings

    def get_sensor(self, name: str) -> BaseSensor | None:
        """Return a sensor by name, or None if not registered."""
        return self._sensors.get(name)

    def __len__(self) -> int:
        return len(self._sensors)

    def __iter__(self):
        return iter(self._sensors.values())

    def list_sensors(self) -> list[str]:
        """Return a list of all registered sensor names."""
        return list(self._sensors.keys())
