/**
 * main.ino — ESP32 fire suppression sensor node
 *
 * open-fire-suppression — ESP32 firmware port
 * Part of the open-fire-suppression system. This firmware runs on an
 * ESP32 as a lightweight sensor node that:
 *   1. Reads fire sensors (smoke, temp, IR, thermal array, gas)
 *   2. Runs multi-sensor fusion detection
 *   3. Drives suppression relays (with safety interlocks)
 *   4. Publishes status via MQTT to the central Pi 5 dashboard
 *   5. Alerts via buzzer and WS2812 LED evacuation guidance
 *
 * The ESP32 node operates independently — it continues detecting and
 * suppressing even if WiFi/MQTT to the Pi 5 is lost. This makes it
 * suitable for remote or standalone deployment.
 *
 * Parent project: src/fire_suppression/main.py (Raspberry Pi 5)
 * This firmware:  firmware/esp32/src/main.ino
 *
 * USE AT YOUR OWN RISK — see root README for regulatory disclaimers.
 */

#include <Arduino.h>
#include "config.h"
#include "sensors/sensors.h"
#include "detection/detection.h"
#include "safety/safety.h"
#include "actuation/actuation.h"
#include "telemetry/telemetry.h"

// ── Global Subsystems ────────────────────────────────────────────
SensorManager        sensors;
FireDetectionEngine  detection;
SafetyInterlock      safety;
RelayController      actuation;
Telemetry            telemetry;

// ── State ────────────────────────────────────────────────────────
SensorReading   last_reading;
DetectionResult last_detection;
uint32_t        last_loop_time = 0;
bool            mqtt_initialized = false;

// ── Setup ────────────────────────────────────────────────────────
void setup() {
    Serial.begin(FS_SERIAL_BAUD);
    delay(100);

    Serial.println("\n======================================");
    Serial.printf("open-fire-suppression %s\n", FS_VERSION);
    Serial.println("ESP32 Fire Detection & Suppression Node");
    Serial.println("======================================\n");

    // 1. Initialize safety first — system starts DISARMED
    Serial.println("[1/5] Safety interlock...");
    safety.begin();
    Serial.printf("  State: %s\n", safety_state_str(safety.state()));

    // 2. Initialize actuation — ensure all relays OFF
    Serial.println("[2/5] Actuation relays...");
    actuation.begin();
    Serial.println("  All relays OFF (safe state)");

    // 3. Initialize sensors
    Serial.println("[3/5] Sensors...");
    sensors.begin();
    Serial.printf("  %d sensors initialized, %d healthy\n",
                  (int)sensors.count(), (int)sensors.healthy_count());

    // 4. Initialize alerts (buzzer + LED)
    Serial.println("[4/5] Alerts (buzzer + LED)...");
    telemetry.buzzer_begin();
    telemetry.led_begin();
    Serial.println("  Buzzer + WS2812 LED ready");

    // 5. Connect WiFi + MQTT (non-blocking on failure)
    Serial.println("[5/5] Connectivity...");
    if (telemetry.wifi_connect()) {
        if (telemetry.mqtt_connect()) {
            mqtt_initialized = true;
            Serial.println("  MQTT connected — telemetry active");
        } else {
            Serial.println("  MQTT failed — running standalone");
        }
    } else {
        Serial.println("  WiFi failed — running standalone");
    }

    Serial.println("\n── System Ready ──");
    Serial.printf("Safety: %s | Sensors: %d/%d | MQTT: %s\n",
                  safety_state_str(safety.state()),
                  (int)sensors.healthy_count(),
                  (int)sensors.count(),
                  mqtt_initialized ? "yes" : "no");
    Serial.println("======================================\n");

    // Feed watchdog
    safety.feed_watchdog();
}

