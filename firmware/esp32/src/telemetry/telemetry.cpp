/**
 * telemetry.cpp — MQTT telemetry, buzzer, and LED alerts for ESP32
 *
 * Publishes JSON status to the Pi 5 MQTT broker every 5 seconds.
 * Drives buzzer with priority-based patterns (clear→critical).
 * Drives WS2812 LED strip for evacuation guidance.
 */
#include "telemetry/telemetry.h"
#include "../config.h"

Telemetry::Telemetry()
    : _mqtt(), _leds(nullptr), _last_mqtt_publish(0),
      _mqtt_publish_interval(5000),  // 5 s between publishes
      _buzzer_priority(0), _buzzer_toggle_time(0), _buzzer_on(false),
      _led_last_update(0), _led_mode(0), _led_zone(0), _led_phase(0) {}

// ── WiFi ─────────────────────────────────────────────────────────
bool Telemetry::wifi_connect() {
    Serial.printf("WiFi connecting to %s", FS_WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(FS_WIFI_SSID, FS_WIFI_PASSWORD);

    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < FS_WIFI_TIMEOUT_MS) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf(" OK\nIP: %s\n", WiFi.localIP().toString().c_str());
        return true;
    }

    Serial.println(" FAILED");
    return false;
}

bool Telemetry::wifi_connected() const {
    return WiFi.status() == WL_CONNECTED;
}

void Telemetry::wifi_disconnect() {
    WiFi.disconnect();
}

// ── MQTT ─────────────────────────────────────────────────────────
bool Telemetry::mqtt_connect() {
    _mqtt.setClient(_wifi_client);
    _mqtt.setServer(FS_MQTT_BROKER, FS_MQTT_PORT);
    _mqtt.setBufferSize(FS_MQTT_BUFFER_SIZE);
    _mqtt.setKeepAlive(FS_MQTT_KEEPALIVE_S);

    Serial.printf("MQTT connecting to %s:%d", FS_MQTT_BROKER, FS_MQTT_PORT);
    if (_mqtt.connect(FS_MQTT_CLIENT_ID)) {
        Serial.println(" OK");
        return true;
    }
    Serial.println(" FAILED");
    return false;
}

bool Telemetry::mqtt_connected() {
    return _mqtt.connected();
}

void Telemetry::mqtt_loop() {
    if (_mqtt.connected()) {
        _mqtt.loop();
    }
}

void Telemetry::_publish(const char *subtopic, const char *payload) {
    if (!_mqtt.connected()) return;

    char topic[128];
    snprintf(topic, sizeof(topic), "%s/%s", FS_MQTT_TOPIC_BASE, subtopic);
    _mqtt.publish(topic, payload);
}

void Telemetry::publish_status(const SensorReading &r,
                                const DetectionResult &d,
                                const SafetyInterlock &s,
                                const RelayController &a) {
    uint32_t now = millis();
    if (now - _last_mqtt_publish < _mqtt_publish_interval) return;
    if (!_mqtt.connected()) return;

    _last_mqtt_publish = now;

    String json = build_status_json(r, d, s, a);
    _publish("status", json.c_str());

    // Alert topic if not clear
    if (d.state >= FIRE_WARNING) {
        _publish("alert", json.c_str());
    }
}

String Telemetry::build_status_json(const SensorReading &r,
                                     const DetectionResult &d,
                                     const SafetyInterlock &s,
                                     const RelayController &a) const {
    char buf[FS_MQTT_BUFFER_SIZE];
    snprintf(buf, sizeof(buf),
        "{"
        "\"version\":\"%s\","
        "\"uptime_s\":%lu,"
        "\"free_heap\":%u,"

        "\"sensors\":{"
        "\"smoke_ppm\":%.1f,"
        "\"temp_c\":%.1f,"
        "\"humidity_pct\":%.1f,"
        "\"ir_object_c\":%.1f,"
        "\"gas_resistance\":%.0f,"
        "\"pressure_hpa\":%.1f,"
        "\"ext_temp_c\":%.1f,"
        "\"thermal_valid\":%s"
        "},"

        "\"detection\":{"
        "\"state\":\"%s\","
        "\"confidence\":%.2f,"
        "\"triggered_count\":%u,"
        "\"triggered_sensors\":\"%s\","
        "\"thermal_hotspots\":%u,"
        "\"thermal_max_c\":%.1f,"
        "\"latency_ms\":%u"
        "},"

        "\"safety\":{"
        "\"state\":\"%s\","
        "\"can_actuate\":%s,"
        "\"e_stop\":%s,"
        "\"tamper\":%s,"
        "\"watchdog_ok\":%s"
        "},"

        "\"actuation\":{"
        "\"state\":\"%s\","
        "\"flow_confirmed\":%s,"
        "\"time_remaining_s\":%.1f"
        "}"
        "}",

        FS_VERSION,
        (unsigned long)(millis() / 1000),
        (unsigned)ESP.getFreeHeap(),

        r.smoke_ppm,
        isnan(r.temp_c) ? 0 : r.temp_c,
        isnan(r.humidity_pct) ? 0 : r.humidity_pct,
        isnan(r.ir_object_c) ? 0 : r.ir_object_c,
        isnan(r.gas_resistance) ? 0 : r.gas_resistance,
        isnan(r.pressure_hpa) ? 0 : r.pressure_hpa,
        isnan(r.ext_temp_c) ? 0 : r.ext_temp_c,
        r.thermal_valid ? "true" : "false",

        fire_state_str(d.state),
        d.confidence,
        d.triggered_count,
        d.triggered_names,
        d.thermal_hotspot_count,
        isnan(d.thermal_hotspot_max_c) ? 0 : d.thermal_hotspot_max_c,
        d.latency_ms,

        safety_state_str(s.state()),
        s.can_actuate() ? "true" : "false",
        s.e_stop_active() ? "true" : "false",
        s.tamper_active() ? "true" : "false",
        s.watchdog_ok() ? "true" : "false",

        actuation_state_str(a.state()),
        a.flow_confirmed() ? "true" : "false",
        a.time_remaining_s()
    );

    return String(buf);
}

