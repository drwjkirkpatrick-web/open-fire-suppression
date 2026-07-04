"""V9-002 — Acknowledgment-required Alerts with Escalation

Critical alerts must be acknowledged. If nobody acknowledges the alert within a
configurable timeout, the system escalates to SMS and voice using the
"Aconitum Napellus" remedy personality: urgent, relentless, and impossible to
ignore until someone takes responsibility.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class PendingAck:
    """A critical alert awaiting owner acknowledgment."""

    alert_id: str
    message: str
    severity: str
    created_at: float
    acknowledged_at: float | None = None
    escalated_at: float | None = None
    resolved: bool = False


AckHandler = Callable[[str], Coroutine[Any, Any, None]]


class AcknowledgmentManager:
    """Tracks critical alerts and escalates if not acknowledged in time.

    Default personality: *Aconitum Napellus* — the panic responder. The tone
    is sharp, immediate, and repeated until a human acknowledges.
    """

    def __init__(
        self,
        escalation_handler: AckHandler | None = None,
        escalation_timeout_seconds: float = 300.0,
        max_escalations: int = 3,
        personality: str = "Aconitum Napellus",
    ) -> None:
        self._pending: dict[str, PendingAck] = {}
        self._escalation_handler = escalation_handler
        self._escalation_timeout = escalation_timeout_seconds
        self._max_escalations = max_escalations
        self.personality = personality
        self._background_task: asyncio.Task | None = None

    def register_alert(
        self,
        alert_id: str,
        message: str,
        severity: str = "critical",
    ) -> PendingAck:
        """Record a new alert that requires acknowledgment."""
        if alert_id in self._pending:
            logger.debug("Alert %s already tracked for acknowledgment", alert_id)
            return self._pending[alert_id]
        ack = PendingAck(
            alert_id=alert_id,
            message=message,
            severity=severity,
            created_at=time.time(),
        )
        self._pending[alert_id] = ack
        logger.warning(
            "ACK REQUIRED: alert %s registered (%s personality)",
            alert_id,
            self.personality,
        )
        return ack

    def acknowledge(self, alert_id: str, user: str = "owner") -> bool:
        """Mark an alert as acknowledged by a human operator."""
        ack = self._pending.get(alert_id)
        if ack is None or ack.acknowledged_at is not None:
            return False
        ack.acknowledged_at = time.time()
        ack.resolved = True
        logger.info("Alert %s acknowledged by %s", alert_id, user)
        return True

    def resolve(self, alert_id: str) -> bool:
        """Mark an alert resolved without requiring an explicit ack."""
        ack = self._pending.get(alert_id)
        if ack is None:
            return False
        ack.resolved = True
        return True

    def needs_acknowledgment(self, alert_id: str) -> bool:
        """True if this alert is still awaiting a human response."""
        ack = self._pending.get(alert_id)
        return ack is not None and ack.acknowledged_at is None and not ack.resolved

    def get_pending(self) -> list[PendingAck]:
        """Return all alerts still awaiting acknowledgment."""
        return [
            a for a in self._pending.values()
            if a.acknowledged_at is None and not a.resolved
        ]

    def get_escalation_candidates(self) -> list[PendingAck]:
        """Return alerts that have passed the escalation timeout."""
        now = time.time()
        return [
            a for a in self.get_pending()
            if (a.escalated_at is None or (now - a.escalated_at) > self._escalation_timeout)
            and (now - a.created_at) > self._escalation_timeout
        ]

    async def run_escalation_loop(self) -> None:
        """Background loop that escalates unacknowledged critical alerts."""
        while True:
            await asyncio.sleep(15)
            candidates = self.get_escalation_candidates()
            for ack in candidates:
                if ack.escalated_at is not None:
                    count = int((time.time() - ack.created_at) // self._escalation_timeout)
                    if count > self._max_escalations:
                        continue
                ack.escalated_at = time.time()
                logger.critical(
                    "ESCALATING unacknowledged alert %s (%s)",
                    ack.alert_id,
                    self.personality,
                )
                if self._escalation_handler:
                    try:
                        await self._escalation_handler(ack.alert_id)
                    except Exception as exc:
                        logger.error("Escalation handler failed for %s: %s", ack.alert_id, exc)

    def start(self) -> None:
        """Start the background escalation watcher."""
        if self._background_task is None or self._background_task.done():
            self._background_task = asyncio.create_task(self.run_escalation_loop())
            logger.info("AcknowledgmentManager escalation loop started")

    async def stop(self) -> None:
        """Stop the background escalation watcher."""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            logger.info("AcknowledgmentManager escalation loop stopped")

    def to_dict(self) -> dict[str, Any]:
        now = time.time()
        pending = self.get_pending()
        return {
            "personality": self.personality,
            "escalation_timeout_seconds": self._escalation_timeout,
            "pending_count": len(pending),
            "pending": [
                {
                    "alert_id": a.alert_id,
                    "message": a.message,
                    "severity": a.severity,
                    "waiting_seconds": round(now - a.created_at, 1),
                    "escalated": a.escalated_at is not None,
                }
                for a in pending
            ],
        }
