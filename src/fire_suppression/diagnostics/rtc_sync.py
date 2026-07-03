"""RTC / NTP time synchronisation diagnostics.

# BOT-009 — RTC/NTP Sync

Reads a DS3231 real-time clock over I²C (address ``0x68``), compares it with
the system clock, checks whether NTP is synchronised, and flags timestamps with
a confidence level.  When clock drift exceeds a configurable threshold the
module can optionally trigger an NTP re-sync.

Usage::

    from fire_suppression.diagnostics.rtc_sync import RtcSyncMonitor
    mon = RtcSyncMonitor(mock=False, drift_threshold_s=5.0)
    status = mon.health_check()
    confidence = mon.get_timestamp_confidence()
"""
from __future__ import annotations

import logging
import os
import re
import struct
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

DS3231_I2C_ADDRESS = 0x68
DS3231_REG_SECONDS = 0x00
DS3231_REG_MINUTES = 0x01
DS3231_REG_HOURS = 0x02
DS3231_REG_DAY = 0x03
DS3231_REG_DATE = 0x04
DS3231_REG_MONTH = 0x05
DS3231_REG_YEAR = 0x06

DEFAULT_DRIFT_THRESHOLD_S = 5.0
DEFAULT_BUS_NUMBER = 1


# ── Bilingual messages ─────────────────────────────────────────────────

_MSGS: Dict[str, Dict[str, str]] = {
    "init_ok": {
        "en": "RTC/NTP sync monitor initialised — drift threshold {threshold}s, mock={mock}",
        "sw": "Kiolesuraanifu ya RTC/NTP kimeanzishwa — kikomo cha kutofautiana {threshold}s, mock={mock}",
    },
    "mock_mode": {
        "en": "RTC/NTP monitor running in mock mode",
        "sw": "Kiolesuraanifu RTC/NTP kinafanya kazi katika hali ya uigizo",
    },
    "ntp_synced": {
        "en": "System clock is NTP-synchronised",
        "sw": "Saa ya mfumo imelinganishwa na NTP",
    },
    "ntp_not_synced": {
        "en": "System clock is NOT NTP-synchronised",
        "sw": "Saa ya mfumo hailingani na NTP",
    },
    "rtc_read_ok": {
        "en": "DS3231 RTC read successfully — {rtc_time}",
        "sw": "DS3231 RTC imesomwa kwa mafanikio — {rtc_time}",
    },
    "rtc_read_fail": {
        "en": "Failed to read DS3231 RTC: {error}",
        "sw": "Imeshindwa kusoma DS3231 RTC: {error}",
    },
    "drift_detected": {
        "en": "Clock drift detected: {drift:.2f}s (RTC {rtc_time} vs SYS {sys_time})",
        "sw": "Kutofautiana kwa saa kimegunduliwa: {drift:.2f}s (RTC {rtc_time} vs SYS {sys_time})",
    },
    "drift_within_limit": {
        "en": "Clock drift within acceptable limits: {drift:.2f}s",
        "sw": "Kutofautiana kwa saa ndani ya mipaka inayokubalika: {drift:.2f}s",
    },
    "ntp_sync_triggered": {
        "en": "NTP sync triggered because drift {drift:.2f}s exceeds threshold {threshold}s",
        "sw": "Mlinganifu wa NTP umeanzishwa kwa sababu kutofautiana {drift:.2f}s kimezidi kiwango {threshold}s",
    },
    "ntp_sync_fail": {
        "en": "NTP sync attempt failed: {error}",
        "sw": "Jaribio la mlinganifu wa NTP limekosa: {error}",
    },
}


def _msg(key: str, lang: str = "en", **kwargs: Any) -> str:
    m = _MSGS.get(key, {})
    return m.get(lang, m.get("en", key)).format(**kwargs)


# ── Enums ────────────────────────────────────────────────────────────────

class TimestampConfidence(Enum):
    """Confidence level for timestamps based on available time sources."""

    HIGH = "high"      # NTP synced
    MEDIUM = "medium"  # RTC only
    LOW = "low"        # Neither NTP nor RTC available


class NtpSyncMethod(Enum):
    """Method used to check or trigger NTP synchronisation."""

    TIMEDATECTL = "timedatectl"
    NTPQ = "ntpq"
    CHRONYC = "chronyc"
    NTPDATE = "ntpdate"
    UNKNOWN = "unknown"


# ── Data classes ───────────────────────────────────────────────────────

