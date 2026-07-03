# open-fire-suppression

An open-source fire detection and suppression control system running on Raspberry Pi 5 (8GB RAM).

> ⚠️ **USE AT YOUR OWN RISK.** This software is provided as-is for educational and research purposes. Any deployment in a real-world fire protection scenario requires professional engineering review, installation by certified technicians, and sign-off by your local Authority Having Jurisdiction (AHJ).
>
> 🏛️ **REGULATORY COMPLIANCE:** Before activating suppression hardware, your system must pass inspection by a licensed fire protection engineer and obtain module installation certification from the appropriate local or national fire safety authority. Failure to do so may violate fire codes, invalidate insurance coverage, and create serious life safety hazards.

---

## Overview

**open-fire-suppression** is the most comprehensive open-source fire detection and suppression control system available. It combines multi-sensor fusion, AI-powered video fire detection, thermal imaging, safety interlocks, adaptive learning, and regulatory compliance tools into a single hardened platform.

## Complete Feature List

### Core Detection (1–8)
| # | Feature | Description |
|---|---------|-------------|
| 1 | **Multi-sensor fusion** | Smoke (MQ-2), temp (SHT40, MLX90614), humidity, IR thermal (AMG8833, MLX90640), VOC (ENS160, BME680), camera |
| 2 | **Sensor health monitoring** | Every sensor tracked with rolling health window; degraded sensors isolated automatically |
| 3 | **Single-sensor threshold detection** | Immediate WARNING on any sensor exceeding configured thresholds |
| 4 | **Multi-sensor fusion detection** | ALERT only when correlated sensors agree within configurable time window |
| 5 | **False-positive suppression** | Cooking, welding, exhaust filtered via temporal and heuristic analysis |
| 6 | **Thermal hotspot detection** | AMG8833 8×8 / MLX90640 32×24 thermal cameras localize fire to room sector |
| 7 | **Pi Camera Module 3 capture** | HSV color analysis for visible flame detection in video stream |
| 8 | **Detection latency tracking** | Every detection path timed and logged for performance audit |

### AI & ML Detection (9–14)
| # | Feature | Description |
|---|---------|-------------|
| 9 | **TFLite fire/smoke model** | On-device YOLOv8-style object detection for fire and smoke bounding boxes |
| 10 | **Kalman filter sensor fusion** | Latent "fire intensity" state estimation smooths noise and tracks trends |
| 11 | **IR flame flicker analysis** | FFT on IR time-series distinguishes flames (1–12 Hz) from static heat sources |
| 12 | **ML false-positive classifier** | On-device Random Forest learns local patterns; rule-based fallback |
| 13 | **Thermal drift compensation** | Auto-corrects IR sensor drift using die-temperature reference |
| 14 | **Smoke plume direction tracking** | Multi-point triangulation estimates smoke origin and spread vector |

### Safety & Resilience (15–30)
| # | Feature | Description |
|---|---------|-------------|
| 15 | **System arming / disarming** | Armed state required before any suppression can activate |
| 16 | **Emergency stop** | Physical E-stop immediately blocks all actuation, latches until reset |
| 17 | **Maintenance mode** | Safe testing mode with suppression disabled, diagnostics enabled |
| 18 | **Tamper detection** | Enclosure breach or unauthorized config change triggers security lockout |
| 19 | **Watchdog timer** | 30-second heartbeat; system auto-disarms if heartbeats stop |
| 20 | **Sensor failure graceful degradation** | Failed sensors redistributed; >50% failure switches to emergency camera-only mode |
| 21 | **Detection engine timeout guard** | 2-second timeout with fallback to fast threshold mode |
| 22 | **SQLite corruption recovery** | WAL robustness, integrity checks, automatic backup restore, JSON fallback logging |
| 23 | **Memory leak prevention** | Periodic GC, bounded queues, tracemalloc profiling with high-water alerts |
| 24 | **Network partition store-and-forward** | Offline message queue replays alerts when connectivity returns |
| 25 | **Relay fuse monitoring** | Per-relay health tracking; failed relays isolated |
| 26 | **Config corruption recovery** | Atomic file writes, last-known-good backup, validation on every reload |
| 27 | **Clock drift / RTC monitoring** | DS3231 RTC support; NTP sync confidence tracking |
| 28 | **Process death resilience** | systemd watchdog heartbeat; dual-process architecture ready |
| 29 | **Water ingress detection** | Enclosure moisture sensor alerts before electronics are damaged |
| 30 | **Vibration / earthquake sensor** | MPU6050/SW-420 seismic detection; auto-arms suppression for 30 min post-quake |

