"""Tests for power management.

# P001 — Battery Voltage Monitoring
# P002 — Low Battery Warning
# P003 — Safe Shutdown on Low Battery
"""
import pytest

from fire_suppression.power.manager import PowerManager, PowerSource


class TestPowerManager:
    """Power management tests."""

    def setup_method(self) -> None:
        self.power = PowerManager()

    @pytest.mark.asyncio
    async def test_mock_status(self) -> None:
        """# P001 — Mock power status returns valid data."""
        status = await self.power.get_status()
        assert status.source == PowerSource.AC
        assert status.battery_percent > 0
        assert status.battery_voltage > 0

    @pytest.mark.asyncio
    async def test_low_battery_warning(self) -> None:
        """# P002 — Low battery triggers warning."""
        # Simulate by setting thresholds above mock values
        self.power.low_battery_percent = 90
        self.power.critical_battery_percent = 5
        action = await self.power.check_and_handle_low_battery()
        assert action == "warning"

    @pytest.mark.asyncio
    async def test_critical_battery_shutdown(self) -> None:
        """# P003 — Critical battery triggers shutdown signal."""
        self.power.low_battery_percent = 95
        self.power.critical_battery_percent = 90
        action = await self.power.check_and_handle_low_battery()
        assert action == "shutdown"

    @pytest.mark.asyncio
    async def test_battery_ok(self) -> None:
        """Normal battery level returns no action."""
        self.power.low_battery_percent = 10
        action = await self.power.check_and_handle_low_battery()
        assert action is None

    @pytest.mark.asyncio
    async def test_default_status_no_ups(self) -> None:
        self.power.ups_type = "none"
        status = await self.power.get_status()
        assert status.source == PowerSource.AC
        assert status.battery_percent == 100.0