@dataclass
class TimeStatus:
    """Snapshot of the current time synchronisation state."""

    system_time: float
    rtc_time: Optional[float] = None
    drift_seconds: float = 0.0
    ntp_synced: bool = False
    ntp_method: NtpSyncMethod = NtpSyncMethod.UNKNOWN
    confidence: TimestampConfidence = TimestampConfidence.LOW
    message_en: str = ""
    message_sw: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_time": self.system_time,
            "rtc_time": self.rtc_time,
            "drift_seconds": self.drift_seconds,
            "ntp_synced": self.ntp_synced,
            "ntp_method": self.ntp_method.value,
            "confidence": self.confidence.value,
            "message_en": self.message_en,
            "message_sw": self.message_sw,
        }


@dataclass
class SyncEvent:
    """Record of a sync attempt or drift alert."""

    timestamp: float
    event_type: str  # "drift_alert", "ntp_attempt", "ntp_success", "ntp_fail"
    details_en: str
    details_sw: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "details_en": self.details_en,
            "details_sw": self.details_sw,
        }


# ── Helper functions ───────────────────────────────────────────────────


def _bcd_to_int(bcd: int) -> int:
    """Convert DS3231 BCD register value to integer."""
    return ((bcd >> 4) * 10) + (bcd & 0x0F)


