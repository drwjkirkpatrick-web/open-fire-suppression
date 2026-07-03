"""Tests for the RTC/NTP sync module.

# BOT-009 — RTC/NTP Sync Tests
"""
import time
from pathlib import Path

import pytest

from fire_suppression.diagnostics.rtc_sync import (
    NtpSyncMethod,
    RtcSyncMonitor,
    SyncEvent,
    TimeStatus,
    TimestampConfidence,
)


class TestRtcSyncMonitor:
    """# BOT-009 — RTC/NTP Sync"""

    def test_init_defaults(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        assert mon.drift_threshold_s == 5.0
        assert mon.auto_sync is True
        assert mon.mock is True
        assert mon.feature_id == "BOT-009"
        assert mon.lang == "en"

    def test_init_custom(self) -> None:
        mon = RtcSyncMonitor(
            bus_number=3,
            drift_threshold_s=10.0,
            auto_sync=False,
            mock=True,
            lang="sw",
        )
        assert mon.bus_number == 3
        assert mon.drift_threshold_s == 10.0
        assert mon.auto_sync is False
        assert mon.lang == "sw"

    def test_read_rtc_mock(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        rtc = mon.read_rtc()
        assert rtc is not None
        # Mock RTC should be close to now + 3s offset
        assert abs(time.mktime(rtc) - (time.time() + 3.0)) < 2.0

    def test_check_ntp_status_mock(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        synced, method = mon.check_ntp_status()
        assert synced is False
        assert method == NtpSyncMethod.UNKNOWN

    def test_attempt_ntp_sync_mock(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        result = mon.attempt_ntp_sync()
        assert result is True

    def test_poll_creates_status(self) -> None:
        mon = RtcSyncMonitor(mock=True, drift_threshold_s=60.0)
        status = mon.poll()
        assert isinstance(status, TimeStatus)
        assert status.ntp_synced is False
        assert status.confidence == TimestampConfidence.MEDIUM  # RTC only
        assert status.rtc_time is not None
        # Mock drift is ~3s, within 60s threshold
        assert status.drift_seconds < 60.0

    def test_poll_drift_alert(self) -> None:
        mon = RtcSyncMonitor(mock=True, drift_threshold_s=1.0)
        mon.poll()
        events = mon.get_events()
        # With mock threshold=1s, drift ~3s should trigger drift_alert
        drift_events = [e for e in events if e.event_type == "drift_alert"]
        assert len(drift_events) >= 1
        assert "drift" in drift_events[0].details_en.lower()

    def test_health_check(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        health = mon.health_check()
        assert isinstance(health, dict)
        assert "healthy" in health
        assert "ntp_synced" in health
        assert "rtc_available" in health
        assert "confidence" in health
        assert health["mock"] is True

    def test_get_feature_overview(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        overview = mon.get_feature_overview()
        assert overview["feature_id"] == "BOT-009"
        assert overview["feature_name"] == "RTC/NTP Sync"
        assert "supports" in overview
        assert "ds3231_i2c_read" in overview["supports"]
        assert "bilingual_messages" in overview["supports"]

    def test_to_dict(self) -> None:
        mon = RtcSyncMonitor(mock=True, drift_threshold_s=60.0)
        d = mon.to_dict()
        assert d["feature_id"] == "BOT-009"
        assert d["feature_name"] == "RTC/NTP Sync"
        assert "latest_status" in d
        assert d["latest_status"]["confidence"] in {"high", "medium", "low"}
        assert "events" in d

    def test_get_timestamp_confidence(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        conf = mon.get_timestamp_confidence()
        assert conf == TimestampConfidence.MEDIUM

    def test_get_timestamp_confidence_polls_once(self) -> None:
        mon = RtcSyncMonitor(mock=True)
        assert mon._status is None
        _ = mon.get_timestamp_confidence()
        assert mon._status is not None

    def test_clear_events(self) -> None:
        mon = RtcSyncMonitor(mock=True, drift_threshold_s=1.0)
        mon.poll()
        assert len(mon.get_events()) > 0
        mon.clear_events()
        assert len(mon.get_events()) == 0

    def test_time_status_to_dict(self) -> None:
        ts = TimeStatus(
            system_time=1700000000.0,
            rtc_time=1700000003.0,
            drift_seconds=3.0,
            ntp_synced=False,
            ntp_method=NtpSyncMethod.UNKNOWN,
            confidence=TimestampConfidence.MEDIUM,
            message_en="ok",
            message_sw="sawa",
        )
        d = ts.to_dict()
        assert d["system_time"] == 1700000000.0
        assert d["ntp_method"] == "unknown"
        assert d["confidence"] == "medium"
        assert d["message_sw"] == "sawa"

    def test_sync_event_to_dict(self) -> None:
        ev = SyncEvent(
            timestamp=1700000000.0,
            event_type="drift_alert",
            details_en="drift detected",
            details_sw="kutofautiana kimegunduliwa",
        )
        d = ev.to_dict()
        assert d["event_type"] == "drift_alert"
        assert d["details_sw"] == "kutofautiana kimegunduliwa"

    def test_bcd_helpers(self) -> None:
        from fire_suppression.diagnostics.rtc_sync import (
            _bcd_to_int,
            _int_to_bcd,
            _parse_ds3231_hour,
        )

        assert _bcd_to_int(0x42) == 42
        assert _int_to_bcd(42) == 0x42
        # 24-hour mode: 0x19 = 19
        assert _parse_ds3231_hour(0x19) == 19
        # 12-hour PM: 0x72 = 12 PM
        assert _parse_ds3231_hour(0x72) == 12

    def test_run_cmd_not_found(self) -> None:
        rc, out, err = RtcSyncMonitor._run_cmd(["/bin/false_xyz"], timeout=1.0)
        # Should fail because command does not exist
        assert rc != 0
