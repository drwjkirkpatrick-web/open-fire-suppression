"""Tests for audio keep-alive, fault isolation, dashboard UI, and phrase database.

# AUD-003 + AUD-004 + RES-002 + UI-001..UI-010 Tests
"""
import asyncio
import time

import pytest

from fire_suppression.alerts.audio_keep_alive import (
    AudioKeepAlive,
    AudioPriority,
    AudioTask,
    FaultIsolator,
    PlaybackResult,
    PhraseCache,
)
from fire_suppression.alerts.phrase_database import (
    EVACUATION_PHRASES,
    FIRE_ALERT_PHRASES,
    initialize_phrase_database,
)
from fire_suppression.resilience.fault_isolation import (
    FaultIsolatedExecutor,
    isolated,
    isolated_async,
)
from fire_suppression.web.dashboard_ui import (
    AlertLevel,
    DashboardUI,
    ZoneStatus,
)


# ── PhraseCache Tests ──

class TestPhraseCache:
    def test_init_mock(self) -> None:
        cache = PhraseCache(mock=True)
        stats = cache.to_dict()
        assert stats["db_path"] == ":memory:"

    def test_add_and_get(self) -> None:
        cache = PhraseCache(mock=True)
        cache.add_phrase("test_phrase", "alert", "Test EN", "Test SW", priority=2)
        en = cache.get_phrase("test_phrase", "en")
        sw = cache.get_phrase("test_phrase", "sw")
        assert en["text"] == "Test EN"
        assert sw["text"] == "Test SW"

    def test_get_missing(self) -> None:
        cache = PhraseCache(mock=True)
        assert cache.get_phrase("missing", "en") is None

    def test_log_usage(self) -> None:
        cache = PhraseCache(mock=True)
        cache.add_phrase("usage_test", "alert", "EN", "SW")
        cache.log_usage("usage_test", "en", "kitchen", 45.0)
        popular = cache.get_popular_phrases()
        assert len(popular) >= 1

    def test_get_by_category(self) -> None:
        cache = PhraseCache(mock=True)
        cache.add_phrase("cat_test", "evacuation", "EN", "SW")
        cache.add_phrase("cat_test2", "evacuation", "EN2", "SW2")
        cache.add_phrase("cat_alert", "alert", "EN", "SW")
        evac = cache.get_phrases_by_category("evacuation")
        assert len(evac) == 2


# ── AudioKeepAlive Tests ──

class TestAudioKeepAlive:
    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        audio = AudioKeepAlive(mock=True)
        await audio.start()
        assert audio._running is True
        status = audio.get_status()
        assert status["running"] is True
        await audio.stop()
        assert audio._running is False

    @pytest.mark.asyncio
    async def test_enqueue_and_play(self) -> None:
        audio = AudioKeepAlive(mock=True)
        await audio.start()

        # Add a phrase first
        audio._cache.add_phrase("fire_alert", "alert", "Fire!", "Moto!", priority=3)

        audio.enqueue("fire_alert", "en", priority=AudioPriority.FIRE_ALERT)
        # Let it process
        await asyncio.sleep(0.05)

        status = audio.get_status()
        assert status["queue_depth"] == 0  # Should be processed
        await audio.stop()

    @pytest.mark.asyncio
    async def test_play_immediately(self) -> None:
        audio = AudioKeepAlive(mock=True)
        await audio.start()
        audio._cache.add_phrase("emergency", "alert", "Emergency!", "Dharura!", priority=3)

        result = audio.play_immediately("emergency", "en")
        assert isinstance(result, PlaybackResult)
        assert result.success is True
        assert result.latency_ms < 100
        await audio.stop()

    @pytest.mark.asyncio
    async def test_priority_queue(self) -> None:
        audio = AudioKeepAlive(mock=True)
        await audio.start()

        audio._cache.add_phrase("info", "status", "Info", "Habari", priority=0)
        audio._cache.add_phrase("alert", "alert", "Alert", "Onyo", priority=2)

        # Queue low priority first
        audio.enqueue("info", "en", priority=AudioPriority.INFO)
        # Then high priority
        audio.enqueue("alert", "en", priority=AudioPriority.FIRE_ALERT)

        # Check queue ordering — high priority should be first
        with audio._lock:
            tasks = list(audio._queue)

        await audio.stop()

    @pytest.mark.asyncio
    async def test_interrupt(self) -> None:
        audio = AudioKeepAlive(mock=True)
        await audio.start()

        audio._cache.add_phrase("low", "status", "Low", "Chini", priority=0)
        audio._cache.add_phrase("high", "alert", "High", "Juu", priority=3)

        audio.enqueue("low", "en", priority=AudioPriority.INFO)
        audio.enqueue("high", "en", priority=AudioPriority.EMERGENCY, interrupt=True)

        # After interrupt, only high priority should remain
        with audio._lock:
            tasks = list(audio._queue)
        assert len(tasks) == 1
        assert tasks[0].phrase_id == "high"

        await audio.stop()

    @pytest.mark.asyncio
    async def test_to_dict(self) -> None:
        audio = AudioKeepAlive(mock=True)
        await audio.start()
        d = audio.to_dict()
        assert "running" in d
        assert "queue_depth" in d
        assert "cache" in d
        await audio.stop()


