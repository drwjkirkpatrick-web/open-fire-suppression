/**
 * Arduino.h — Minimal mock for native (host) unit tests
 *
 * Provides just enough of the Arduino API for the detection engine
 * and sensor structs to compile without real hardware.
 */
#ifndef ARDUINO_H_MOCK
#define ARDUINO_H_MOCK

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <cstdio>

// ── Arduino types ────────────────────────────────────────────────
typedef uint8_t  byte;
typedef bool     boolean;
typedef uint8_t  uint8_t;
typedef uint16_t uint16_t;
typedef uint32_t uint32_t;
typedef int16_t  int16_t;
typedef int32_t  int32_t;

#define HIGH 1
#define LOW  0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2

// ── Mock functions ───────────────────────────────────────────────
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t, uint8_t) {}
inline int  digitalRead(uint8_t) { return HIGH; }
inline int  analogRead(uint8_t) { return 0; }
inline void analogReadResolution(uint8_t) {}
inline void analogSetAttenuation(uint8_t) {}
inline void delay(unsigned long) {}
inline unsigned long millis() { return 0; }
inline unsigned long micros() { return 0; }

// ── Serial mock ──────────────────────────────────────────────────
class SerialMock {
public:
    void begin(unsigned long) {}
    void printf(const char *, ...) {}
    void print(const char *) {}
    void println(const char *) {}
    void println() {}
};
extern SerialMock Serial;

// ── String mock ──────────────────────────────────────────────────
#include <string>
class String : public std::string {
public:
    String() : std::string() {}
    String(const char *s) : std::string(s) {}
    String(const std::string &s) : std::string(s) {}
    const char *c_str() const { return std::string::c_str(); }
};

// ── ESP mock ──────────────────────────────────────────────────────
struct ESPMock {
    uint32_t getFreeHeap() { return 200000; }
};
extern ESPMock ESP;

// ── Arduino math helpers ─────────────────────────────────────────
template<typename T>
inline T constrain(T val, T lo, T hi) {
    return val < lo ? lo : (val > hi ? hi : val);
}

inline float powf(float base, float exp) { return powf(base, exp); }

// ──isnan/isinf ───────────────────────────────────────────────────
#ifndef NAN
#define NAN (0.0f / 0.0f)
#endif

#endif // ARDUINO_H_MOCK