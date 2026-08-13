/**
 * types.h — Shared types for ESP32 fire suppression
 *
 * SensorReading and SensorHealth are defined here so the detection
 * engine can use them without pulling in sensor library headers.
 */
#ifndef FIRE_SUPPRESSION_TYPES_H
#define FIRE_SUPPRESSION_TYPES_H

#include <Arduino.h>
#include <string.h>
#include <math.h>

// ── Sensor Reading (mirrors Python SensorReading dataclass) ─────
struct SensorReading {
    String  sensor_name;
    uint32_t timestamp;  // millis()
    float   smoke_ppm;
    float   temp_c;
    float   humidity_pct;
    float   ir_object_c;
    float   ir_ambient_c;
    float   gas_resistance;
    float   pressure_hpa;
    float   ext_temp_c;
    float   thermal_grid[64];  // AMG8833 8×8
    bool    thermal_valid;
    bool    valid;             // false if read failed
};

// ── Sensor Health (mirrors Python SensorHealth) ──────────────────
struct SensorHealth {
    uint32_t total_reads   = 0;
    uint32_t successful    = 0;
    uint32_t failed         = 0;
    uint32_t last_success   = 0;  // millis()
    String   last_error     = "";
    bool     ok             = true;

    float success_rate() const {
        return total_reads == 0 ? 0.0f : (float)successful / total_reads;
    }
};

#endif // FIRE_SUPPRESSION_TYPES_H