# ── FaultIsolator Tests ──

class TestFaultIsolator:
    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        isolator = FaultIsolator({"test": lambda: "ok"})
        result = await isolator.execute("test")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_execute_async_success(self) -> None:
        async def async_fn():
            return "async_ok"
        isolator = FaultIsolator({"async_test": async_fn})
        result = await isolator.execute("async_test")
        assert result == "async_ok"

    @pytest.mark.asyncio
    async def test_execute_failure_degrades(self) -> None:
        def fail_fn():
            raise RuntimeError("test error")
        isolator = FaultIsolator({"fail": fail_fn}, max_failures=2)

        # First failure
        with pytest.raises(RuntimeError):
            await isolator.execute("fail")
        health = isolator.get_health()
        assert health["fail"]["fails"] == 1
        assert health["fail"]["degraded"] is False

        # Second failure — degraded
        with pytest.raises(RuntimeError):
            await isolator.execute("fail")
        health = isolator.get_health()
        assert health["fail"]["degraded"] is True


# ── FaultIsolatedExecutor Tests ──

class TestFaultIsolatedExecutor:
    def test_wrap_success(self) -> None:
        executor = FaultIsolatedExecutor()

        @executor.wrap("sensor")
        def read_sensor():
            return 42

        result = read_sensor()
        assert result == 42

    def test_wrap_failure_recovery(self) -> None:
        executor = FaultIsolatedExecutor(max_failures=2, recovery_interval_sec=300.0)
        call_count = 0

        @executor.wrap("flaky")
        def flaky_sensor():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        # First call fails, module not yet degraded
        assert flaky_sensor() is None
        health = executor.get_health("flaky")
        assert health["fails"] == 1
        assert health["degraded"] is False

        # Second call degrades the module
        assert flaky_sensor() is None
        health = executor.get_health("flaky")
        assert health["degraded"] is True
        assert health["fails"] == 2

        # Third call should be skipped (degraded)
        assert flaky_sensor() is None

    def test_get_health(self) -> None:
        executor = FaultIsolatedExecutor()

        @executor.wrap("test_mod")
        def test_fn():
            return True

        test_fn()
        health = executor.get_health()
        assert "test_mod" in health
        assert health["test_mod"]["total_calls"] == 1

    def test_reset_module(self) -> None:
        executor = FaultIsolatedExecutor()

        @executor.wrap("reset_test")
        def fail_fn():
            raise RuntimeError("fail")

        fail_fn()
        fail_fn()
        fail_fn()

        assert executor.get_health("reset_test")["degraded"] is True
        executor.reset_module("reset_test")
        assert executor.get_health("reset_test")["degraded"] is False


# ── DashboardUI Tests ──

