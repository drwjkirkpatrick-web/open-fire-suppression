/**
 * actuation.h — Suppression relay control for ESP32
 *
 * Ports the Python RelayController to C++.
 * Manages relay outputs with:
 *   - Configurable active-high/low logic
 *   - Pre-activation buzzer warning (configurable duration)
 *   - Suppression duration timeout
 *   - Flow sensor feedback confirmation
 *   - Manual override button
 *
 * Mirrors: src/fire_suppression/actuation/relay.py
 */
#ifndef FIRE_SUPPRESSION_ACTUATION_H
#define FIRE_SUPPRESSION_ACTUATION_H

#include <Arduino.h>
#include "../config.h"

// ── Actuation State (mirrors Python ActuationState enum) ─────────
enum ActuationState {
    ACT_IDLE          = 0,
    ACT_PRE_ACTIVATION = 1,  // warning countdown running
    ACT_ACTIVE         = 2,  // suppression relays engaged
    ACT_COOLDOWN       = 3,  // post-suppression cooldown
    ACT_ERROR          = 4   // flow sensor reported failure
};

const char* actuation_state_str(ActuationState s);

// ── Relay Controller ─────────────────────────────────────────────
class RelayController {
public:
    RelayController();

    void begin();                           // set pin modes, ensure OFF

    // Called every loop tick — manages state machine
    void update();

    // Request suppression (returns false if safety disallows)
    bool activate(uint8_t zone_mask = 0xFF, const char *reason = "");

    // Stop suppression immediately
    void deactivate();

    // State queries
    ActuationState state() const { return _state; }
    bool is_active() const { return _state == ACT_ACTIVE; }
    bool in_pre_activation() const { return _state == ACT_PRE_ACTIVATION; }

    // Individual relay control
    void relay_on(uint8_t index);
    void relay_off(uint8_t index);
    void all_relays_off();

    // Flow sensor check
    bool flow_confirmed() const;

    // Pre-activation progress (0.0–1.0)
    float pre_activation_progress() const;

    // Time remaining in current state (seconds)
    float time_remaining_s() const;

private:
    ActuationState _state;
    uint8_t  _relay_pins[FS_RELAY_COUNT];
    bool     _active_low;
    uint32_t _state_start;       // millis() when state began
    uint32_t _pre_activation_s;  // warning duration
    uint32_t _suppress_duration_s;
    uint8_t  _active_zone_mask;
    char     _reason[32];
    bool     _flow_ok;

    void _enter_state(ActuationState s);
    void _set_relay(uint8_t idx, bool on);
};

#endif // FIRE_SUPPRESSION_ACTUATION_H