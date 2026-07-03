"""Tests for safety interlock system.

# F001 — System Arming
# F002 — Disarm Safety
# F003 — Maintenance Mode
# F006 — Emergency Stop
"""
import pytest

from fire_suppression.safety.interlock import SafetyInterlock, SafetyState


class TestSafetyInterlock:
    """Safety interlock tests."""

    def setup_method(self) -> None:
        self.safety = SafetyInterlock()

    def test_initial_state_is_disarmed(self) -> None:
        """# F001 — System starts DISARMED."""
        assert self.safety.state == SafetyState.DISARMED
        assert self.safety.is_armed is False
        assert self.safety.can_actuate is False

    def test_arm_changes_state(self) -> None:
        """# F001 — Arm transitions to ARMED."""
        result = self.safety.arm(pin=1234)
        assert result is True
        assert self.safety.state == SafetyState.ARMED
        assert self.safety.is_armed is True
        assert self.safety.can_actuate is True

    def test_disarm_inhibits_actuation(self) -> None:
        """# F002 — Disarm immediately blocks actuation."""
        self.safety.arm(pin=1234)
        assert self.safety.can_actuate is True
        self.safety.disarm()
        assert self.safety.state == SafetyState.DISARMED
        assert self.safety.can_actuate is False

    def test_emergency_stop_blocks_all(self) -> None:
        """# F006 — E-stop prevents arming and actuation."""
        self.safety._on_emergency_stop()
        assert self.safety.state == SafetyState.EMERGENCY_STOP
        assert self.safety.can_actuate is False
        result = self.safety.arm(pin=1234)
        assert result is False

    def test_emergency_stop_reset(self) -> None:
        """# F006 — E-stop reset returns to DISARMED."""
        self.safety._on_emergency_stop()
        assert self.safety.state == SafetyState.EMERGENCY_STOP
        result = self.safety.reset_emergency_stop(pin=1234)
        assert result is True
        assert self.safety.state == SafetyState.DISARMED

    def test_maintenance_mode(self) -> None:
        """# F003 — Maintenance mode blocks actuation."""
        self.safety._on_maintenance()
        assert self.safety.state == SafetyState.MAINTENANCE
        assert self.safety.can_actuate is False

    def test_maintenance_release(self) -> None:
        """# F003 — Release maintenance returns to DISARMED."""
        self.safety._on_maintenance()
        self.safety._on_maintenance_release()
        assert self.safety.state == SafetyState.DISARMED

    def test_watchdog_feed(self) -> None:
        """# F005 — Watchdog feeds and checks correctly."""
        self.safety.feed_watchdog()
        status = self.safety.check_watchdog()
        assert status["status"] == "ok"
        assert status["elapsed_seconds"] < 1.0

    def test_watchdog_expired(self) -> None:
        """# F005 — Watchdog expires after timeout."""
        self.safety._watchdog_last_feed = 0  # Long ago
        self.safety.watchdog_timeout = 30
        status = self.safety.check_watchdog()
        assert status["status"] == "expired"

    def test_tamper_blocks_actuation(self) -> None:
        """# F004 — Tamper locks out system."""
        self.safety._on_tamper()
        assert self.safety.state == SafetyState.TAMPERED
        assert self.safety.can_actuate is False

    def test_tamper_reset(self) -> None:
        """# F004 — Tamper reset returns to DISARMED."""
        self.safety._on_tamper()
        result = self.safety.reset_tamper(pin=1234)
        assert result is True
        assert self.safety.state == SafetyState.DISARMED
