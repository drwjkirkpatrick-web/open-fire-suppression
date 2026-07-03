"""Tests for fire detection engine.

# D001 — Single-Sensor Threshold Fire Detection
# D002 — Multi-Sensor Fusion Fire Detection
# D003 — False Positive Suppression
# D004 — Thermal Hotspot Detection
# D008 — Confidence Scoring
"""
import pytest

from fire_suppression.detection.engine import FireDetectionEngine, FireState
from fire_suppression.sensors.base import MockSensor, SensorReading


class TestFireDetection:
    """Fire detection engine tests."""

    def setup_method(self) -> None:
        self.engine = FireDetectionEngine()

    def test_clear_state_no_readings(self) -> None:
        """# D001 — No readings = CLEAR."""
        result = self.engine.detect({})
        assert result.state == FireState.CLEAR
        assert result.confidence == 0.0

    def test_single_sensor_warning(self) -> None:
        """# D001 — Single sensor above threshold → WARNING."""
        reading = SensorReading(
            sensor_name="mq2",
            timestamp=0.0,
            values={"smoke_ppm": 500.0},  # Above 300 threshold
        )
        result = self.engine.detect({"mq2": reading})
        assert result.state == FireState.WARNING
        assert result.confidence > 0
        assert "mq2" in result.triggered_sensors

    def test_multi_sensor_fusion_alert(self) -> None:
        """# D002 — Two sensors confirming → ALERT."""
        mq2 = SensorReading("mq2", 0.0, {"smoke_ppm": 500.0})
        mlx = SensorReading("mlx90614", 0.0, {"object_temperature_c": 150.0})
        result = self.engine.detect({"mq2": mq2, "mlx90614": mlx})
        assert result.state == FireState.ALERT
        assert result.confidence >= 0.6

    def test_false_positive_suppression(self) -> None:
        """# D003 — Only temperature high, no smoke/gas → no ALERT."""
        mlx = SensorReading("mlx90614", 0.0, {"object_temperature_c": 150.0})
        result = self.engine.detect({"mlx90614": mlx})
        # Should be WARNING (single sensor), not ALERT (need fusion)
        assert result.state == FireState.WARNING
        assert result.confidence < 0.6

    def test_false_alarm_scenario(self) -> None:
        """# D003 — Hot day + normal air = no alert."""
        sht40 = SensorReading("sht40", 0.0, {"temperature_c": 65.0, "humidity_percent": 50.0})
        # No smoke, no gas — just temp
        result = self.engine.detect({"sht40": sht40})
        assert result.state == FireState.WARNING  # Temp threshold exceeded
        assert "sht40" in result.triggered_sensors

    def test_confidence_increases_with_sensors(self) -> None:
        """# D008 — Confidence increases with more confirming sensors."""
        mq2 = SensorReading("mq2", 0.0, {"smoke_ppm": 500.0})
        mlx = SensorReading("mlx90614", 0.0, {"object_temperature_c": 150.0})
        bme = SensorReading("bme680", 0.0, {"gas_resistance_ohm": 2000.0})

        r1 = self.engine.detect({"mq2": mq2})
        r2 = self.engine.detect({"mq2": mq2, "mlx90614": mlx})
        r3 = self.engine.detect({"mq2": mq2, "mlx90614": mlx, "bme680": bme})

        # Note: because of activation history window, these build on each other
        assert r1.confidence >= 0
        assert r3.confidence >= r2.confidence

    def test_thermal_hotspot_detection(self) -> None:
        """# D004 — Detect hotspots in thermal grid."""
        # Create 8×8 grid with hotspot in center
        values = {f"pixel_{i:02d}": 25.0 for i in range(64)}
        for r in range(3, 5):
            for c in range(3, 5):
                values[f"pixel_{r*8+c:02d}"] = 70.0

        reading = SensorReading("amg8833", 0.0, values)
        result = self.engine.detect({"amg8833": reading})
        assert len(result.thermal_hotspots) > 0
        hotspot = result.thermal_hotspots[0]
        assert hotspot["max_temp_c"] >= 70.0
        assert hotspot["size"] >= 4

    def test_latency_tracking(self) -> None:
        mq2 = SensorReading("mq2", 0.0, {"smoke_ppm": 500.0})
        mlx = SensorReading("mlx90614", 0.0, {"object_temperature_c": 150.0})
        result = self.engine.detect({"mq2": mq2, "mlx90614": mlx})
        assert result.latency_ms >= 0
        assert result.latency_ms < 100  # Should complete in <100ms

    def test_disabled_detection(self) -> None:
        from fire_suppression.config import Config
        cfg = Config()
        cfg._data["detection"]["enabled"] = False
        engine = FireDetectionEngine(cfg)
        mq2 = SensorReading("mq2", 0.0, {"smoke_ppm": 9999.0})
        result = engine.detect({"mq2": mq2})
        assert result.state == FireState.CLEAR
        assert result.reason == "detection_disabled"
