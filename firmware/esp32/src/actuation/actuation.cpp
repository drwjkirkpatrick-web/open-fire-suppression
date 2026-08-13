/**
 * actuation.cpp — Relay control implementation for ESP32
 *
 * State machine: IDLE → PRE_ACTIVATION → ACTIVE → COOLDOWN → IDLE
 * Pre-activation sounds buzzer for FS_PRE_ACTIVATION_S seconds.
 * Active drives relays for FS_SUPPRESS_DURATION_S seconds.
 * Flow sensor checked during ACTIVE for confirmation.
 */
#include "actuation/actuation.h"
#include "../config.h"

const char* actuation_state_str(ActuationState s) {
    switch (s) {
        case ACT_IDLE:           return "idle";
        case ACT_PRE_ACTIVATION: return "pre_activation";
        case ACT_ACTIVE:         return "active";
        case ACT_COOLDOWN:       return "cooldown";
        case ACT_ERROR:          return "error";
        default:                 return "unknown";
    }
}

RelayController::RelayController()
    : _state(ACT_IDLE), _active_low(FS_RELAY_ACTIVE_LOW),
      _state_start(0), _pre_activation_s(FS_PRE_ACTIVATION_S),
      _suppress_duration_s(FS_SUPPRESS_DURATION_S),
      _active_zone_mask(0), _flow_ok(false) {

    // Copy relay pins from config
    uint8_t pins[] = FS_RELAY_PINS;
    memcpy(_relay_pins, pins, sizeof(_relay_pins));
    _reason[0] = '\0';
}

void RelayController::begin() {
    for (uint8_t i = 0; i < FS_RELAY_COUNT; i++) {
        pinMode(_relay_pins[i], OUTPUT);
        _set_relay(i, false);  // ensure all OFF at startup
    }
    pinMode(FS_FLOW_SENSOR_PIN, INPUT);
    pinMode(FS_MANUAL_BUTTON_PIN, INPUT_PULLUP);
}

void RelayController::_set_relay(uint8_t idx, bool on) {
    if (idx >= FS_RELAY_COUNT) return;

    // Active-low: LOW = ON, HIGH = OFF
    // Active-high: HIGH = ON, LOW = OFF
    bool level = _active_low ? !on : on;
    digitalWrite(_relay_pins[idx], level ? HIGH : LOW);
}

void RelayController::relay_on(uint8_t index) {
    _set_relay(index, true);
}

void RelayController::relay_off(uint8_t index) {
    _set_relay(index, false);
}

void RelayController::all_relays_off() {
    for (uint8_t i = 0; i < FS_RELAY_COUNT; i++) {
        _set_relay(i, false);
    }
}

void RelayController::_enter_state(ActuationState s) {
    _state = s;
    _state_start = millis();
}

bool RelayController::activate(uint8_t zone_mask, const char *reason) {
    if (_state == ACT_ACTIVE || _state == ACT_PRE_ACTIVATION) {
        return true;  // already activating
    }

    _active_zone_mask = zone_mask;
    strncpy(_reason, reason, sizeof(_reason) - 1);
    _reason[sizeof(_reason) - 1] = '\0';
    _enter_state(ACT_PRE_ACTIVATION);
    return true;
}

void RelayController::deactivate() {
    all_relays_off();
    _enter_state(ACT_IDLE);
    _reason[0] = '\0';
}

void RelayController::update() {
    uint32_t now = millis();
    uint32_t elapsed_s = (now - _state_start) / 1000;

    switch (_state) {
        case ACT_IDLE:
            // Check manual button (GPIO 0 = BOOT button)
            if (digitalRead(FS_MANUAL_BUTTON_PIN) == LOW) {
                delay(50);  // crude debounce
                if (digitalRead(FS_MANUAL_BUTTON_PIN) == LOW) {
                    activate(0xFF, "manual_button");
                }
            }
            break;

        case ACT_PRE_ACTIVATION:
            // Sound buzzer warning for pre-activation duration
            if (elapsed_s >= _pre_activation_s) {
                // Engage relays
                for (uint8_t i = 0; i < FS_RELAY_COUNT; i++) {
                    if (_active_zone_mask & (1 << i)) {
                        _set_relay(i, true);
                    }
                }
                _enter_state(ACT_ACTIVE);
            }
            break;

        case ACT_ACTIVE: {
            // Check flow sensor
            int flow_raw = analogRead(FS_FLOW_SENSOR_PIN);
            _flow_ok = (flow_raw > 2000);  // ADC threshold for flow

            // Check suppression duration
            if (elapsed_s >= _suppress_duration_s) {
                all_relays_off();
                _enter_state(ACT_COOLDOWN);
            }
            break;
        }

        case ACT_COOLDOWN:
            // 30 s cooldown before returning to idle
            if (elapsed_s >= 30) {
                _enter_state(ACT_IDLE);
                _reason[0] = '\0';
            }
            break;

        case ACT_ERROR:
            // Stay in error until explicitly deactivated
            break;
    }
}

bool RelayController::flow_confirmed() const {
    return _flow_ok;
}

float RelayController::pre_activation_progress() const {
    if (_state != ACT_PRE_ACTIVATION) return 0.0f;
    uint32_t elapsed = (millis() - _state_start) / 1000;
    return constrain((float)elapsed / _pre_activation_s, 0.0f, 1.0f);
}

float RelayController::time_remaining_s() const {
    uint32_t elapsed_s = (millis() - _state_start) / 1000;

    switch (_state) {
        case ACT_PRE_ACTIVATION:
            return (float)(_pre_activation_s - elapsed_s);
        case ACT_ACTIVE:
            return (float)(_suppress_duration_s - elapsed_s);
        case ACT_COOLDOWN:
            return (float)(30 - elapsed_s);
        default:
            return 0.0f;
    }
}