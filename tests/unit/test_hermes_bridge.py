"""Tests for Hermes bridge.

# HBR-001 — HBR-003
"""
import asyncio

import pytest

from fire_suppression.bridge.hermes_bridge import HermesBridge


class TestHermesBridge:
    @pytest.mark.asyncio
    async def test_mock_connect(self, tmp_path) -> None:
        bridge = HermesBridge(mock=True, status_file=tmp_path / "status.json")
        await bridge.connect()
        assert bridge._running is True
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_send_fire_alert(self, tmp_path) -> None:
        bridge = HermesBridge(mock=True, status_file=tmp_path / "status.json")
        await bridge.connect()
        from fire_suppression.detection.engine import DetectionResult, FireState
        result = DetectionResult(FireState.ALERT, 0.85, "test")
        await bridge.send_fire_alert(result, {"mq2": 150})
        await asyncio.sleep(0.3)
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_send_humidity_alert(self, tmp_path) -> None:
        bridge = HermesBridge(mock=True, status_file=tmp_path / "status.json")
        await bridge.connect()
        from fire_suppression.sensors.base import SensorReading
        reading = SensorReading("sht40", 0, {"humidity_percent": 8.0})
        await bridge.send_humidity_alert(reading, 15.0, zone="kitchen")
        await asyncio.sleep(0.3)
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_send_status_report(self, tmp_path) -> None:
        bridge = HermesBridge(mock=True, status_file=tmp_path / "status.json")
        await bridge.connect()
        await bridge.send_status_report(
            {"armed": True, "fire_state": "clear"},
        )
        status = bridge.get_last_status()
        assert status["system"]["armed"] is True
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_send_error(self, tmp_path) -> None:
        bridge = HermesBridge(mock=True, status_file=tmp_path / "status.json")
        await bridge.connect()
        await bridge.send_error("mq2", "sensor timeout")
        await asyncio.sleep(0.3)
        await bridge.disconnect()

    @pytest.mark.asyncio
    async def test_heartbeat(self, tmp_path) -> None:
        bridge = HermesBridge(mock=True, status_file=tmp_path / "status.json")
        await bridge.connect()
        await bridge.send_heartbeat()
        await asyncio.sleep(0.3)
        await bridge.disconnect()
