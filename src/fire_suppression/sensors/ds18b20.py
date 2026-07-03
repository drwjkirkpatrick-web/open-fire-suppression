"""DS18B20 1-Wire temperature sensor driver.

# S011 — DS18B20 1-Wire Temperature
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

W1_DEVICES_BASE = "/sys/bus/w1/devices"
W1_SLAVE_FILE = "w1_slave"


class DS18B20Sensor(BaseSensor):
    """Maxim DS18B20 1-Wire digital thermometer.

    Reads temperature from the Linux 1-Wire sysfs interface.
    Requires ``dtoverlay=w1-gpio`` in ``/boot/firmware/config.txt``.
    """

    def __init__(
        self,
        name: str = "ds18b20",
        *,
        base_path: str = W1_DEVICES_BASE,
        device_id: str | None = None,  # If None, reads first found device
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.base_path = Path(base_path)
        self.device_id = device_id
        self._device_path: Path | None = None

        if not mock:
            self._discover_device()

    def _discover_device(self) -> None:
        """Find the DS18B20 device in the sysfs tree."""
        if not self.base_path.exists():
            logger.warning("1-Wire sysfs not available at %s", self.base_path)
            return

        if self.device_id:
            path = self.base_path / self.device_id / W1_SLAVE_FILE
            if path.exists():
                self._device_path = path
                logger.info("DS18B20 using specified device: %s", self.device_id)
            else:
                logger.warning("DS18B20 device %s not found", self.device_id)
        else:
            # Auto-discover first device
            for entry in self.base_path.iterdir():
                if entry.name.startswith("28-"):
                    slave_file = entry / W1_SLAVE_FILE
                    if slave_file.exists():
                        self._device_path = slave_file
                        logger.info("DS18B20 auto-discovered: %s", entry.name)
                        break

            if self._device_path is None:
                logger.warning("No DS18B20 devices found in %s", self.base_path)

    def _parse_temperature(self, data: str) -> float:
        """Parse temperature from w1_slave file content.

        Example input::

            28 00 4b 46 ff ff 0c 10 fc : crc=fc YES
            28 00 4b 46 ff ff 0c 10 fc t=25000

        Returns temperature in °C.
        """
        lines = data.strip().split("\n")
        if len(lines) < 2:
            raise ValueError("Invalid w1_slave format")

        # Check CRC
        if "YES" not in lines[0]:
            raise ValueError("DS18B20 CRC check failed")

        # Parse temperature
        temp_line = lines[1]
        if "t=" not in temp_line:
            raise ValueError("Temperature not found in w1_slave data")

        temp_str = temp_line.split("t=")[1]
        temp_millidegrees = int(temp_str)
        return temp_millidegrees / 1000.0

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={"temperature_c": 25.0},
                raw="28 00 4b 46 ff ff 0c 10 fc : crc=fc YES\n28 00 4b 46 ff ff 0c 10 fc t=25000",
                unit="°C",
            )

        if self._device_path is None:
            raise RuntimeError("DS18B20 device not discovered")

        try:
            data = self._device_path.read_text()
            temp_c = self._parse_temperature(data)

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={"temperature_c": round(temp_c, 3)},
                raw=data,
                unit="°C",
            )

        except Exception as exc:
            logger.error("DS18B20 read error: %s", exc)
            raise

    async def close(self) -> None:
        self._closed = True

    def get_device_ids(self) -> list[str]:
        """Return list of discovered DS18B20 device IDs."""
        if not self.base_path.exists():
            return []
        return [
            entry.name
            for entry in self.base_path.iterdir()
            if entry.name.startswith("28-") and (entry / W1_SLAVE_FILE).exists()
        ]
