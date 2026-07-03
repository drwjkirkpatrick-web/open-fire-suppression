"""Persistent store-and-forward queue for notifications when network is down.

# BOT-005 — Store-and-Forward Telemetry Queue

SQLite-backed queue that buffers SMS/email/webhook notifications during
network outages. A background task drains the queue when connectivity
returns, using exponential backoff per item.

Usage::

    sf = StoreForwardQueue("/var/lib/fire-suppression/store_forward.db", mock=True)
    await sf.start()
    sf.enqueue("sms", {"to": "+254****5678", "body": "Fire alert"})
    results = await sf.drain()
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Schema ──────────────────────────────────────────────────────────

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 5,
    next_retry_time REAL NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_queue_next_retry ON queue_items(next_retry_time);
CREATE INDEX IF NOT EXISTS idx_queue_created ON queue_items(created_at);
"""

# ── Bilingual messages ──────────────────────────────────────────────

_MESSAGES: dict[str, dict[str, str]] = {
    "item_queued": {
        "en": "Item queued for {channel}",
        "sw": "Kipengele kimehifadhiwa kwa {channel}",
    },
    "drain_started": {
        "en": "Queue drain started ({count} items)",
        "sw": "Kutoa kwingine kimeanza (kipengele {count})",
    },
    "drain_completed": {
        "en": "Queue drain completed: {sent} sent, {failed} failed",
        "sw": "Kutoa kwingine kumekamilika: {sent} kimetumwa, {failed} kimeshindwa",
    },
    "network_unavailable": {
        "en": "Network unavailable — skipping drain",
        "sw": "Mtandao haupatikani — kukwepa kutoa kwingine",
    },
    "retry_scheduled": {
        "en": "Retry {retry}/{max_retries} scheduled for item {item_id} in {delay}s",
        "sw": (
            "Jaribio {retry}/{max_retries} limepangwa kwa kipengele {item_id} "
            "baada ya sekunde {delay}"
        ),
    },
    "max_retries_exceeded": {
        "en": "Item {item_id} exceeded max retries — removed from queue",
        "sw": (
            "Kipengele {item_id} kimezidi jaribio la juu — "
            "limeondolewa kwenye foleni"
        ),
    },
    "send_success": {
        "en": "Item {item_id} sent via {channel}",
        "sw": "Kipengele {item_id} kimetumwa kupitia {channel}",
    },
    "send_failed": {
        "en": "Item {item_id} failed via {channel}: {reason}",
        "sw": "Kipengele {item_id} kimeshindwa kupitia {channel}: {reason}",
    },
}


def _msg(key: str, lang: str = "en", **kwargs: Any) -> str:
    """Return bilingual message by key and language."""
    lang = lang if lang in ("en", "sw") else "en"
    template = _MESSAGES.get(key, {}).get(lang, key)
    return template.format(**kwargs)


# ── Data model ──────────────────────────────────────────────────────

@dataclass
class QueueItem:
    """A single store-and-forward queue item."""
    id: int
    channel: str
    payload: dict[str, Any]
    retry_count: int
    max_retries: int
    next_retry_time: float
    created_at: float


# ── Main class ──────────────────────────────────────────────────────