// ── Main Loop ────────────────────────────────────────────────────
void loop() {
    uint32_t now = millis();

    // Throttle main loop to FS_LOOP_INTERVAL_MS
    if (now - last_loop_time < FS_LOOP_INTERVAL_MS) {
        // Still update fast subsystems (buzzer, LED, MQTT keepalive)
        telemetry.led_update();
        telemetry.mqtt_loop();
        return;
    }
    last_loop_time = now;

    // ── 1. Poll all sensors ──────────────────────────────────────
    sensors.poll_all(last_reading);

    // ── 2. Run fire detection ────────────────────────────────────
    last_detection = detection.detect(last_reading);

    // ── 3. Update safety state ───────────────────────────────────
    safety.update();
    safety.feed_watchdog();

    // ── 4. Actuation state machine ───────────────────────────────
    actuation.update();

    // ── 5. Alert routing ─────────────────────────────────────────
    // Map detection state to alert priority
    uint8_t alert_priority = FS_ALERT_PRIORITY_CLEAR;
    uint8_t led_zone = 0;

    switch (last_detection.state) {
        case FIRE_CLEAR:
            alert_priority = FS_ALERT_PRIORITY_CLEAR;
            telemetry.led_clear();
            break;

        case FIRE_WARNING:
            alert_priority = FS_ALERT_PRIORITY_WARNING;
            telemetry.led_warning();
            break;

        case FIRE_ALERT:
            alert_priority = FS_ALERT_PRIORITY_ALERT;
            telemetry.led_alert();
            break;

        case FIRE_CONFIRMED:
            alert_priority = FS_ALERT_PRIORITY_CRITICAL;
            telemetry.led_alert();
            break;
    }

    // Override: E-stop or tamper → critical
    if (safety.e_stop_active() || safety.tamper_active()) {
        alert_priority = FS_ALERT_PRIORITY_CRITICAL;
        telemetry.led_alert();
    }

    telemetry.buzzer_alert(alert_priority);

    // ── 6. Suppression actuation ─────────────────────────────────
    // Only activate if:
    //   - Detection says ALERT or higher
    //   - Safety says we CAN actuate (ARMED, no E-stop, no tamper)
    //   - Actuation is currently IDLE or in COOLDOWN
    if (last_detection.state >= FIRE_ALERT &&
        safety.can_actuate() &&
        (actuation.state() == ACT_IDLE)) {

        // Determine which zones to suppress based on thermal hotspots
        uint8_t zone_mask = 0xFF;  // default: all zones
        if (last_detection.thermal_hotspot_count > 0) {
            // Target only zones with thermal hotspots
            // For now, all zones — zone targeting logic can be expanded
            zone_mask = 0xFF;
        }

        actuation.activate(zone_mask, last_detection.reason);
        last_detection.state = FIRE_CONFIRMED;

        Serial.printf("[SUPPRESSION] Activated! zone_mask=0x%02X reason=%s\n",
                      zone_mask, last_detection.reason);
    }

    // If safety disallows actuation during an active fire, log it
    if (last_detection.state >= FIRE_ALERT && !safety.can_actuate()) {
        Serial.printf("[BLOCKED] Safety state: %s — suppression inhibited\n",
                      safety_state_str(safety.state()));
    }

    // ── 7. Telemetry ─────────────────────────────────────────────
    if (mqtt_initialized) {
        telemetry.mqtt_loop();
        telemetry.publish_status(last_reading, last_detection,
                                  safety, actuation);
    }

    // ── 8. Serial status (always — for debug/monitor) ───────────
    Serial.printf("\n[%lus] %s | conf=%.2f | triggered=%d (%s) | "
                  "safety=%s | act=%s | heap=%u\n",
                  (unsigned long)(now / 1000),
                  fire_state_str(last_detection.state),
                  last_detection.confidence,
                  last_detection.triggered_count,
                  last_detection.triggered_names,
                  safety_state_str(safety.state()),
                  actuation_state_str(actuation.state()),
                  (unsigned)ESP.getFreeHeap());

    // Sensor values
    Serial.printf("  MQ2=%.0fppm SHT40=%.1f°C/%.1f%% MLX=%.1f°C "
                  "BME=%.0fΩ DS18=%.1f°C AMG=%s\n",
                  last_reading.smoke_ppm,
                  isnan(last_reading.temp_c) ? 0 : last_reading.temp_c,
                  isnan(last_reading.humidity_pct) ? 0 : last_reading.humidity_pct,
                  isnan(last_reading.ir_object_c) ? 0 : last_reading.ir_object_c,
                  isnan(last_reading.gas_resistance) ? 0 : last_reading.gas_resistance,
                  isnan(last_reading.ext_temp_c) ? 0 : last_reading.ext_temp_c,
                  last_reading.thermal_valid ? "yes" : "no");

    // ── 9. Watchdog check ────────────────────────────────────────
    if (!safety.watchdog_ok()) {
        Serial.println("[WATCHDOG] Timeout! Auto-disarming.");
        safety.disarm();
        actuation.deactivate();
        // Re-feed to allow recovery
        safety.feed_watchdog();
    }

    // Update LED animation
    telemetry.led_update();
}