// ── Buzzer ───────────────────────────────────────────────────────
void Telemetry::buzzer_begin() {
    pinMode(FS_BUZZER_PIN, OUTPUT);
    digitalWrite(FS_BUZZER_PIN, LOW);
    _buzzer_priority = 0;
    _buzzer_on = false;
}

void Telemetry::buzzer_alert(uint8_t priority) {
    _buzzer_priority = priority;
    if (priority == FS_ALERT_PRIORITY_CLEAR) {
        buzzer_off();
    }
}

void Telemetry::buzzer_off() {
    digitalWrite(FS_BUZZER_PIN, LOW);
    _buzzer_on = false;
    _buzzer_priority = 0;
}

void Telemetry::_buzzer_update() {
    if (_buzzer_priority == FS_ALERT_PRIORITY_CLEAR) {
        buzzer_off();
        return;
    }

    // Priority-based beep patterns (period in ms)
    uint32_t period;
    switch (_buzzer_priority) {
        case FS_ALERT_PRIORITY_INFO:     period = 2000; break;  // short blip every 2s
        case FS_ALERT_PRIORITY_WARNING:  period = 1000; break;  // beep every 1s
        case FS_ALERT_PRIORITY_ALERT:    period = 500;  break;  // rapid beep
        case FS_ALERT_PRIORITY_CRITICAL: period = 200;  break;  // continuous fast
        default:                         period = 0;    break;
    }

    if (period == 0) return;

    uint32_t now = millis();
    if (now - _buzzer_toggle_time >= period) {
        _buzzer_toggle_time = now;
        _buzzer_on = !_buzzer_on;
        digitalWrite(FS_BUZZER_PIN, _buzzer_on ? HIGH : LOW);
    }
}

// ── LED Evacuation Guidance ──────────────────────────────────────
void Telemetry::led_begin() {
    _leds = new Adafruit_NeoPixel(FS_LED_COUNT, FS_LED_PIN,
                                   NEO_GRB + NEO_KHZ800);
    _leds->begin();
    _leds->clear();
    _leds->show();
}

void Telemetry::led_clear() {
    _led_mode = 0;
    if (_leds) {
        _leds->clear();
        _leds->show();
    }
}

void Telemetry::led_evacuate(uint8_t zone) {
    _led_mode = 1;
    _led_zone = zone;
}

void Telemetry::led_warning() {
    _led_mode = 2;
}

void Telemetry::led_alert() {
    _led_mode = 3;
}

void Telemetry::_led_animate() {
    if (!_leds) return;

    uint32_t now = millis();
    if (now - _led_last_update < 100) return;  // 10 FPS animation
    _led_last_update = now;

    _led_phase = (_led_phase + 1) % 100;

    switch (_led_mode) {
        case 0:  // clear — all off
            _leds->clear();
            _leds->show();
            break;

        case 1: {  // evacuate — green path away from fire zone
            for (uint8_t i = 0; i < FS_LED_COUNT; i++) {
                if (i < _led_zone) {
                    // Green path — bright pulsing
                    uint8_t brightness = 128 + 127 * sin(_led_phase * 0.0628);
                    _leds->setPixelColor(i, _leds->Color(0, brightness, 0));
                } else {
                    // Red — danger zone
                    _leds->setPixelColor(i, _leds->Color(255, 0, 0));
                }
            }
            _leds->show();
            break;
        }

        case 2: {  // warning — pulsing yellow
            uint8_t brightness = 128 + 127 * sin(_led_phase * 0.0628);
            uint32_t color = _leds->Color(brightness, brightness, 0);
            for (uint8_t i = 0; i < FS_LED_COUNT; i++) {
                _leds->setPixelColor(i, color);
            }
            _leds->show();
            break;
        }

        case 3: {  // alert — flashing red
            bool on = (_led_phase % 20) < 10;
            uint32_t color = on ? _leds->Color(255, 0, 0) : 0;
            for (uint8_t i = 0; i < FS_LED_COUNT; i++) {
                _leds->setPixelColor(i, color);
            }
            _leds->show();
            break;
        }
    }
}

void Telemetry::led_update() {
    _led_animate();
}