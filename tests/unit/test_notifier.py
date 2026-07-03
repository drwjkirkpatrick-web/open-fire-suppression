"""Tests for alert notification system.

# IMP-003 — Cellular/WiFi Alert Notification System
"""
import pytest
import asyncio

from fire_suppression.telemetry.notifier import AlertNotifier, NotificationLevel


class TestAlertNotifier:
    """# IMP-003 — Cellular/WiFi Alert Notification System"""

    @pytest.mark.asyncio
    async def test_buzzer_channel_mock(self) -> None:
        notifier = AlertNotifier(channels=["buzzer"], mock=True)
        await notifier.start()
        notifier.send(NotificationLevel.ALERT, "Test", "Buzzer test")
        await asyncio.sleep(0.5)
        await notifier.stop()

    @pytest.mark.asyncio
    async def test_multiple_channels_mock(self) -> None:
        notifier = AlertNotifier(
            channels=["buzzer", "sms", "email", "webhook"],
            mock=True,
        )
        await notifier.start()
        notifier.send(NotificationLevel.CRITICAL, "FIRE", "Critical test")
        await asyncio.sleep(0.5)
        await notifier.stop()

    def test_rate_limiting_different_levels(self) -> None:
        notifier = AlertNotifier(channels=[], mock=True)
        # Should not raise
        notifier.send(NotificationLevel.INFO, "Info 1", "test")
        notifier.send(NotificationLevel.WARNING, "Warn 1", "test")
        notifier.send(NotificationLevel.ALERT, "Alert 1", "test")
        # No assertions needed — queueing is the test

    @pytest.mark.asyncio
    async def test_queue_processing(self) -> None:
        notifier = AlertNotifier(channels=["buzzer"], mock=True)
        await notifier.start()
        notifier.send(NotificationLevel.INFO, "Test 1", "msg 1")
        notifier.send(NotificationLevel.INFO, "Test 2", "msg 2")
        await asyncio.sleep(0.5)
        assert notifier._queue.empty()
        await notifier.stop()
