/**
 * safety.cpp — Safety interlock implementation for ESP32
 *
 * Manages arming, E-stop, tamper, maintenance mode, and watchdog.
 * All inputs are debounced with 50ms settling time.
 * E-stop latches until explicitly reset.
 */
#include "safety/safety.h"
#include "../config.h"

const char* safety_state_str(SafetyState s) {
    switch (s) {
        case SAFETY_DISARMED:       return "disarmed";
        case SAFETY_ARMED:          return "armed";
        case SAFETY_MAINTENANCE:    return "maintenance";
        case SAFETY_EMERGENCY_STOP: return "emergency_stop";
        case SAFETY_TAMPERED:       return "tampered";
        default:                    return "unknown";
    }
}

SafetyInterlock::SafetyInterlock()
    : _state(SAFETY_DISARMED), _e_stop_latched(false),
      _tamper_active(false), _watchdog_last_feed(0),
      _last_arm_raw(false), _last_estop_raw(false),
      _last_tamper_raw(false), _last_maint_raw(false),
      _debounce_timer(0) {}

void SafetyInterlock::begin() {
    // Configure inputs with pull-ups (switches to GND when pressed)
    pinMode(FS_ARM_PIN,   INPUT_PULLUP);
    pinMode(FS_ESTOP_PIN, INPUT_PULLUP);
    pinMode(FS_TAMPER_PIN, INPUT_PULLUP);
    pinMode(FS_MAINT_PIN, INPUT_PULLUP);

    _watchdog_last_feed = millis();
    _debounce_timer = millis();

    // Read initial state
    _last_arm_raw   = digitalRead(FS_ARM_PIN) == LOW;
    _last_estop_raw = digitalRead(FS_ESTOP_PIN) == LOW;
    _last_tamper_raw = digitalRead(FS_TAMPER_PIN) == LOW;
    _last_maint_raw = digitalRead(FS_MAINT_PIN) == LOW;

    // Initial state assessment
    if (_last_estop_raw) {
        _e_stop_latched = true;
        _state = SAFETY_EMERGENCY_STOP;
    } else if (_last_tamper_raw) {
        _tamper_active = true;
        _state = SAFETY_TAMPERED;
    } else if (_last_maint_raw) {
        _state = SAFETY_MAINTENANCE;
    } else if (_last_arm_raw) {
        _state = SAFETY_ARMED;
    } else {
        _state = SAFETY_DISARMED;
    }
}

void SafetyInterlock::update() {
    uint32_t now = millis();

    // Debounce: only check after DEBOUNCE_MS since last check
    if (now - _debounce_timer < DEBOUNCE_MS) return;
    _debounce_timer = now;

    bool arm_raw   = digitalRead(FS_ARM_PIN) == LOW;
    bool estop_raw = digitalRead(FS_ESTOP_PIN) == LOW;
    bool tamper_raw = digitalRead(FS_TAMPER_PIN) == LOW;
    bool maint_raw = digitalRead(FS_MAINT_PIN) == LOW;

    // E-stop latches — once pressed, stays until reset
    if (estop_raw) {
        _e_stop_latched = true;
    }

    // Tamper detection
    _tamper_active = tamper_raw;

    // Store for external queries
    _last_arm_raw = arm_raw;
    _last_estop_raw = estop_raw;
    _last_tamper_raw = tamper_raw;
    _last_maint_raw = maint_raw;

    _check_transitions();
}

void SafetyInterlock::_check_transitions() {
    // Priority: E-stop > Tamper > Maintenance > Arm/Disarm

    if (_e_stop_latched) {
        _state = SAFETY_EMERGENCY_STOP;
        return;
    }

    if (_tamper_active) {
        _state = SAFETY_TAMPERED;
        return;
    }

    if (_last_maint_raw) {
        _state = SAFETY_MAINTENANCE;
        return;
    }

    // Arm switch toggles between ARMED and DISARMED
    if (_last_arm_raw && _state != SAFETY_ARMED) {
        _state = SAFETY_ARMED;
    } else if (!_last_arm_raw && _state == SAFETY_ARMED) {
        _state = SAFETY_DISARMED;
    }
}

bool SafetyInterlock::can_actuate() const {
    return _state == SAFETY_ARMED;
}

void SafetyInterlock::arm() {
    if (!_e_stop_latched && !_tamper_active) {
        _state = SAFETY_ARMED;
    }
}

void SafetyInterlock::disarm() {
    if (_state == SAFETY_ARMED) {
        _state = SAFETY_DISARMED;
    }
}

void SafetyInterlock::reset_emergency_stop() {
    _e_stop_latched = false;
    _check_transitions();
}

void SafetyInterlock::feed_watchdog() {
    _watchdog_last_feed = millis();
}

bool SafetyInterlock::watchdog_ok() const {
    return (millis() - _watchdog_last_feed) < FS_WATCHDOG_TIMEOUT_MS;
}