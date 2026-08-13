/**
 * detection.cpp — Fire detection engine implementation for ESP32
 *
 * Ports the Python FireDetectionEngine.detect() method.
 * Strategy:
 *   1. Check each sensor against its threshold → WARNING
 *   2. If ≥ fusion_min sensors triggered within fusion_window → ALERT
 *   3. Thermal hotspot count from AMG8833 grid
 *   4. Weighted confidence score
 */
#include "detection/detection.h"
#include "../config.h"

const char* fire_state_str(FireState s) {
    switch (s) {
        case FIRE_CLEAR:     return "clear";
        case FIRE_WARNING:   return "warning";
        case FIRE_ALERT:     return "alert";
        case FIRE_CONFIRMED: return "confirmed";
        default:             return "unknown";
    }
}

FireDetectionEngine::FireDetectionEngine()
    : _last_state(FIRE_CLEAR), _last_confidence(0.0f), _act_count(0) {

    // Load thresholds from config.h
    _thresh_mq2     = FS_THRESH_MQ2_PPM;
    _thresh_mlx     = FS_THRESH_MLX90614_C;
    _thresh_sht     = FS_THRESH_SHT40_C;
    _thresh_bme_gas = FS_THRESH_BME680_GAS;
    _thresh_ds18    = FS_THRESH_DS18B20_C;
    _thresh_amg     = FS_THRESH_AMG8833_C;

    _fusion_min     = FS_FUSION_MIN_SENSORS;
    _fusion_window  = FS_FUSION_WINDOW_MS;

    _w_smoke   = FS_CONF_SMOKE_WEIGHT;
    _w_temp    = FS_CONF_TEMP_WEIGHT;
    _w_gas     = FS_CONF_GAS_WEIGHT;
    _w_thermal = FS_CONF_THERMAL_WEIGHT;

    memset(_activations, 0, sizeof(_activations));
}

void FireDetectionEngine::_prune_activations(uint32_t now) {
    uint8_t write_idx = 0;
    for (uint8_t i = 0; i < _act_count; i++) {
        if (now - _activations[i].timestamp < _fusion_window) {
            if (write_idx != i) _activations[write_idx] = _activations[i];
            write_idx++;
        }
    }
    _act_count = write_idx;
}

void FireDetectionEngine::_add_activation(const char *name,
                                            float weight,
                                            uint32_t now) {
    // Check if this sensor already has a recent activation
    for (uint8_t i = 0; i < _act_count; i++) {
        if (strncmp(_activations[i].sensor_name, name, 16) == 0) {
            _activations[i].timestamp = now;  // refresh
            return;
        }
    }

    if (_act_count < MAX_ACTIVATIONS) {
        strncpy(_activations[_act_count].sensor_name, name, 16);
        _activations[_act_count].sensor_name[15] = '\0';
        _activations[_act_count].timestamp = now;
        _activations[_act_count].confidence_weight = weight;
        _act_count++;
    }
}

float FireDetectionEngine::_calc_confidence() {
    float conf = 0.0f;
    for (uint8_t i = 0; i < _act_count; i++) {
        conf += _activations[i].confidence_weight;
    }
    return constrain(conf, 0.0f, 1.0f);
}

uint8_t FireDetectionEngine::_count_thermal_hotspots(
        const SensorReading &r, float &max_c) {
    if (!r.thermal_valid) {
        max_c = NAN;
        return 0;
    }

    uint8_t count = 0;
    max_c = -273.15f;

    for (uint8_t i = 0; i < 64; i++) {
        float t = r.thermal_grid[i];
        if (t > max_c) max_c = t;
        if (t >= FS_THERMAL_HOTSPOT_MIN_C) count++;
    }

    return count;
}

