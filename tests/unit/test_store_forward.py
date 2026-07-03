"""Tests for store-and-forward persistent queue.

# BOT-005 — Store-and-Forward Telemetry Queue
"""
import asyncio
from pathlib import Path

import pytest

from fire_suppression.telemetry.store_forward import StoreForwardQueue, _msg


class TestStoreForwardQueue:
    """# BOT-005 — Store-and-Forward Telemetry Queue"""

    # ── Basic lifecycle ─────────────────────────────────────────────

    def test_init(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        assert sf.mock is True
        assert sf.feature_id == "BOT-005"
        sf.close()

    def test_enqueue_and_count(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        item_id = sf.enqueue("sms", {"to": "+254****5678", "body": "Fire!"})
        assert isinstance(item_id, int)
        assert sf._count_pending() == 1
        sf.close()

    def test_enqueue_multiple_channels(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        sf.enqueue("sms", {"to": "+254****5678", "body": "Fire!"})
        sf.enqueue("email", {"to": "admin@example.com", "subject": "Alert"})
        sf.enqueue("webhook", {"url": "https://example.com/hook", "data": {"x": 1}})
        assert sf._count_pending() == 3
        sf.close()

    # ── Drain / network ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_drain_empty_queue(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        result = await sf.drain()
        assert result["skipped"] is True
        assert result["sent"] == 0
        sf.close()

    @pytest.mark.asyncio
    async def test_drain_sends_pending_items(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        sf.enqueue("sms", {"to": "+254****5678", "body": "Fire!"})
        sf.enqueue("webhook", {"url": "https://example.com/hook", "data": {}})
        result = await sf.drain()
        assert result["skipped"] is False
        assert result["sent"] == 2
        assert result["failed"] == 0
        assert sf._count_pending() == 0
        sf.close()

    @pytest.mark.asyncio
    async def test_drain_network_down(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        sf._mock_network_up = False  # type: ignore[attr-defined]
        sf.enqueue("sms", {"to": "+254****5678", "body": "Fire!"})
        result = await sf.drain()
        assert result["skipped"] is True
        assert result["reason"] == "network_unavailable"
        assert sf._count_pending() == 1
        sf.close()

    # ── Retry / backoff ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_retry_exceeds_max_retries(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        # Force _send_via_channel to always fail by overriding it
        async def _fail(*args, **kwargs) -> bool:
            return False
        sf._send_via_channel = _fail  # type: ignore[method-assign]
        sf.enqueue("sms", {"to": "+254****5678", "body": "Fire!"}, max_retries=0)
        result = await sf.drain()
        # With max_retries=0 the item is removed immediately after first failure
        assert result["failed"] == 1
        assert sf._count_pending() == 0
        sf.close()

    @pytest.mark.asyncio
    async def test_retry_backoff_updates_next_retry_time(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        call_count = 0

        async def _fail_once(*args, **kwargs) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count > 1

        sf._send_via_channel = _fail_once  # type: ignore[method-assign]
        sf.enqueue("sms", {"to": "+254****5678", "body": "Fire!"}, max_retries=3)

        # First drain — fails, schedules retry for 1s in the future
        result = await sf.drain()
        assert result["failed"] == 1
        assert sf._count_pending() == 1

        # Advance time past retry window so item is pending again
        import time
        time.sleep(1.1)
        result2 = await sf.drain()
        assert result2["sent"] == 1
        assert sf._count_pending() == 0
        sf.close()

    # ── Bilingual ───────────────────────────────────────────────────

    def test_bilingual_messages(self) -> None:
        en = _msg("network_unavailable", lang="en")
        sw = _msg("network_unavailable", lang="sw")
        assert "Network unavailable" in en
        assert "Mtandao haupatikani" in sw

    # ── Overview / dict ─────────────────────────────────────────────

    def test_health_check(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        hc = sf.health_check()
        assert hc["feature_id"] == "BOT-005"
        assert hc["healthy"] is True
        assert hc["pending_items"] == 0
        sf.close()

    def test_get_feature_overview(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True, language="sw")
        overview = sf.get_feature_overview()
        assert overview["feature_id"] == "BOT-005"
        assert "exponential_backoff" in overview["supports"]
        assert overview["language"] == "sw"
        sf.close()

    def test_to_dict(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True)
        d = sf.to_dict()
        assert "feature_id" in d
        assert "drain_interval" in d
        sf.close()

    # ── Background task ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_start_stop_background_task(self, tmp_path: Path) -> None:
        sf = StoreForwardQueue(tmp_path / "sf.db", mock=True, drain_interval=0.1)
        await sf.start()
        await asyncio.sleep(0.15)  # Let at least one loop iteration run
        await sf.stop()
        assert sf._running is False
        assert sf._task is None
        sf.close()
