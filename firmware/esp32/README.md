# ESP32 Firmware — open-fire-suppression

Lightweight fire detection & suppression sensor node for ESP32.

Part of [open-fire-suppression](../../README.md) — the full Raspberry Pi 5 system.
The ESP32 node operates **independently**: it detects, suppresses, and alerts
even if WiFi/MQTT to the Pi 5 dashboard is lost.

## Hardware

| Component | ESP32 Pin | Bus | Notes |
|-----------|-----------|-----|-------|
| MQ-2 smoke | GPIO 34 | ADC1 | 12-bit, 0–3.3V |
| SHT40 temp/humidity | 0x44 | I2C | SDA=21, SCL=22 |
| MLX90614 IR temp | 0x5A | I2C | Object + ambient temp |
| BME680 env/gas | 0x77 | I2C | Temp + humidity + pressure + gas |
| AMG8833 8×8 thermal | 0x69 | I2C | Hotspot localization |
| DS18B20 ext temp | GPIO 4 | OneWire | 12-bit resolution |
| 4-ch relay module | 26,27,14,12 | GPIO | Active-low |
| Flow sensor | GPIO 35 | ADC1 | Suppression confirmation |
| Buzzer | GPIO 25 | PWM | Priority-based patterns |
| WS2812 LED strip | GPIO 2 | Data | 8 LEDs, evacuation guidance |
| Arm switch | GPIO 32 | GPIO | Pull-up, active-low |
| E-stop button | GPIO 33 | GPIO | Pull-up, latching |
| Tamper switch | GPIO 13 | GPIO | Pull-up, active-low |
| Maintenance switch | GPIO 15 | GPIO | Pull-up, active-low |
| Manual button | GPIO 0 | GPIO | BOOT button (dual-use) |

## Build & Flash

```bash
# Install PlatformIO Core
pip install platformio

# Build firmware
cd firmware/esp32
pio run

# Upload to ESP32 (connect via USB)
pio run -t upload

# Serial monitor
pio device monitor
```

## Run Tests (native, no hardware needed)

```bash
pio test -e native
```

## Architecture

```
src/
├── main.ino              # Setup + main loop: sensors → detect → safety → actuate → telemetry
├── config.h              # All pin assignments, thresholds, WiFi/MQTT settings
├── sensors/
│   ├── sensors.h         # BaseSensor + SensorReading + SensorHealth structs
│   └── sensors.cpp       # MQ-2, SHT40, MLX90614, BME680, AMG8833, DS18B20 + SensorManager
├── detection/
│   ├── detection.h       # FireState enum + DetectionResult + FireDetectionEngine
│   └── detection.cpp     # Threshold check → fusion → confidence scoring
├── safety/
│   ├── safety.h          # SafetyState enum + SafetyInterlock
│   └── safety.cpp        # Arming, E-stop latch, tamper, maintenance, watchdog
├── actuation/
│   ├── actuation.h       # ActuationState enum + RelayController
│   └── actuation.cpp     # State machine: IDLE→PRE_ACTIVATION→ACTIVE→COOLDOWN
└── telemetry/
    ├── telemetry.h       # Telemetry class (WiFi + MQTT + buzzer + LED)
    └── telemetry.cpp    # JSON status publish, buzzer patterns, LED animations
```

## Detection Strategy

Mirrors the Raspberry Pi 5 Python detection engine:

1. **Single-sensor threshold** → `WARNING`
   - MQ-2 smoke > 300 ppm
   - MLX90614 IR object temp > 80°C
   - SHT40 ambient temp > 60°C
   - BME680 gas resistance < 5000Ω (lower = more VOCs)
   - DS18B20 external temp > 70°C
   - AMG8833 any pixel > 60°C (min 4 pixels = hotspot)

2. **Multi-sensor fusion** → `ALERT`
   - ≥ 2 sensors triggered within 5-second window
   - Weighted confidence: smoke 30%, temp 30%, gas 20%, thermal 20%

3. **Suppression activation** → `CONFIRMED`
   - Only if safety interlock is ARMED
   - Pre-activation buzzer warning (10 seconds)
   - Relay engagement for 60 seconds
   - Flow sensor confirmation check

## Safety Interlocks

- **Arming switch** (GPIO 32): System must be ARMED before any actuation
- **E-stop** (GPIO 33): Latches until manual reset — blocks all actuation
- **Tamper** (GPIO 13): Enclosure breach → security lockout
- **Maintenance mode** (GPIO 15): Disables suppression, enables diagnostics
- **Watchdog**: 30-second heartbeat — auto-disarms if heartbeats stop

## MQTT Topics

Published to `fire_suppression/` base topic:

| Topic | Content |
|-------|---------|
| `status` | Full JSON status (every 5s) |
| `alert` | Same JSON, published on WARNING+ for immediate attention |

JSON payload includes: version, uptime, free heap, all sensor values,
detection state/confidence/triggered sensors, safety state, actuation state.

## Standalone Operation

If WiFi or MQTT is unavailable, the ESP32 continues:
- Reading sensors and running detection
- Driving buzzer and LED alerts
- Actuating suppression (if armed)

Telemetry is queued and published when connectivity returns.

## Regulatory Disclaimer

**This is not a certified fire alarm system.** It is open-source research
firmware. Any deployment requires professional engineering review, certified
installation, and AHJ sign-off. See the root [README](../../README.md) for
full disclaimers.

## License

MIT — See root `LICENSE` file.