bool FireDetectionEngine::_check_thresholds(const SensorReading &r,
                                              DetectionResult &dr) {
    uint8_t triggered = 0;
    dr.triggered_names[0] = '\0';
    uint32_t now = millis();

    // MQ-2 smoke
    if (r.smoke_ppm > _thresh_mq2) {
        _add_activation("mq2", _w_smoke, now);
        triggered++;
        strcat(dr.triggered_names, "mq2,");
    }

    // MLX90614 IR object temp
    if (!isnan(r.ir_object_c) && r.ir_object_c > _thresh_mlx) {
        _add_activation("mlx90614", _w_temp, now);
        triggered++;
        strcat(dr.triggered_names, "mlx90614,");
    }

    // SHT40 ambient temp
    if (!isnan(r.temp_c) && r.temp_c > _thresh_sht) {
        _add_activation("sht40", _w_temp, now);
        triggered++;
        strcat(dr.triggered_names, "sht40,");
    }

    // BME680 gas resistance (lower = more VOCs)
    if (!isnan(r.gas_resistance) && r.gas_resistance < _thresh_bme_gas) {
        _add_activation("bme680", _w_gas, now);
        triggered++;
        strcat(dr.triggered_names, "bme680,");
    }

    // DS18B20 external temp
    if (!isnan(r.ext_temp_c) && r.ext_temp_c > _thresh_ds18) {
        _add_activation("ds18b20", _w_temp, now);
        triggered++;
        strcat(dr.triggered_names, "ds18b20,");
    }

    // AMG8833 thermal array — any pixel above threshold
    if (r.thermal_valid) {
        float max_c;
        uint8_t hotspots = _count_thermal_hotspots(r, max_c);
        if (hotspots >= FS_THERMAL_HOTSPOT_MIN_PX) {
            _add_activation("amg8833", _w_thermal, now);
            triggered++;
            strcat(dr.triggered_names, "amg8833,");
        }
        dr.thermal_hotspot_count = hotspots;
        dr.thermal_hotspot_max_c = max_c;
    }

    // Remove trailing comma
    size_t len = strlen(dr.triggered_names);
    if (len > 0 && dr.triggered_names[len - 1] == ',')
        dr.triggered_names[len - 1] = '\0';

    dr.triggered_count = triggered;
    return triggered > 0;
}

bool FireDetectionEngine::_check_fusion(DetectionResult &dr) {
    _prune_activations(millis());
    return _act_count >= _fusion_min;
}

DetectionResult FireDetectionEngine::detect(const SensorReading &r) {
    uint32_t start = millis();

    DetectionResult dr;
    dr.state = FIRE_CLEAR;
    dr.confidence = 0.0f;
    dr.triggered_count = 0;
    dr.triggered_names[0] = '\0';
    dr.thermal_hotspot_count = 0;
    dr.thermal_hotspot_max_c = NAN;
    dr.timestamp = millis();
    dr.latency_ms = 0;
    dr.reason[0] = '\0';

    if (!r.valid) {
        strcpy(dr.reason, "no valid sensor data");
        dr.latency_ms = millis() - start;
        return dr;
    }

    // Step 1: single-sensor thresholds
    bool any_triggered = _check_thresholds(r, dr);

    if (!any_triggered) {
        // No sensors triggered — clear state
        _act_count = 0;
        _last_state = FIRE_CLEAR;
        _last_confidence = 0.0f;
        strcpy(dr.reason, "clear");
        dr.latency_ms = millis() - start;
        return dr;
    }

    // Step 2: multi-sensor fusion
    bool fusion_passed = _check_fusion(dr);

    if (fusion_passed) {
        dr.state = FIRE_ALERT;
        dr.confidence = _calc_confidence();
        strcpy(dr.reason, "multi-sensor fusion");
    } else {
        dr.state = FIRE_WARNING;
        dr.confidence = _calc_confidence() * 0.5f;  // half confidence for single sensor
        strcpy(dr.reason, "single-sensor threshold");
    }

    _last_state = dr.state;
    _last_confidence = dr.confidence;
    dr.latency_ms = millis() - start;
    return dr;
}