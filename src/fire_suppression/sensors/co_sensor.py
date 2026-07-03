"""Carbon monoxide (CO) sensor driver.

# ADD-017 — CO / Carbon Monoxide Detection

Integrates electrochemical CO sensor (e.g., Winsen ZE07-CO,
MiCS-4514) with dedicated alert threshold. CO is produced by
incomplete combustion before visible smoke appears.
"""
from __future__ import annotations

import logging
import struct
import time
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading, SensorStatus

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

ZE07_CO_ADDR = 0xA0 >> 1  # 0x50 (7-bit address)


class COSensor(BaseSensor):
    """Carbon monoxide sensor driver for ZE07-CO (UART) or MiCS-4514 (analog).

    # ADD-017 — CO / Carbon Monoxide Detection
    """

    def __init__(
        self,
        name: str = "co",
        interface: str = "uart",
        uart_port: str = "/dev/ttyAMA0",
        baud: int = 9600,
        alert_threshold_ppm: float = 35.0,  # OSHA 8-hour TWA
        *,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.interface = interface
        self.uart_port = uart_port
        self.baud = baud
        self.alert_threshold = alert_threshold_ppm
        self._serial = None

        if not mock and interface == "uart":
            try:
                import serial
                self._serial = serial.Serial(uart_port, baud, timeout=1.0)
            except Exception as exc:
                logger.warning("CO sensor serial init failed: %s", exc)
                self.mock = True

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                self.name, time.time(),
                {"co_ppm": 0.0, "alert": False},
                SensorStatus.OK,
            )

        if self.interface == "uart" and self._serial:
            return await self._read_uart()
        return SensorReading(
            self.name, time.time(),
            {"co_ppm": 0.0, "error": "no_interface"},
            SensorStatus.ERROR,
        )

    async def _read_uart(self) -> SensorReading:
        """Read ZE07-CO sensor via UART.

        Protocol: FF 01 [gas_high] [gas_low] [temp] [status] [checksum]
        """
        try:
            self._serial.write(b"\xFF\x01\x86\x00\x00\x00\x00\x00\x79")
            import time as _time
            _time.sleep(0.1)
            data = self._serial.read(9)
            if len(data) != 9:
                return SensorReading(self.name, time.time(), {"error": "short_read"}, SensorStatus.ERROR)

            if data[0] != 0xFF or data[1] != 0x86:
                return SensorReading(self.name, time.time(), {"error": "bad_header"}, SensorStatus.ERROR)

            ppm = (data[2] << 8) | data[3]
            temp = data[4] - 40  # Offset
            status = data[5]

            # Verify checksum
            checksum = sum(data[1:8]) % 256
            checksum = (~checksum + 1) % 256
            if checksum != data[8]:
                return SensorReading(self.name, time.time(), {"error": "bad_checksum"}, SensorStatus.ERROR)

            return SensorReading(
                self.name, time.time(),
                {
                    "co_ppm": ppm,
                    "sensor_temp_c": temp,
                    "status": status,
                    "alert": ppm >= self.alert_threshold,
                },
                SensorStatus.OK,
            )
        except Exception as exc:
            logger.error("CO sensor read error: %s", exc)
            return SensorReading(self.name, time.time(), {"error": str(exc)}, SensorStatus.ERROR)

    async def close(self) -> None:
        if self._serial:
            self._serial.close()
            self._serial = None

    def get_alert_threshold(self) -> float:
        return self.alert_threshold

    def set_alert_threshold(self, ppm: float) -> None:
        self.alert_threshold = ppm
        logger.info("CO alert threshold set to %.1f ppm", ppm)
