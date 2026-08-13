/**
 * safety.h — Safety interlock system for ESP32
 *
 * Ports the Python SafetyInterlock to C++.
 * The system must be ARMED before any suppression actuation can occur.
 * Safety-critical inputs (E-stop, tamper, maintenance) are monitored
 * continuously via debounced GPIO.
 *
 * Mirrors: src/fire_suppression/safety/interlock.py
 */
#ifndef FIRE_SUPPRESSION_SAFETY_H
#define FIRE_SUPPRESSION_SAFETY_H

#include <Arduino.h>

// ── Safety State (mirrors Python SafetyState enum) ───────────────
enum SafetyState {
    SAFETY_DISARMED       = 0,
    SAFETY_ARMED          = 1,
    SAFETY_MAINTENANCE    = 2,
    SAFETY_EMERGENCY_STOP = 3,
    SAFETY_TAMPERED       = 4
};

const char* safety_state_str(SafetyState s);

// ── Safety Interlock ─────────────────────────────────────────────
class SafetyInterlock {
public:
    SafetyInterlock();

    void begin();                          // init GPIO with pull-ups
    void update();                         // call every loop — debounce + state

    SafetyState state() const { return _state; }
    bool can_actuate() const;              // true only if ARMED

    void arm();                            // software arm
    void disarm();                         // software disarm
    void reset_emergency_stop();           // clear E-stop latch

    // Watchdog
    void feed_watchdog();
    bool watchdog_ok() const;

    // Status for telemetry
    bool armed() const     { return _state == SAFETY_ARMED; }
    bool e_stop_active() const { return _e_stop_latched; }
    bool tamper_active() const { return _tamper_active; }
    bool maintenance_mode() const { return _state == SAFETY_MAINTENANCE; }

private:
    SafetyState _state;
    bool        _e_stop_latched;
    bool        _tamper_active;
    uint32_t    _watchdog_last_feed;

    // Debounce state per pin
    bool        _last_arm_raw;
    bool        _last_estop_raw;
    bool        _last_tamper_raw;
    bool        _last_maint_raw;
    uint32_t    _debounce_timer;
    static const uint32_t DEBOUNCE_MS = 50;

    void _check_transitions();
};

#endif // FIRE_SUPPRESSION_SAFETY_H