### Suppression & Actuation (31–37)
| # | Feature | Description |
|---|---------|-------------|
| 31 | **Relay control** | GPIO relay management with dry-run test, activation feedback, manual override |
| 32 | **Pre-activation warning** | Configurable buzzer warning before suppression releases |
| 33 | **Suppression feedback** | Confirmation that relays actually toggled; fault detection |
| 34 | **Water mist zone targeting** | Thermal-camera-guided activation of only nearest nozzle(s) |
| 35 | **Smart sprinkler valve integration** | Addressable valves with flow confirmation and pressure monitoring |
| 36 | **CO / carbon monoxide detection** | Electrochemical CO sensor; alerts before smoke is visible |
| 37 | **Voice alert system (TTS)** | Spoken evacuation instructions via pyttsx3 offline synthesis |

### Alerting & Notification (38–48)
| # | Feature | Description |
|---|---------|-------------|
| 38 | **Local buzzer** | Hardware buzzer with priority-based patterns |
| 39 | **SMS alerts (Twilio)** | Cellular SMS to configured numbers with rate limiting |
| 40 | **Email alerts (SMTP)** | SMTP email with TLS support |
| 41 | **Webhook notifications** | HTTP POST to any endpoint with JSON payload |
| 42 | **Hermes Agent bridge** | Rich structured notifications to Hermes for Telegram/SMS relay |
| 43 | **MQTT IoT integration** | Publish to any MQTT broker; Home Assistant auto-discovery |
| 44 | **Haptic alerts (BLE)** | Vibration patterns to smartwatches / wearable pagers for deaf/hard-of-hearing |
| 45 | **LED evacuation guidance** | WS2812 strips show dynamic escape routes away from fire zone |
| 46 | **Multi-zone architecture** | Each zone has independent sensors, thresholds, and relays |
| 47 | **Store-and-forward queue** | Persistent offline notification queue survives reboots |
| 48 | **Rate limiting** | Prevents alert spam; critical alerts bypass limits |

### Telemetry & Logging (49–58)
| # | Feature | Description |
|---|---------|-------------|
| 49 | **SQLite event logging** | Timestamped event database with sensor history and detection results |
| 50 | **Log rotation** | Automatic archival when database exceeds configurable size |
| 51 | **Tamper-evident audit log** | SHA-256 hash chain detects log tampering; HTML reports exportable |
| 52 | **Cloud telemetry backup** | Encrypted upload of critical events to S3/Backblaze/MinIO |
| 53 | **Air Quality Index (AQI)** | EPA-style AQI from PM2.5/VOC for public health publishing |
| 54 | **Real-time dashboard** | FastAPI web UI with live sensor readings and fire state |
| 55 | **Dashboard WebSocket** | Push updates to browser without polling |
| 56 | **Historical data query API** | REST endpoints for sensor history and event search |
| 57 | **Mobile app API** | Arm/disarm, status view, push notification, alert acknowledge endpoints |
| 58 | **Automated incident reports** | Auto-generated PDF/HTML post-fire reports for insurance and fire marshal |

### Power & Environmental (59–66)
| # | Feature | Description |
|---|---------|-------------|
| 59 | **Battery voltage monitoring** | Real-time UPS battery level via I2C ADC |
| 60 | **Low battery warning** | Alert when battery drops below configurable threshold |
| 61 | **Safe shutdown on low battery** | Graceful system shutdown before power is lost |
| 62 | **AC power loss detection** | Immediate alert on mains failure |
| 63 | **Power source tracking** | Reports battery vs. mains vs. solar |
| 64 | **Environmental baseline learning** | 48-hour auto-baseline adapts thresholds to seasonal conditions |
| 65 | **Seasonal threshold adjustment** | Month-based multipliers plus weather API integration |
| 66 | **Night vision enhancement** | IR illuminator + NoIR camera for 24/7 fire detection |

