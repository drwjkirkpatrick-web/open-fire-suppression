/**
 * config.h — ESP32 configuration for open-fire-suppression
 *
 * Maps the Raspberry Pi 5 Python config (src/fire_suppression/config.py)
 * to ESP32 GPIO pins, I2C addresses, WiFi/MQTT settings, and detection
 * thresholds. All tunable values are #defines so they compile to flash
 * with zero runtime overhead.
 *
 * Hardware: ESP32 DevKitC (38-pin)
 * Sensors:  MQ-2 (ADC), SHT40, MLX90614, BME680, AMG8833 (I2C), DS18B20 (1-Wire)
 * Actuation: 4-channel relay module (active-low)
 * Alerts:    Active buzzer + WS2812 LED strip
 * Safety:    Arm switch, E-stop button, Tamper switch
 * Comms:     WiFi + MQTT to central Pi 5 dashboard
 */
#ifndef FIRE_SUPPRESSION_CONFIG_H
#define FIRE_SUPPRESSION_CONFIG_H

#include <Arduino.h>

// ── System ──────────────────────────────────────────────────────
#define FS_VERSION          "esp32-1.0.0"
#define FS_SERIAL_BAUD      115200
#define FS_LOOP_INTERVAL_MS 1000   // main loop tick (1 s)
#define FS_WATCHDOG_TIMEOUT_MS 30000  // 30 s — matches Pi config

// ── I2C Bus ─────────────────────────────────────────────────────
#define FS_I2C_SDA          21
#define FS_I2C_SCL          22
#define FS_I2C_FREQ         100000  // 100 kHz

// ── Sensor Pins ──────────────────────────────────────────────────
#define FS_MQ2_ADC_PIN      34     // ADC1_CH6 — smoke sensor
#define FS_MQ2_WARMUP_MS    60000  // 60 s warmup (matches Pi config)
#define FS_DS18B20_PIN      4      // OneWire data line

// ── I2C Sensor Addresses ────────────────────────────────────────
#define FS_SHT40_ADDR       0x44
#define FS_MLX90614_ADDR    0x5A
#define FS_BME680_ADDR      0x77
#define FS_AMG8833_ADDR     0x69

// ── Actuation (Relay) ────────────────────────────────────────────
#define FS_RELAY_COUNT      4
#define FS_RELAY_PINS       {26, 27, 14, 12}  // GPIO pins
#define FS_RELAY_ACTIVE_LOW true               // common relay modules
#define FS_PRE_ACTIVATION_S 10                  // 10 s buzzer before suppress
#define FS_SUPPRESS_DURATION_S 60               // 60 s suppression burst
#define FS_FLOW_SENSOR_PIN  35                  // ADC1_CH7 — flow confirm
#define FS_MANUAL_BUTTON_PIN 0                  // BOOT button (GPIO 0)
#define FS_BUZZER_PIN       25                   // PWM buzzer

// ── Safety ──────────────────────────────────────────────────────
#define FS_ARM_PIN          32     // Arm/disarm toggle switch
#define FS_ESTOP_PIN        33     // Emergency stop button
#define FS_TAMPER_PIN       13     // Enclosure tamper switch
#define FS_MAINT_PIN        15     // Maintenance mode switch

// ── LED Evacuation (WS2812) ──────────────────────────────────────
#define FS_LED_PIN          2      // GPIO 2
#define FS_LED_COUNT       8      // 8-LED strip for zone guidance

// ── WiFi ─────────────────────────────────────────────────────────
#define FS_WIFI_SSID        "FIRE_SUPPRESSION_AP"
#define FS_WIFI_PASSWORD    "change-me-please"
#define FS_WIFI_TIMEOUT_MS  15000  // 15 s connect timeout

// ── MQTT ─────────────────────────────────────────────────────────
#define FS_MQTT_BROKER      "192.168.4.1"   // Pi 5 dashboard IP
#define FS_MQTT_PORT        1883
#define FS_MQTT_CLIENT_ID   "esp32-fire-node"
#define FS_MQTT_TOPIC_BASE  "fire_suppression"
#define FS_MQTT_KEEPALIVE_S 30
#define FS_MQTT_BUFFER_SIZE 512

// ── Detection Thresholds (mirror Pi config DEFAULT_CONFIG) ───────
// Single-sensor thresholds → WARNING
#define FS_THRESH_MQ2_PPM        300      // smoke ppm
#define FS_THRESH_MLX90614_C     80.0f    // IR object temp °C
#define FS_THRESH_SHT40_C        60.0f    // ambient temp °C
#define FS_THRESH_BME680_GAS     5000     // gas resistance Ω (lower = worse)
#define FS_THRESH_ENS160_TVOC    500     // TVOC ppb (if ENS160 present)
#define FS_THRESH_DS18B20_C      70.0f   // external temp probe °C
#define FS_THRESH_AMG8833_C      60.0f   // thermal array pixel temp °C

// Multi-sensor fusion → ALERT
#define FS_FUSION_MIN_SENSORS    2       // min correlated sensors
#define FS_FUSION_WINDOW_MS      5000   // 5 s correlation window

// Confidence weights (must sum to ~1.0)
#define FS_CONF_SMOKE_WEIGHT     0.30f
#define FS_CONF_TEMP_WEIGHT      0.30f
#define FS_CONF_GAS_WEIGHT       0.20f
#define FS_CONF_THERMAL_WEIGHT   0.20f

// Thermal hotspot
#define FS_THERMAL_HOTSPOT_MIN_C  60.0f
#define FS_THERMAL_HOTSPOT_MIN_PX 4

// ── Alert Priorities ────────────────────────────────────────────
#define FS_ALERT_PRIORITY_CLEAR    0
#define FS_ALERT_PRIORITY_INFO     1
#define FS_ALERT_PRIORITY_WARNING  2
#define FS_ALERT_PRIORITY_ALERT    3
#define FS_ALERT_PRIORITY_CRITICAL 4

// ── Mock Mode (for testing without sensors) ─────────────────────
// #define FS_MOCK_MODE 1  // Uncomment to run without real hardware

#endif // FIRE_SUPPRESSION_CONFIG_H