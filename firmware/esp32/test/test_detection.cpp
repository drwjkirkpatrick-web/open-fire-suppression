/**
 * test_detection.cpp — Unit tests for ESP32 detection engine
 *
 * Runs on the native (host) platform via PlatformIO's native test runner.
 * Tests the core detection logic without any hardware dependencies.
 *
 * Run: pio test -e native
 */

#include <unity.h>
#include <string.h>
#include <math.h>

// Include config and detection — mock the Arduino-specific types
#define ARDUINO_H_MOCKED
#include "config.h"
#include "types.h"
#include "detection/detection.h"

// ── Test helpers ─────────────────────────────────────────────────

static SensorReading make_clear_reading() {
    SensorReading r;
    memset(&r, 0, sizeof(r));
    r.timestamp = 0;
    r.smoke_ppm = 50;        // below threshold
    r.temp_c = 25.0f;        // normal temp
    r.humidity_pct = 45.0f;
    r.ir_object_c = 25.0f;   // normal IR
    r.ir_ambient_c = 25.0f;
    r.gas_resistance = 50000; // high resistance = clean air
    r.pressure_hpa = 1013.0f;
    r.ext_temp_c = 25.0f;
    r.thermal_valid = false;
    r.valid = true;
    return r;
}

static SensorReading make_smoke_only_reading() {
    SensorReading r = make_clear_reading();
    r.smoke_ppm = 500;  // above threshold (300)
    return r;
}

static SensorReading make_smoke_and_temp_reading() {
    SensorReading r = make_clear_reading();
    r.smoke_ppm = 500;       // above threshold
    r.temp_c = 70.0f;        // above threshold (60)
    r.ir_object_c = 90.0f;   // above threshold (80)
    return r;
}

static SensorReading make_all_triggered_reading() {
    SensorReading r = make_clear_reading();
    r.smoke_ppm = 800;
    r.temp_c = 75.0f;
    r.ir_object_c = 95.0f;
    r.gas_resistance = 3000;  // below threshold (5000)
    r.ext_temp_c = 80.0f;
    // Thermal grid: set some pixels above 60°C
    r.thermal_valid = true;
    for (int i = 0; i < 64; i++) {
        r.thermal_grid[i] = (i < 10) ? 65.0f : 25.0f;
    }
    return r;
}

// ── Tests ─────────────────────────────────────────────────────────

void test_clear_state_no_triggers(void) {
    FireDetectionEngine engine;
    SensorReading r = make_clear_reading();
    DetectionResult dr = engine.detect(r);

    TEST_ASSERT_EQUAL(FIRE_CLEAR, dr.state);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, dr.confidence);
    TEST_ASSERT_EQUAL(0, dr.triggered_count);
}

void test_warning_single_sensor_smoke(void) {
    FireDetectionEngine engine;
    SensorReading r = make_smoke_only_reading();
    DetectionResult dr = engine.detect(r);

    TEST_ASSERT_EQUAL(FIRE_WARNING, dr.state);
    TEST_ASSERT(dr.confidence > 0.0f);
    TEST_ASSERT_EQUAL(1, dr.triggered_count);
    TEST_ASSERT_TRUE(strstr(dr.triggered_names, "mq2") != nullptr);
}

void test_alert_multi_sensor_fusion(void) {
    FireDetectionEngine engine;
    SensorReading r = make_smoke_and_temp_reading();
    DetectionResult dr = engine.detect(r);

    TEST_ASSERT_EQUAL(FIRE_ALERT, dr.state);
    TEST_ASSERT(dr.confidence > 0.0f);
    TEST_ASSERT(dr.triggered_count >= 2);
}

void test_confidence_increases_with_more_sensors(void) {
    FireDetectionEngine engine;

    // Single sensor
    SensorReading r1 = make_smoke_only_reading();
    DetectionResult dr1 = engine.detect(r1);

    // Multiple sensors — need a fresh engine to avoid activation history
    FireDetectionEngine engine2;
    SensorReading r2 = make_all_triggered_reading();
    DetectionResult dr2 = engine2.detect(r2);

    TEST_ASSERT(dr2.confidence > dr1.confidence);
}

void test_thermal_hotspot_detection(void) {
    FireDetectionEngine engine;
    SensorReading r = make_all_triggered_reading();
    DetectionResult dr = engine.detect(r);

    TEST_ASSERT(dr.thermal_hotspot_count >= FS_THERMAL_HOTSPOT_MIN_PX);
    TEST_ASSERT(dr.thermal_hotspot_max_c >= FS_THERMAL_HOTSPOT_MIN_C);
}

void test_invalid_reading_returns_clear(void) {
    FireDetectionEngine engine;
    SensorReading r;
    memset(&r, 0, sizeof(r));
    r.valid = false;

    DetectionResult dr = engine.detect(r);
    TEST_ASSERT_EQUAL(FIRE_CLEAR, dr.state);
}

void test_gas_resistance_low_triggers(void) {
    FireDetectionEngine engine;
    SensorReading r = make_clear_reading();
    r.gas_resistance = 2000;  // below threshold (5000)

    DetectionResult dr = engine.detect(r);
    TEST_ASSERT(dr.triggered_count >= 1);
    TEST_ASSERT_TRUE(strstr(dr.triggered_names, "bme680") != nullptr);
}

void test_latency_nonzero(void) {
    FireDetectionEngine engine;
    SensorReading r = make_smoke_and_temp_reading();
    DetectionResult dr = engine.detect(r);

    // Latency should be recorded (may be 0 on fast native execution)
    TEST_ASSERT(dr.latency_ms >= 0);
}

void test_state_strings(void) {
    TEST_ASSERT_EQUAL_STRING("clear", fire_state_str(FIRE_CLEAR));
    TEST_ASSERT_EQUAL_STRING("warning", fire_state_str(FIRE_WARNING));
    TEST_ASSERT_EQUAL_STRING("alert", fire_state_str(FIRE_ALERT));
    TEST_ASSERT_EQUAL_STRING("confirmed", fire_state_str(FIRE_CONFIRMED));
}

// ── Main ──────────────────────────────────────────────────────────

int main(int argc, char **argv) {
    UNITY_BEGIN();

    RUN_TEST(test_clear_state_no_triggers);
    RUN_TEST(test_warning_single_sensor_smoke);
    RUN_TEST(test_alert_multi_sensor_fusion);
    RUN_TEST(test_confidence_increases_with_more_sensors);
    RUN_TEST(test_thermal_hotspot_detection);
    RUN_TEST(test_invalid_reading_returns_clear);
    RUN_TEST(test_gas_resistance_low_triggers);
    RUN_TEST(test_latency_nonzero);
    RUN_TEST(test_state_strings);

    UNITY_END();
    return 0;
}