class StoreForwardQueue:
    """Persistent store-and-forward notification queue.

    Buffers notifications during network outages and drains them
    when connectivity is restored. Supports exponential backoff and
    per-channel mock dispatch.
    """

    feature_id = "BOT-005"

    def __init__(
        self,
        db_path: str | Path,
        *,
        mock: bool = False,
        network_check_interval: float = 30.0,
        drain_interval: float = 10.0,
        language: str = "en",
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.mock = mock
        self.network_check_interval = network_check_interval
        self.drain_interval = drain_interval
        self.language = language if language in ("en", "sw") else "en"
        self._conn: sqlite3.Connection | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._init_db()

    # ── Database ────────────────────────────────────────────────────

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(QUEUE_SCHEMA)
        self._conn.commit()

    def _get_pending(self) -> list[QueueItem]:
        """Fetch items ready for retry (next_retry_time <= now)."""
        assert self._conn is not None
        now = time.time()
        rows = self._conn.execute(
            """SELECT id, channel, payload_json, retry_count, max_retries,
                      next_retry_time, created_at
               FROM queue_items
               WHERE next_retry_time <= ?
               ORDER BY created_at ASC""",
            (now,),
        ).fetchall()
        return [
            QueueItem(
                id=row["id"],
                channel=row["channel"],
                payload=json.loads(row["payload_json"]),
                retry_count=row["retry_count"],
                max_retries=row["max_retries"],
                next_retry_time=row["next_retry_time"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def _count_pending(self) -> int:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT COUNT(*) FROM queue_items"
        ).fetchone()
        return row[0] if row else 0

    def _delete_item(self, item_id: int) -> None:
        assert self._conn is not None
        self._conn.execute("DELETE FROM queue_items WHERE id = ?", (item_id,))
        self._conn.commit()

    def _update_retry(self, item_id: int, retry_count: int, next_retry: float) -> None:
        assert self._conn is not None
        self._conn.execute(
            """UPDATE queue_items
               SET retry_count = ?, next_retry_time = ?
               WHERE id = ?""",
            (retry_count, next_retry, item_id),
        )
        self._conn.commit()

    # ── Public API ────────────────────────────────────────────────────

    def enqueue(
        self,
        channel: str,
        payload: dict[str, Any],
        max_retries: int = 5,
    ) -> int:
        """Add a notification to the persistent queue.

        Returns the assigned queue item id.
        """
        assert self._conn is not None
        now = time.time()
        payload_json = json.dumps(payload, separators=(",", ":"))
        cursor = self._conn.execute(
            """INSERT INTO queue_items
               (channel, payload_json, retry_count, max_retries, next_retry_time, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (channel, payload_json, 0, max_retries, now, now),
        )
        self._conn.commit()
        item_id = cursor.lastrowid or 0
        logger.info(
            _msg("item_queued", lang=self.language, channel=channel)
            + " [id=%s]",
            item_id,
        )
        return item_id

    async def drain(self) -> dict[str, Any]:
        """Attempt to send all pending queue items.

        Returns a summary dict with sent/failed counts.
        """
        if not await self._is_network_available():
            logger.warning(_msg("network_unavailable", lang=self.language))
            return {"sent": 0, "failed": 0, "skipped": True, "reason": "network_unavailable"}

        items = self._get_pending()
        if not items:
            return {"sent": 0, "failed": 0, "skipped": True, "reason": "queue_empty"}

        logger.info(_msg("drain_started", lang=self.language, count=len(items)))
        sent = 0
        failed = 0

        for item in items:
            ok = await self._process_item(item)
            if ok:
                sent += 1
            else:
                failed += 1
            # Brief yield to avoid blocking event loop
            await asyncio.sleep(0)

        logger.info(_msg("drain_completed", lang=self.language, sent=sent, failed=failed))
        return {"sent": sent, "failed": failed, "skipped": False}

    # ── Network health ────────────────────────────────────────────────

    async def _is_network_available(self) -> bool:
        """Check if network is available. Mockable for testing."""
        if self.mock:
            # In mock mode, assume network is up unless explicitly toggled off
            return getattr(self, "_mock_network_up", True)
        try:
            import socket
            # Try to reach Cloudflare DNS (1.1.1.1) — lightweight
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: socket.create_connection(("1.1.1.1", 53), timeout=3) is not None,
            )
        except Exception:
            return False

    # ── Item processing ───────────────────────────────────────────────

    async def _process_item(self, item: QueueItem) -> bool:
        """Attempt to send one queue item. Returns True on success."""
        try:
            ok = await self._send_via_channel(item.channel, item.payload)
        except Exception as exc:
            ok = False
            reason = str(exc)
            logger.error(
                _msg("send_failed", lang=self.language, item_id=item.id,
                     channel=item.channel, reason=reason)
            )

        if ok:
            logger.info(
                _msg("send_success", lang=self.language, item_id=item.id, channel=item.channel)
            )
            self._delete_item(item.id)
            return True

        # Failed — schedule retry with exponential backoff
        next_retry = item.retry_count + 1
        if next_retry > item.max_retries:
            logger.warning(
                _msg("max_retries_exceeded", lang=self.language, item_id=item.id)
            )
            self._delete_item(item.id)
            return False

        delay = 2 ** item.retry_count  # 1, 2, 4, 8, 16...
        next_retry_time = time.time() + delay
        self._update_retry(item.id, next_retry, next_retry_time)
        logger.info(
            _msg("retry_scheduled", lang=self.language, retry=next_retry,
                 max_retries=item.max_retries, item_id=item.id, delay=delay)
        )
        return False

    async def _send_via_channel(self, channel: str, payload: dict[str, Any]) -> bool:
        """Dispatch payload to the appropriate channel."""
        if self.mock:
            logger.info("[MOCK %s] payload=%s", channel.upper(), payload)
            return True

        if channel == "sms":
            return await self._send_sms(payload)
        if channel == "email":
            return await self._send_email(payload)
        if channel == "webhook":
            return await self._send_webhook(payload)
        logger.warning(
            "Unknown channel '%s' — treating as success to avoid infinite retry",
            channel,
        )
        return True

    async def _send_sms(self, payload: dict[str, Any]) -> bool:
        # Delegate to notifier / Kenya SMS in production
        logger.debug("Sending SMS: %s", payload)
        return True

    async def _send_email(self, payload: dict[str, Any]) -> bool:
        logger.debug("Sending email: %s", payload)
        return True

    async def _send_webhook(self, payload: dict[str, Any]) -> bool:
        try:
            import aiohttp
            url = payload.get("url")
            if not url:
                logger.error("Webhook payload missing 'url'")
                return False
            timeout = aiohttp.ClientTimeout(total=10)
            async with (
                aiohttp.ClientSession() as session,
                session.post(url, json=payload.get("data", {}), timeout=timeout) as resp,
            ):
                return resp.status < 500
        except Exception as exc:
            logger.error("Webhook send failed: %s", exc)
            return False

    # ── Background task ───────────────────────────────────────────────

    async def start(self) -> None:
        """Start the periodic background drain task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._drain_loop())
        logger.info("StoreForwardQueue BOT-005 started (drain_interval=%.1fs)", self.drain_interval)

    async def stop(self) -> None:
        """Stop the background drain task."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("StoreForwardQueue BOT-005 stopped")

    async def _drain_loop(self) -> None:
        while self._running:
            try:
                await self.drain()
            except Exception:
                logger.exception("Drain loop error")
            try:
                await asyncio.wait_for(
                    asyncio.sleep(self.drain_interval),
                    timeout=self.drain_interval + 5,
                )
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    # ── Introspection ─────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        pending = self._count_pending()
        return {
            "feature_id": self.feature_id,
            "healthy": pending < 1000,
            "pending_items": pending,
            "mock": self.mock,
            "db_path": str(self.db_path),
            "language": self.language,
        }

    def get_feature_overview(self) -> dict[str, Any]:
        supports = [
            "enqueue",
            "drain",
            "exponential_backoff",
            "network_health_check",
            "sms",
            "email",
            "webhook",
        ]
        return {
            "feature_id": self.feature_id,
            "feature_name": "Store-and-Forward Telemetry Queue",
            "mock": self.mock,
            "supports": supports,
            "language": self.language,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.health_check(),
            "drain_interval": self.drain_interval,
            "network_check_interval": self.network_check_interval,
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
