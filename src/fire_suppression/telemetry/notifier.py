"""Multi-channel alert notification system.

# IMP-003 — Cellular/WiFi Alert Notification System

Supports local buzzer, SMS (via Twilio), email (SMTP), and generic webhook.
Queue-based with retry logic and rate limiting.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from fire_suppression.alerts.quiet_hours import QuietHoursScheduler
from fire_suppression.telemetry.acknowledgment_manager import AcknowledgmentManager

logger = logging.getLogger(__name__)


class NotificationLevel(Enum):
    """Priority level for notifications."""
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"


@dataclass
class Notification:
    """A single notification to be sent."""
    level: NotificationLevel
    title: str
    message: str
    timestamp: float
    retry_count: int = 0


class AlertNotifier:
    """Multi-channel alert notification system.

    Usage::

        notifier = AlertNotifier()
        notifier.send(NotificationLevel.ALERT, "FIRE DETECTED", "Smoke + Temp confirmed")
    """

    def __init__(
        self,
        channels: list[str] | None = None,
        sms_config: dict | None = None,
        email_config: dict | None = None,
        webhook_url: str | None = None,
        quiet_hours: QuietHoursScheduler | None = None,
        ack_manager: AcknowledgmentManager | None = None,
        *,
        mock: bool = False,
    ) -> None:
        self.channels = channels or ["buzzer"]
        self.sms_config = sms_config or {}
        self.email_config = email_config or {}
        self.webhook_url = webhook_url
        self.mock = mock
        self._quiet_hours = quiet_hours or QuietHoursScheduler()
        self._ack_manager = ack_manager
        self._queue: asyncio.Queue[Notification] = asyncio.Queue()
        self._last_sent: dict[str, float] = {}  # Rate limiting per channel
        self._rate_limit_seconds = 60  # Min seconds between same-level notifications
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the notification dispatch loop."""
        self._running = True
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info("Alert notifier started with channels: %s", self.channels)

    async def stop(self) -> None:
        """Stop the notification dispatch loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def send(self, level: NotificationLevel, title: str, message: str, alert_id: str | None = None) -> None:
        """Queue a notification for dispatch.

        Critical/Alert notifications may require acknowledgment. If an
        acknowledgment manager is configured, critical/alert messages are
        registered for escalation when unacknowledged.
        """
        # Quiet-hours gate: non-critical messages are held during rest windows.
        if self._quiet_hours.should_suppress(level.value):
            logger.info("Quiet-hours suppressed %s notification: %s", level.value, title)
            return

        notif = Notification(level=level, title=title, message=message, timestamp=time.time())

        # Register critical and alert-level notifications for acknowledgment.
        if self._ack_manager and level in (NotificationLevel.CRITICAL, NotificationLevel.ALERT):
            self._ack_manager.register_alert(
                alert_id or f"{title}-{notif.timestamp:.0f}",
                message,
                severity=level.value,
            )

        self._queue.put_nowait(notif)
        logger.debug("Notification queued: %s - %s", level.value, title)

    def acknowledge(self, alert_id: str, user: str = "owner") -> bool:
        """Acknowledge an alert, stopping its escalation."""
        if self._ack_manager is None:
            return False
        return self._ack_manager.acknowledge(alert_id, user=user)

    async def _dispatch_loop(self) -> None:
        """Process notification queue continuously."""
        while self._running:
            try:
                notification = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            await self._dispatch(notification)

    async def _dispatch(self, notification: Notification) -> None:
        """Dispatch a notification to all configured channels."""
        tasks = []
        for channel in self.channels:
            # Rate limiting
            key = f"{channel}_{notification.level.value}"
            last = self._last_sent.get(key, 0)
            if time.time() - last < self._rate_limit_seconds and notification.level != NotificationLevel.CRITICAL:
                logger.debug("Rate limited: %s", key)
                continue

            if channel == "buzzer":
                tasks.append(self._send_buzzer(notification))
            elif channel == "sms":
                tasks.append(self._send_sms(notification))
            elif channel == "email":
                tasks.append(self._send_email(notification))
            elif channel == "webhook":
                tasks.append(self._send_webhook(notification))

            self._last_sent[key] = time.time()

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for channel, result in zip(self.channels, results):
                if isinstance(result, Exception):
                    logger.error("Notification to %s failed: %s", channel, result)
                    notification.retry_count += 1
                    if notification.retry_count < 3:
                        await asyncio.sleep(2 ** notification.retry_count)
                        self._queue.put_nowait(notification)

    async def _send_buzzer(self, notification: Notification) -> None:
        """Trigger local buzzer alert pattern."""
        if self.mock:
            logger.info("[MOCK BUZZER] %s: %s", notification.title, notification.message)
            return
        try:
            from gpiozero import OutputDevice
            buzzer = OutputDevice(20, active_high=True)
            # Alert pattern: 3 short beeps for warning, continuous for critical
            if notification.level == NotificationLevel.CRITICAL:
                buzzer.on()
                await asyncio.sleep(5.0)
                buzzer.off()
            else:
                for _ in range(3):
                    buzzer.on()
                    await asyncio.sleep(0.2)
                    buzzer.off()
                    await asyncio.sleep(0.2)
        except Exception as exc:
            logger.error("Buzzer alert failed: %s", exc)

    async def _send_sms(self, notification: Notification) -> None:
        """Send SMS via Twilio API."""
        if self.mock:
            logger.info("[MOCK SMS] %s: %s", notification.title, notification.message)
            return
        try:
            from twilio.rest import Client
            client = Client(
                self.sms_config.get("account_sid"),
                self.sms_config.get("auth_token"),
            )
            message = client.messages.create(
                body=f"[{notification.level.value.upper()}] {notification.title}: {notification.message}",
                from_=self.sms_config.get("from_number"),
                to=self.sms_config.get("to_number"),
            )
            logger.info("SMS sent: %s", message.sid)
        except Exception as exc:
            logger.error("SMS send failed: %s", exc)

    async def _send_email(self, notification: Notification) -> None:
        """Send email via SMTP."""
        if self.mock:
            logger.info("[MOCK EMAIL] %s: %s", notification.title, notification.message)
            return
        try:
            import smtplib
            from email.mime.text import MIMEText

            msg = MIMEText(notification.message)
            msg["Subject"] = f"[{notification.level.value.upper()}] {notification.title}"
            msg["From"] = self.email_config.get("from")
            msg["To"] = self.email_config.get("to")

            with smtplib.SMTP(self.email_config.get("host", "localhost"),
                              self.email_config.get("port", 587)) as server:
                if self.email_config.get("use_tls"):
                    server.starttls()
                if self.email_config.get("username"):
                    server.login(self.email_config["username"], self.email_config["password"])
                server.send_message(msg)
            logger.info("Email sent to %s", self.email_config.get("to"))
        except Exception as exc:
            logger.error("Email send failed: %s", exc)

    async def _send_webhook(self, notification: Notification) -> None:
        """Send HTTP POST to configured webhook URL."""
        if self.mock or not self.webhook_url:
            logger.info("[MOCK WEBHOOK] %s: %s", notification.title, notification.message)
            return
        try:
            import aiohttp
            payload = {
                "level": notification.level.value,
                "title": notification.title,
                "message": notification.message,
                "timestamp": notification.timestamp,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status >= 400:
                        logger.warning("Webhook returned %d", resp.status)
                    else:
                        logger.info("Webhook sent successfully")
        except Exception as exc:
            logger.error("Webhook send failed: %s", exc)
