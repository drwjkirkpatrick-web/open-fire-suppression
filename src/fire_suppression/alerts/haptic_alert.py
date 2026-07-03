"""Haptic alert system for hearing-impaired individuals.

# ADD-011 — Haptic Alert for Hearing-Impaired

Connects to Bluetooth Low Energy wearable devices (smartwatches,
pagers, dedicated haptic bands) and sends vibration patterns
corresponding to alert severity.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class HapticPattern(Enum):
    """Vibration patterns for different alert types."""
    INFO = "short"       # One short pulse
    WARNING = "double"   # Two short pulses
    FIRE_ALERT = "sos"   # S-O-S pattern (3 short, 3 long, 3 short)
    EVACUATE = "rapid"   # Rapid continuous pulses
    ALL_CLEAR = "long"   # One long pulse


@dataclass
class HapticDevice:
    name: str
    mac_address: str
    connected: bool = False


class HapticAlertSystem:
    """BLE haptic alert controller.

    Usage::

        haptic = HapticAlertSystem()
        await haptic.connect_device("AA:BB:CC:DD:EE:FF")
        await haptic.send_pattern(HapticPattern.FIRE_ALERT)
    """

    def __init__(self, *, mock: bool = False) -> None:
        self.mock = mock
        self._devices: dict[str, HapticDevice] = {}
        self._client = None

    async def connect_device(self, mac_address: str, name: str = "haptic_device") -> bool:
        """Pair and connect to a BLE haptic device."""
        if self.mock:
            self._devices[mac_address] = HapticDevice(name=name, mac_address=mac_address, connected=True)
            logger.info("[MOCK] Haptic device connected: %s", mac_address)
            return True

        try:
            import bleak
            # bleak is async-native
            self._client = bleak.BleakClient(mac_address)
            await self._client.connect()
            self._devices[mac_address] = HapticDevice(name=name, mac_address=mac_address, connected=True)
            logger.info("Haptic device connected: %s", mac_address)
            return True
        except ImportError:
            logger.warning("bleak not installed — haptic alerts disabled")
            self.mock = True
            return False
        except Exception as exc:
            logger.error("Haptic device connection failed: %s", exc)
            return False

    async def send_pattern(self, pattern: HapticPattern, mac_address: str | None = None) -> None:
        """Send a haptic pattern to one or all connected devices."""
        targets = [mac_address] if mac_address else list(self._devices.keys())

        for addr in targets:
            device = self._devices.get(addr)
            if not device or not device.connected:
                continue

            if self.mock:
                logger.info("[MOCK HAPTIC] %s -> %s", pattern.value, addr)
                continue

            try:
                # Write to vibration characteristic (common UUID for haptic devices)
                # Actual UUID varies by device — this is a placeholder
                vibration_uuid = "00002a06-0000-1000-8000-00805f9b34fb"
                pattern_bytes = self._pattern_to_bytes(pattern)
                if self._client and self._client.is_connected:
                    await self._client.write_gatt_char(vibration_uuid, pattern_bytes)
                    logger.debug("Haptic pattern sent to %s: %s", addr, pattern.value)
            except Exception as exc:
                logger.warning("Haptic send failed for %s: %s", addr, exc)

    def _pattern_to_bytes(self, pattern: HapticPattern) -> bytes:
        """Convert pattern to device-specific byte sequence."""
        # Generic vibration motor patterns (duration in ms)
        patterns = {
            HapticPattern.INFO: b"\x01\x32",      # 50ms
            HapticPattern.WARNING: b"\x02\x32\x00\x32",  # 50ms pause 50ms
            HapticPattern.FIRE_ALERT: b"\x03\x32\x32\x32\x64\x64\x64\x32\x32\x32",
            HapticPattern.EVACUATE: b"\x0A\x1E",  # 10 x 30ms rapid
            HapticPattern.ALL_CLEAR: b"\x01\xC8",  # 200ms
        }
        return patterns.get(pattern, b"\x01\x32")

    async def disconnect_all(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        for device in self._devices.values():
            device.connected = False

    def get_connected_devices(self) -> list[HapticDevice]:
        return [d for d in self._devices.values() if d.connected]
