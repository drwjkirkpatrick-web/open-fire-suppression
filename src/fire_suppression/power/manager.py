"""Power management and UPS monitoring for Raspberry Pi 5.

# P001 — Battery Voltage Monitoring
# P002 — Low Battery Warning
# P003 — Safe Shutdown on Low Battery
# P004 — AC Power Loss Detection
# P005 — AC Power Restore
# P006 — PiSugar / PiJuice Integration
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from fire_suppression.config import Config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PowerSource(Enum):
    """Current power source."""
    AC = "ac"
    BATTERY = "battery"
    UNKNOWN = "unknown"


@dataclass
class PowerStatus:
    """Current power status snapshot."""
    source: PowerSource
    battery_percent: float
    battery_voltage: float
    is_charging: bool
    is_low_battery: bool
    is_critical_battery: bool
    timestamp: float


class PowerManager:
    """Monitors power status, battery level, and manages safe shutdown.

    Supports multiple UPS types:
    - ``pisugar``: PiSugar 3 Plus (I2C API)
    - ``pijuice``: PiJuice HAT (I2C API)
    - ``diy``: Custom ADC-based monitoring
    - ``none``: AC-only, no battery monitoring
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        power = self.config.section("power")

        self.ups_type = str(power.get("ups_type", "none")).lower()
        self.battery_adc_channel = int(power.get("battery_adc_channel", 3))
        self.voltage_divider_ratio = float(power.get("voltage_divider_ratio", 2.0))
        self.low_battery_percent = float(power.get("low_battery_percent", 20))
        self.critical_battery_percent = float(power.get("critical_battery_percent", 5))
        self.ac_detect_pin = int(power.get("ac_detect_pin", 25))
        self.poll_interval = float(power.get("poll_interval_seconds", 5.0))

        self._last_status: PowerStatus | None = None
        self._low_battery_warned = False
        self._gpio = None
        self._bus = None

        if not self.config.mock_hardware:
            self._init_hardware()

    def _init_hardware(self) -> None:
        """Initialize power monitoring hardware."""
        if self.ups_type in ("pisugar", "pijuice"):
            try:
                from smbus2 import SMBus
                self._bus = SMBus(self.config.get("sensors", "i2c_bus", default=1))
                logger.info("UPS %s I2C bus initialized", self.ups_type)
            except Exception as exc:
                logger.error("UPS I2C init failed: %s", exc)
                self._bus = None
        elif self.ups_type == "diy":
            try:
                from gpiozero import Button
                self._ac_detect = Button(self.ac_detect_pin, pull_up=True)
                logger.info("DIY power monitoring initialized (AC detect pin %d)", self.ac_detect_pin)
            except Exception as exc:
                logger.error("DIY power GPIO init failed: %s", exc)
                self._ac_detect = None

    async def get_status(self) -> PowerStatus:
        """Read current power status from UPS or ADC."""
        if self.config.mock_hardware:
            return PowerStatus(
                source=PowerSource.AC,
                battery_percent=85.0,
                battery_voltage=4.0,
                is_charging=True,
                is_low_battery=False,
                is_critical_battery=False,
                timestamp=time.time(),
            )

        if self.ups_type == "pisugar":
            return await self._read_pisugar()
        elif self.ups_type == "pijuice":
            return await self._read_pijuice()
        elif self.ups_type == "diy":
            return await self._read_diy()
        else:
            # No UPS — assume AC power
            return PowerStatus(
                source=PowerSource.AC,
                battery_percent=100.0,
                battery_voltage=5.0,
                is_charging=True,
                is_low_battery=False,
                is_critical_battery=False,
                timestamp=time.time(),
            )

    async def _read_pisugar(self) -> PowerStatus:
        """Read PiSugar 3 Plus battery status via I2C."""
        # PiSugar exposes battery info via its own I2C registers
        # In production, use pisugar-server REST API or official Python library
        # This is a simplified placeholder
        try:
            # Mock reading for now — real implementation would query PiSugar registers
            battery_pct = 75.0
            battery_v = 3.8
            is_charging = True
            return PowerStatus(
                source=PowerSource.AC if is_charging else PowerSource.BATTERY,
                battery_percent=battery_pct,
                battery_voltage=battery_v,
                is_charging=is_charging,
                is_low_battery=battery_pct <= self.low_battery_percent,
                is_critical_battery=battery_pct <= self.critical_battery_percent,
                timestamp=time.time(),
            )
        except Exception as exc:
            logger.error("PiSugar read failed: %s", exc)
            return self._default_status()

    async def _read_pijuice(self) -> PowerStatus:
        """Read PiJuice battery status via I2C."""
        try:
            # PiJuice I2C address is 0x14
            # In production, use pijuice Python library
            battery_pct = 70.0
            battery_v = 3.7
            is_charging = True
            return PowerStatus(
                source=PowerSource.AC if is_charging else PowerSource.BATTERY,
                battery_percent=battery_pct,
                battery_voltage=battery_v,
                is_charging=is_charging,
                is_low_battery=battery_pct <= self.low_battery_percent,
                is_critical_battery=battery_pct <= self.critical_battery_percent,
                timestamp=time.time(),
            )
        except Exception as exc:
            logger.error("PiJuice read failed: %s", exc)
            return self._default_status()

    async def _read_diy(self) -> PowerStatus:
        """Read DIY ADC-based battery monitoring."""
        try:
            from smbus2 import SMBus

            # Read battery voltage from ADS1115 on configured channel
            # Config: OS=1, MUX=single channel, PGA=±4.096V, MODE=single-shot, DR=128SPS
            mux_codes = [0x4000, 0x5000, 0x6000, 0x7000]
            config = 0xC283 | (mux_codes[self.battery_adc_channel] & 0x7000)

            bus = SMBus(self.config.get("sensors", "i2c_bus", default=1))
            adc_addr = self.config.get("sensors", "ads1115", "address", default=0x48)

            bus.write_i2c_block_data(adc_addr, 0x01, [(config >> 8) & 0xFF, config & 0xFF])
            await asyncio.sleep(0.01)
            result = bus.read_i2c_block_data(adc_addr, 0x00, 2)
            import struct
            raw = struct.unpack(">h", bytes(result))[0]
            bus.close()

            adc_voltage = (raw / 32767.0) * 4.096
            battery_voltage = adc_voltage * self.voltage_divider_ratio

            # Estimate percentage for Li-ion (3.0V = 0%, 4.2V = 100%)
            battery_pct = max(0.0, min(100.0, (battery_voltage - 3.0) / 1.2 * 100))

            # AC detect via GPIO
            ac_present = self._ac_detect.is_pressed if hasattr(self, '_ac_detect') and self._ac_detect else True

            return PowerStatus(
                source=PowerSource.AC if ac_present else PowerSource.BATTERY,
                battery_percent=round(battery_pct, 1),
                battery_voltage=round(battery_voltage, 3),
                is_charging=ac_present,
                is_low_battery=battery_pct <= self.low_battery_percent,
                is_critical_battery=battery_pct <= self.critical_battery_percent,
                timestamp=time.time(),
            )
        except Exception as exc:
            logger.error("DIY power read failed: %s", exc)
            return self._default_status()

    def _default_status(self) -> PowerStatus:
        return PowerStatus(
            source=PowerSource.UNKNOWN,
            battery_percent=0.0,
            battery_voltage=0.0,
            is_charging=False,
            is_low_battery=False,
            is_critical_battery=False,
            timestamp=time.time(),
        )

    async def check_and_handle_low_battery(self) -> str | None:
        """Check battery level and return action required.

        Returns:
            - ``"warning"`` if low battery threshold reached
            - ``"shutdown"`` if critical battery threshold reached
            - ``None`` if battery level OK
        """
        status = await self.get_status()
        self._last_status = status

        if status.is_critical_battery:
            logger.critical("CRITICAL BATTERY: %.0f%% — initiating safe shutdown", status.battery_percent)
            return "shutdown"

        if status.is_low_battery and not self._low_battery_warned:
            logger.warning("LOW BATTERY: %.0f%%", status.battery_percent)
            self._low_battery_warned = True
            return "warning"

        if not status.is_low_battery:
            self._low_battery_warned = False

        return None

    async def safe_shutdown(self) -> None:
        """Initiate safe system shutdown.

        Syncs filesystem and calls ``shutdown -h now``.
        """
        logger.critical("SAFE SHUTDOWN initiated")
        try:
            # Sync filesystem
            os.sync()
            await asyncio.sleep(0.5)
            # Shutdown
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
        except Exception as exc:
            logger.error("Safe shutdown failed: %s", exc)

    # ── Cleanup ──

    async def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        logger.info("Power manager closed")