def _int_to_bcd(n: int) -> int:
    """Convert integer to DS3231 BCD register value."""
    return ((n // 10) << 4) | (n % 10)


def _is_12h_mode(hour_reg: int) -> bool:
    return bool(hour_reg & 0x40)


def _parse_ds3231_hour(hour_reg: int) -> int:
    """Extract hour from DS3231 hour register (handles 12h/24h)."""
    if _is_12h_mode(hour_reg):
        hour = _bcd_to_int(hour_reg & 0x1F)
        if hour == 12:
            hour = 0
        if hour_reg & 0x20:
            hour += 12
        return hour
    return _bcd_to_int(hour_reg & 0x3F)


def _parse_ds3231_year(month_reg: int, year_reg: int) -> int:
    """Parse year from DS3231 month and year registers."""
    century = 2000 if (month_reg & 0x80) else 1900
    return century + _bcd_to_int(year_reg)


def _format_time_tuple(t: time.struct_time) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", t)


# ── Main class ─────────────────────────────────────────────────────────

class RtcSyncMonitor:
    """Monitors DS3231 RTC and NTP synchronisation status.

    Args:
        bus_number: I²C bus number (default ``1``).
        drift_threshold_s: Maximum acceptable drift in seconds before an
            alert or re-sync attempt is triggered.
        auto_sync: If ``True``, attempt NTP re-sync when drift is exceeded.
        mock: If ``True``, use synthetic values and avoid real I²C / system calls.
        lang: Preferred language for log messages (``"en"`` or ``"sw"``).
    """

    def __init__(
        self,
        bus_number: int = DEFAULT_BUS_NUMBER,
        drift_threshold_s: float = DEFAULT_DRIFT_THRESHOLD_S,
        auto_sync: bool = True,
        mock: bool = False,
        lang: str = "en",
    ) -> None:
        self.bus_number = bus_number
        self.drift_threshold_s = drift_threshold_s
        self.auto_sync = auto_sync
        self.mock = mock
        self.lang = lang
        self.feature_id = "BOT-009"

        self._bus: Any = None
        self._status: Optional[TimeStatus] = None
        self._events: list[SyncEvent] = []

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
                logger.debug("SMBus opened on bus %d", bus_number)
            except Exception as exc:
                logger.warning("Cannot open SMBus: %s — falling back to mock", exc)
                self.mock = True

        if mock:
            logger.info(_msg("mock_mode", lang=self.lang))

        logger.info(
            _msg(
                "init_ok",
                lang=self.lang,
                threshold=drift_threshold_s,
                mock=self.mock,
            )
        )

    # ── RTC reading ────────────────────────────────────────────────────

    def _read_rtc_registers(self) -> Tuple[int, ...]:
        """Read all seven DS3231 time registers starting at 0x00."""
        if self._bus is None:
            raise RuntimeError("SMBus not available")
        regs = []
        for offset in range(7):
            val = self._bus.read_byte_data(DS3231_I2C_ADDRESS, DS3231_REG_SECONDS + offset)
            regs.append(val)
        return tuple(regs)

    def _parse_rtc_time(self, regs: Tuple[int, ...]) -> time.struct_time:
        """Convert DS3231 register tuple to a ``time.struct_time``."""
        sec = _bcd_to_int(regs[0])
        minute = _bcd_to_int(regs[1])
        hour = _parse_ds3231_hour(regs[2])
        day = _bcd_to_int(regs[4])
        month = _bcd_to_int(regs[5] & 0x7F)
        year = _parse_ds3231_year(regs[5], regs[6])

        # weekday is ignored by time.mktime, but we keep it for completeness
        return time.struct_time((year, month, day, hour, minute, sec, 0, 0, -1))

    def read_rtc(self) -> Optional[time.struct_time]:
        """Return the current DS3231 RTC time as ``time.struct_time``.

        Returns ``None`` on failure or when running in mock mode without a
        configured mock RTC value.
        """
        if self.mock:
            # In mock mode return a time slightly offset from system time
            t = time.localtime(time.time() + 3.0)
            logger.debug("Mock RTC returned %s", _format_time_tuple(t))
            return t

        try:
            regs = self._read_rtc_registers()
            rtc_struct = self._parse_rtc_time(regs)
            logger.debug("RTC read: %s", _format_time_tuple(rtc_struct))
            return rtc_struct
        except Exception as exc:
            logger.error(_msg("rtc_read_fail", lang=self.lang, error=str(exc)))
            return None

    # ── NTP status ───────────────────────────────────────────────────────

    @staticmethod
    def _run_cmd(cmd: list[str], timeout: float = 3.0) -> Tuple[int, str, str]:
        """Run a shell command and return (rc, stdout, stderr)."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except Exception as exc:
            return -1, "", str(exc)

    def check_ntp_status(self) -> Tuple[bool, NtpSyncMethod]:
        """Check whether the system clock is NTP-synchronised.

        Tries ``timedatectl``, then ``ntpq -p``, then ``chronyc tracking``.
        Returns ``(synced, method)``.
        """
        if self.mock:
            return False, NtpSyncMethod.UNKNOWN

        # timedatectl status
        rc, stdout, _ = self._run_cmd(["timedatectl", "status"])
        if rc == 0:
            synced = "NTP synchronized: yes" in stdout or "System clock synchronized: yes" in stdout
            if synced:
                return True, NtpSyncMethod.TIMEDATECTL
            # Some distros show "NTP service: active" but not synced status
            if "NTP enabled: yes" in stdout:
                return False, NtpSyncMethod.TIMEDATECTL

        # ntpq -p
        rc, stdout, _ = self._run_cmd(["ntpq", "-p"])
        if rc == 0:
            # Look for a line starting with * (synced peer)
            for line in stdout.splitlines():
                if line.startswith("*"):
                    return True, NtpSyncMethod.NTPQ
            return False, NtpSyncMethod.NTPQ

        # chronyc tracking
        rc, stdout, _ = self._run_cmd(["chronyc", "tracking"])
        if rc == 0:
            # If we can get tracking info, chronyd is running
            # "Leap status" : Normal indicates synced
            if "Leap status" in stdout:
                if "Normal" in stdout:
                    return True, NtpSyncMethod.CHRONYC
                return False, NtpSyncMethod.CHRONYC

        return False, NtpSyncMethod.UNKNOWN

    def attempt_ntp_sync(self) -> bool:
        """Attempt to force an immediate NTP synchronisation.

        Tries ``timedatectl set-ntp true``, ``systemctl restart
        systemd-timesyncd``, ``ntpdate``, and ``ntpd -gq`` in that order.
        Returns ``True`` if any command succeeds.
        """
        if self.mock:
            logger.info("Mock NTP sync: simulated success")
            return True

        commands = [
            (["timedatectl", "set-ntp", "true"], NtpSyncMethod.TIMEDATECTL),
            (["systemctl", "restart", "systemd-timesyncd"], NtpSyncMethod.TIMEDATECTL),
            (["ntpdate", "-u", "pool.ntp.org"], NtpSyncMethod.NTPDATE),
            (["ntpd", "-gq"], NtpSyncMethod.NTPQ),
        ]

        for cmd, method in commands:
            rc, _, _ = self._run_cmd(cmd, timeout=10.0)
            if rc == 0:
                logger.info("NTP sync succeeded via %s", method.value)
                return True

        logger.error(_msg("ntp_sync_fail", lang=self.lang, error="all methods failed"))
        return False

    # ── Drift detection ────────────────────────────────────────────────

    def _calculate_drift(
        self, system_time: float, rtc_struct: Optional[time.struct_time]
    ) -> float:
        if rtc_struct is None:
            return 0.0
        rtc_epoch = time.mktime(rtc_struct)
        return abs(system_time - rtc_epoch)

    def _determine_confidence(self, ntp_synced: bool, rtc_available: bool) -> TimestampConfidence:
        if ntp_synced:
            return TimestampConfidence.HIGH
        if rtc_available:
            return TimestampConfidence.MEDIUM
        return TimestampConfidence.LOW

    def poll(self) -> TimeStatus:
        """Poll RTC and NTP status, compute drift, and optionally trigger sync.

        Returns a :class:`TimeStatus` snapshot.
        """
        system_time = time.time()
        rtc_struct = self.read_rtc()
        ntp_synced, ntp_method = self.check_ntp_status()

        drift = self._calculate_drift(system_time, rtc_struct)
        rtc_available = rtc_struct is not None
        confidence = self._determine_confidence(ntp_synced, rtc_available)

        sys_time_str = _format_time_tuple(time.localtime(system_time))
        rtc_time_str = _format_time_tuple(rtc_struct) if rtc_struct else "N/A"

        if drift > self.drift_threshold_s:
            msg_en = _msg(
                "drift_detected",
                lang="en",
                drift=drift,
                rtc_time=rtc_time_str,
                sys_time=sys_time_str,
            )
            msg_sw = _msg(
                "drift_detected",
                lang="sw",
                drift=drift,
                rtc_time=rtc_time_str,
                sys_time=sys_time_str,
            )
            logger.warning("[RTC] %s | %s", msg_en, msg_sw)
            self._events.append(
                SyncEvent(
                    timestamp=system_time,
                    event_type="drift_alert",
                    details_en=msg_en,
                    details_sw=msg_sw,
                )
            )

            if self.auto_sync and not ntp_synced:
                sync_msg_en = _msg(
                    "ntp_sync_triggered",
                    lang="en",
                    drift=drift,
                    threshold=self.drift_threshold_s,
                )
                sync_msg_sw = _msg(
                    "ntp_sync_triggered",
                    lang="sw",
                    drift=drift,
                    threshold=self.drift_threshold_s,
                )
                logger.warning("[RTC] %s | %s", sync_msg_en, sync_msg_sw)
                success = self.attempt_ntp_sync()
                self._events.append(
                    SyncEvent(
                        timestamp=time.time(),
                        event_type="ntp_success" if success else "ntp_fail",
                        details_en=sync_msg_en,
                        details_sw=sync_msg_sw,
                    )
                )
        else:
            msg_en = _msg("drift_within_limit", lang="en", drift=drift)
            msg_sw = _msg("drift_within_limit", lang="sw", drift=drift)
            logger.debug("[RTC] %s | %s", msg_en, msg_sw)

        status = TimeStatus(
            system_time=system_time,
            rtc_time=time.mktime(rtc_struct) if rtc_struct else None,
            drift_seconds=drift,
            ntp_synced=ntp_synced,
            ntp_method=ntp_method,
            confidence=confidence,
            message_en=msg_en,
            message_sw=msg_sw,
        )
        self._status = status
        return status

    # ── Health & introspection ─────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """Return current health status of the time synchronisation subsystem."""
        status = self._status
        if status is None:
            # Run a single poll if never polled
            status = self.poll()

        healthy = status.confidence != TimestampConfidence.LOW
        if status.drift_seconds > self.drift_threshold_s:
            healthy = False

        return {
            "healthy": healthy,
            "ntp_synced": status.ntp_synced,
            "ntp_method": status.ntp_method.value,
            "rtc_available": status.rtc_time is not None,
            "drift_seconds": status.drift_seconds,
            "confidence": status.confidence.value,
            "mock": self.mock,
        }

    def get_feature_overview(self) -> Dict[str, Any]:
        """Return feature metadata."""
        return {
            "feature_id": self.feature_id,
            "feature_name": "RTC/NTP Sync",
            "mock": self.mock,
            "supports": [
                "ds3231_i2c_read",
                "ntp_status_detection",
                "clock_drift_monitoring",
                "timestamp_confidence_flags",
                "auto_ntp_resync",
                "bilingual_messages",
            ],
        }

    def to_dict(self) -> Dict[str, Any]:
        """Return full serialisable state."""
        status = self._status
        if status is None:
            status = self.poll()

        return {
            **self.health_check(),
            "feature_id": self.feature_id,
            "feature_name": "RTC/NTP Sync",
            "drift_threshold_s": self.drift_threshold_s,
            "auto_sync": self.auto_sync,
            "lang": self.lang,
            "latest_status": status.to_dict(),
            "events": [e.to_dict() for e in self._events[-10:]],
        }

    def get_timestamp_confidence(self) -> TimestampConfidence:
        """Return the current timestamp confidence level.

        Convenience wrapper that does a fresh :meth:`poll` if no status has
        been recorded yet.
        """
        if self._status is None:
            self.poll()
        assert self._status is not None
        return self._status.confidence

    # ── Convenience helpers ────────────────────────────────────────────────

    def get_events(self) -> list[SyncEvent]:
        """Return all recorded sync / drift events."""
        return list(self._events)

    def clear_events(self) -> None:
        """Clear the event history."""
        self._events.clear()
