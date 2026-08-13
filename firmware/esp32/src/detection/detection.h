/**
 * detection.h — Fire detection engine for ESP32
 *
 * Ports the Python FireDetectionEngine to C++.
 * Strategy:
 *   1. Single-sensor threshold check → WARNING
 *   2. Multi-sensor correlation within time window → ALERT
 *   3. Thermal hotspot detection for localization
 *   4. Confidence scoring with weighted sensors
 *
 * Mirrors: src/fire_suppression/detection/engine.py
 */
#ifndef FIRE_SUPPRESSION_DETECTION_H
#define FIRE_SUPPRESSION_DETECTION_H

#include <Arduino.h>
#include "types.h"

// ── Fire State (mirrors Python FireState enum) ───────────────────
enum FireState {
    FIRE_CLEAR      = 0,  // no detection
    FIRE_WARNING    = 1,  // single sensor threshold exceeded
    FIRE_ALERT      = 2,  // multi-sensor fusion confirms fire
    FIRE_CONFIRMED  = 3   // suppression activated
};

// String helper for serial/MQTT
const char* fire_state_str(FireState s);

// ── Detection Result (mirrors Python DetectionResult) ───────────
struct DetectionResult {
    FireState state;
    float     confidence;          // 0.0–1.0
    uint8_t   triggered_count;      // number of sensors triggered
    char      triggered_names[64];  // comma-separated sensor names
    uint8_t   thermal_hotspot_count;
    float     thermal_hotspot_max_c;
    uint32_t  timestamp;
    uint16_t  latency_ms;
    char      reason[64];
};

// ── Activation Record (for fusion time window) ───────────────────
struct Activation {
    char      sensor_name[16];
    uint32_t  timestamp;
    float     confidence_weight;
};

// ── Fire Detection Engine ────────────────────────────────────────
class FireDetectionEngine {
public:
    FireDetectionEngine();

    DetectionResult detect(const SensorReading &r);

    // Configuration setters (optional overrides)
    void set_fusion_min_sensors(uint8_t n) { _fusion_min = n; }
    void set_fusion_window_ms(uint32_t ms) { _fusion_window = ms; }

    // State queries
    FireState state() const { return _last_state; }
    float     confidence() const { return _last_confidence; }

private:
    FireState   _last_state;
    float       _last_confidence;

    // Thresholds (from config.h)
    float       _thresh_mq2;
    float       _thresh_mlx;
    float       _thresh_sht;
    float       _thresh_bme_gas;
    float       _thresh_ds18;
    float       _thresh_amg;

    // Fusion parameters
    uint8_t     _fusion_min;
    uint32_t    _fusion_window;

    // Confidence weights
    float       _w_smoke;
    float       _w_temp;
    float       _w_gas;
    float       _w_thermal;

    // Activation history (rolling window)
    static const uint8_t MAX_ACTIVATIONS = 16;
    Activation  _activations[MAX_ACTIVATIONS];
    uint8_t     _act_count;

    // Thermal hotspot detection
    uint8_t   _count_thermal_hotspots(const SensorReading &r, float &max_c);

    // Single-sensor threshold check
    bool      _check_thresholds(const SensorReading &r, DetectionResult &dr);

    // Multi-sensor fusion within time window
    bool      _check_fusion(DetectionResult &dr);

    // Clean expired activations from the rolling window
    void      _prune_activations(uint32_t now);

    // Add an activation record
    void      _add_activation(const char *name, float weight, uint32_t now);

    // Calculate weighted confidence
    float     _calc_confidence();
};

#endif // FIRE_SUPPRESSION_DETECTION_H