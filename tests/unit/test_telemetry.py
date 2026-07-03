"""Tests for telemetry logger.

# T001 — SQLite Event Logging
# T006 — Log Rotation
"""
import os
from pathlib import Path

import pytest

from fire_suppression.config import Config
from fire_suppression.sensors.base import SensorReading
from fire_suppression.telemetry.logger import TelemetryLogger


class TestTelemetryLogger:
    """Telemetry logging tests."""

    def setup_method(self) -> None:
        # Use temp directory for test database
        self.tmp_dir = Path(__file__).parent / ".test_telemetry"
        self.tmp_dir.mkdir(exist_ok=True)
        self.db_path = self.tmp_dir / "test_events.db"
        # Monkeypatch config data_dir
        Config._instance = None
        os.environ["FIRE_TELEMETRY__DB_PATH"] = str(self.db_path)
        os.environ["FIRE_SYSTEM__DATA_DIR"] = str(self.tmp_dir)
        self.telemetry = TelemetryLogger()

    def teardown_method(self) -> None:
        self.telemetry.close()
        Config._instance = None
        for key in list(os.environ.keys()):
            if key.startswith("FIRE_"):
                del os.environ[key]
        # Cleanup temp files
        import shutil
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_log_sensor_reading(self) -> None:
        """# T001 — Sensor readings are logged to SQLite."""
        reading = SensorReading(
            sensor_name="test",
            timestamp=0.0,
            values={"temp": 25.0},
            raw=None,
            unit="°C",
        )
        self.telemetry.log_sensor_reading(reading, health_status="ok")
        history = self.telemetry.get_sensor_history(sensor_name="test", limit=1)
        assert len(history) == 1
        assert history[0]["sensor_name"] == "test"

    def test_log_event(self) -> None:
        self.telemetry.log_event("test_event", severity="info", message="hello")
        events = self.telemetry.get_events(event_type="test_event")
        assert len(events) >= 1
        assert events[0]["severity"] == "info"

    def test_log_detection(self) -> None:
        self.telemetry.log_detection({
            "timestamp": 0.0,
            "state": "alert",
            "confidence": 0.85,
            "triggered_sensors": ["mq2", "mlx90614"],
            "thermal_hotspots": [],
            "latency_ms": 12.5,
            "reason": "test",
        })
        status = self.telemetry.get_latest_status()
        assert "latest_detection" in status
        assert status["latest_detection"]["confidence"] == pytest.approx(0.85)

    def test_get_sensor_history_filter(self) -> None:
        r1 = SensorReading("s1", 1.0, {"v": 1.0})
        r2 = SensorReading("s2", 2.0, {"v": 2.0})
        self.telemetry.log_sensor_reading(r1)
        self.telemetry.log_sensor_reading(r2)
        history = self.telemetry.get_sensor_history(sensor_name="s1")
        assert len(history) == 1
        assert history[0]["sensor_name"] == "s1"

    def test_db_rotation_no_trigger(self) -> None:
        """# T006 — Small DB does not rotate."""
        result = self.telemetry.check_and_rotate()
        assert result is False  # DB too small to rotate

    def test_db_path_created(self) -> None:
        assert self.telemetry.db_path.parent.exists()