### Configuration & Management (67–74)
| # | Feature | Description |
|---|---------|-------------|
| 67 | **YAML configuration** | Human-readable config with section validation |
| 68 | **Environment variable overrides** | All config keys overridable via `FIRE_*` env vars |
| 69 | **Hot reload (SIGUSR1)** | Runtime config reload without restart |
| 70 | **Remote configuration API** | Update thresholds via HTTP; persisted atomically |
| 71 | **OTA updates** | Git-based over-the-air update with systemd restart |
| 72 | **Startup diagnostics** | I2C scan, sensor comm test, relay dry-run, camera capture |
| 73 | **Predictive maintenance** | Sensor drift tracking alerts before hardware fails |
| 74 | **Regulatory compliance self-check** | NFPA 72 rule engine checks spacing, coverage, battery, notifications |

### Networking & Mesh (75–77)
| # | Feature | Description |
|---|---------|-------------|
| 75 | **Neighbor mesh network** | ESP-NOW/LoRa inter-unit communication; fire alerts propagate to neighbors |
| 76 | **Network partition resilience** | Alerts queue locally, replay on reconnect |
| 77 | **Cellular backup priority** | SMS channel promoted when WiFi fails |

### Accessibility (78–79)
| # | Feature | Description |
|---|---------|-------------|
| 78 | **Haptic alerts** | BLE wearable vibration for deaf/hard-of-hearing |
| 79 | **Voice evacuation instructions** | Spoken alerts with severity-appropriate messaging |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Sensor Layer    │  MQ-2 │ SHT40 │ MLX90614 │ AMG8833 │ ... │
├─────────────────────────────────────────────────────────────┤
│  Detection Engine│  Sensor Fusion → Kalman → TFLite → Flicker│
├─────────────────────────────────────────────────────────────┤
│  Safety Layer    │  Interlocks │ Arming │ Watchdog │ E-Stop  │
├─────────────────────────────────────────────────────────────┤
│  Actuation Layer │  Relay │ Sprinkler │ Mist Targeting │ LED  │
├─────────────────────────────────────────────────────────────┤
│  Alert Layer     │  Buzzer │ TTS │ SMS │ Email │ MQTT │ BLE  │
├─────────────────────────────────────────────────────────────┤
│  Telemetry       │  SQLite │ Audit │ Cloud │ AQI │ Dashboard│
├─────────────────────────────────────────────────────────────┤
│  Resilience      │  Stay-Alive │ Mesh │ Compliance │ Maintain│
├─────────────────────────────────────────────────────────────┤
│  Power           │  UPS │ Battery │ Safe Shutdown │ RTC      │
└─────────────────────────────────────────────────────────────┘
```

## Hardware Requirements

See `docs/sensor_research.md` and `docs/battery_research.md` for full component details, wiring diagrams, and interface specifications.

## Installation

```bash
# Raspberry Pi OS (Bookworm)
sudo apt update
sudo apt install -y python3-pip python3-venv libcamera-dev
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running Tests

All **161 tests pass**. Run the full suite:

```bash
PYTHONPATH=src pytest tests/ -v
```

| Test Suite | Count |
|-----------|-------|
| Core (config, sensors, detection, safety, power, telemetry) | 106 |
| Original 10 Improvements (TFLite, Kalman, zones, diagnostics, baseline, targeting, audit, notifications) | — |
| **Resilience & Stay-Alive** (10 bottlenecks) | +10 |
| **Hermes Bridge** (humidity, fire, status, error, heartbeat) | +6 |
| **20 Additional Improvements** (thermal drift, water ingress, flicker, ML FP, voice, LEDs, cloud, maintenance, sprinklers, plume, haptic, AQI, seasonal, mobile API, CO, vibration, night vision, compliance, mesh, incident report) | +39 |
| **Total** | **161** |

## Compliance & Safety Notice

1. **This is not a certified fire alarm system.** It is open-source research software.
2. **NFPA 72**, **NFPA 10**, and local codes govern real fire suppression installations.
3. **Professional certification** by a licensed fire protection engineer is mandatory before connecting suppression hardware.
4. **Insurance** may not cover damages from uncertified fire protection systems.
5. **Liability** rests with the installer and operator, not the authors or contributors.

## License

MIT — See `LICENSE` for full terms. Use responsibly.
