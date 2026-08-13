/**
 * telemetry.h — MQTT telemetry + alerts for ESP32
 *
 * Ports the Python telemetry/notifier + alerts subsystems to C++.
 * Publishes JSON status to the Pi 5 MQTT broker and drives:
 *   - Active buzzer (priority-based patterns)
 *   - WS2812 LED strip (evacuation guidance)
 *
 * Mirrors:
 *   src/fire_suppression/telemetry/mqtt_client.py
 *   src/fire_suppression/alerts/voice_alert.py (buzzer patterns)
 *   src/fire_suppression/alerts/evacuation_leds.py
 */
#ifndef FIRE_SUPPRESSION_TELEMETRY_H
#define FIRE_SUPPRESSION_TELEMETRY_H

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_NeoPixel.h>
#include "sensors/sensors.h"
#include "detection/detection.h"
#include "safety/safety.h"
#include "actuation/actuation.h"

// ── Telemetry ────────────────────────────────────────────────────
class Telemetry {
public:
    Telemetry();

    // WiFi
    bool wifi_connect();
    bool wifi_connected() const;
    void wifi_disconnect();

    // MQTT
    bool mqtt_connect();
    bool mqtt_connected();
    void mqtt_loop();                       // call every loop — keepalive
    void publish_status(const SensorReading &r,
                        const DetectionResult &d,
                        const SafetyInterlock &s,
                        const RelayController &a);

    // Buzzer
    void buzzer_begin();
    void buzzer_alert(uint8_t priority);    // 0=clear, 1=info, 2=warn, 3=alert, 4=critical
    void buzzer_off();

    // LED evacuation guidance
    void led_begin();
    void led_clear();                       // all off
    void led_evacuate(uint8_t zone);         // green path away from zone
    void led_warning();                     // pulsing yellow
    void led_alert();                       // flashing red
    void led_update();                      // call every loop for animations

    // Status JSON builder (also used by serial output)
    String build_status_json(const SensorReading &r,
                             const DetectionResult &d,
                             const SafetyInterlock &s,
                             const RelayController &a) const;

private:
    WiFiClient    _wifi_client;
    PubSubClient  _mqtt;
    Adafruit_NeoPixel *_leds;

    uint32_t _last_mqtt_publish;
    uint32_t _mqtt_publish_interval;  // ms between publishes

    // Buzzer state
    uint8_t  _buzzer_priority;
    uint32_t _buzzer_toggle_time;
    bool     _buzzer_on;

    // LED animation state
    uint32_t _led_last_update;
    uint8_t  _led_mode;  // 0=clear, 1=evac, 2=warn, 3=alert
    uint8_t  _led_zone;
    uint16_t _led_phase;

    void _publish(const char *subtopic, const char *payload);
    void _buzzer_update();
    void _led_animate();
};

#endif // FIRE_SUPPRESSION_TELEMETRY_H