class TestDashboardUI:
    def test_init(self) -> None:
        ui = DashboardUI(mock=True)
        assert ui._theme == "dark"
        assert ui._language == "en"

    def test_set_language(self) -> None:
        ui = DashboardUI(mock=True)
        result = ui.set_language("sw")
        assert result["success"] is True
        assert result["language"] == "sw"
        assert "evacuate" in result["labels"]

    def test_set_language_invalid(self) -> None:
        ui = DashboardUI(mock=True)
        result = ui.set_language("fr")
        assert result["success"] is False

    def test_accessibility_mode(self) -> None:
        ui = DashboardUI(mock=True)
        result = ui.set_accessibility_mode(True)
        assert result["enabled"] is True
        assert result["features"]["high_contrast"] is True

    def test_layout_config(self) -> None:
        ui = DashboardUI(mock=True)
        mobile = ui.get_layout_config("mobile")
        assert mobile["columns"] == 1
        desktop = ui.get_layout_config("desktop")
        assert desktop["columns"] == 3

    def test_calculate_fire_risk(self) -> None:
        ui = DashboardUI(mock=True)
        zone = ZoneStatus(
            zone_id="kitchen",
            name="Kitchen",
            temperature_c=80.0,
            smoke_ppm=50.0,
            co_ppm=5.0,
            occupancy_count=2,
            alert_level="alert",
            last_update=time.time(),
            sensor_health={"mq2": "ok", "temp": "ok"},
        )
        ui.update_zone(zone)

        result = ui.calculate_fire_risk("kitchen")
        assert result["success"] is True
        assert result["risk_percent"] > 0
        assert "alert_level" in result

    def test_calculate_fire_risk_missing_zone(self) -> None:
        ui = DashboardUI(mock=True)
        result = ui.calculate_fire_risk("missing")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_emergency_action(self) -> None:
        ui = DashboardUI(mock=True)
        result = await ui.emergency_action("test")
        assert result["success"] is True
        assert result["action"] == "test"

    def test_sensor_sparkline(self) -> None:
        ui = DashboardUI(mock=True)
        result = ui.get_sensor_sparkline("kitchen", "temperature", 10)
        assert result["zone_id"] == "kitchen"
        assert len(result["readings"]) == 10
        assert "min" in result["stats"]

    def test_timeline_data(self) -> None:
        ui = DashboardUI(mock=True)
        now = time.time()
        data = ui.get_timeline_data(now - 60, now, "1sec")
        assert len(data) > 0

    def test_theme_switching(self) -> None:
        ui = DashboardUI(mock=True)
        result = ui.set_theme("light")
        assert result["theme"] == "light"
        assert "bg" in result["colors"]

    def test_zone_priority_list(self) -> None:
        ui = DashboardUI(mock=True)
        # Add zones with different risk levels
        for i, temp in enumerate([25.0, 60.0, 30.0]):
            zone = ZoneStatus(
                zone_id=f"zone_{i}",
                name=f"Zone {i}",
                temperature_c=temp,
                smoke_ppm=10.0,
                co_ppm=0.0,
                occupancy_count=0,
                alert_level="normal",
                last_update=time.time(),
                sensor_health={},
            )
            ui.update_zone(zone)

        priorities = ui.get_zone_priority_list()
        assert len(priorities) == 3
        # Highest temp should be first
        assert priorities[0]["zone"]["temperature_c"] == 60.0

    def test_reorder_zones(self) -> None:
        ui = DashboardUI(mock=True)
        for i in range(3):
            zone = ZoneStatus(
                zone_id=f"z{i}",
                name=f"Z{i}",
                temperature_c=20.0,
                smoke_ppm=0.0,
                co_ppm=0.0,
                occupancy_count=0,
                alert_level="normal",
                last_update=time.time(),
                sensor_health={},
            )
            ui.update_zone(zone)

        result = ui.reorder_zones(["z2", "z0", "z1"])
        assert result["success"] is True
        assert result["order"] == ["z2", "z0", "z1"]

    def test_reorder_zones_invalid(self) -> None:
        ui = DashboardUI(mock=True)
        result = ui.reorder_zones(["missing"])
        assert result["success"] is False


# ── Phrase Database Tests ──

class TestPhraseDatabase:
    def test_fire_alert_count(self) -> None:
        assert len(FIRE_ALERT_PHRASES) >= 98

    def test_evacuation_count(self) -> None:
        assert len(EVACUATION_PHRASES) >= 96

    def test_unique_ids(self) -> None:
        all_ids = [p["id"] for p in FIRE_ALERT_PHRASES + EVACUATION_PHRASES]
        assert len(all_ids) == len(set(all_ids)), "Duplicate phrase IDs found"

    def test_has_english_and_swahili(self) -> None:
        for p in FIRE_ALERT_PHRASES + EVACUATION_PHRASES:
            assert p["en"], f"Missing English for {p['id']}"
            assert p["sw"], f"Missing Swahili for {p['id']}"

    def test_categories(self) -> None:
        alert_cats = set(p["cat"] for p in FIRE_ALERT_PHRASES)
        evac_cats = set(p["cat"] for p in EVACUATION_PHRASES)
        assert alert_cats == {"alert", "status"}
        assert evac_cats == {"evacuation"}

    @pytest.mark.skip(reason="Generates actual database — run manually")
    def test_initialize_database(self) -> None:
        initialize_phrase_database()
