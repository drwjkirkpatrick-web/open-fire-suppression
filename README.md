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
| Original 10 Improvements (TFLite, Kalman, zones, diagnostics, baseline, targeting, audit, notifier, mobile, MQTT) | 55 |
| v0.3.0 (Resilience, Hermes bridge, Additional improvements, NFPA compliance, Kenya SMS, USB export) | 40 |
| v0.4.0 (20 next-gen modules + 2 audio upgrades + next-gen tech + resilience stay-alive) | 76 |
| v0.5.0 (Anti-tamper USB update, Pi-optimized blockchain, file integrity monitor) | 33 |
| **Total** | **310** |

### NFPA 72 & NFPA 10 Regulatory Compliance (80–93)
| # | Feature | Description |
|---|---------|-------------|
| 80 | **NFPA 72 rule engine** | 30+ compliance checks: detection spacing, notification, power, monitoring, testing, control |
| 81 | **NFPA 10 extinguisher compliance** | Monthly/annual/hydrostatic test tracking with specific remediation steps |
| 82 | **Compliance gap reports** | Auto-generated reports showing exactly what's non-compliant and how to fix it |
| 83 | **Owner maintenance alerts** | SMS/email alerts to owner when inspections are due, tests are overdue, or equipment needs service |
| 84 | **Compliance score** | Overall percentage score with breakdown by category (detection, notification, power, etc.) |
| 85 | **Auto-fixable issues** | Some compliance gaps can be fixed automatically (e.g., enabling low-battery annunciation) |
| 86 | **Alert acknowledge/resolve** | Owner can acknowledge alerts and mark them resolved when fixed |
| 87 | **Certified technician flag** | Alerts that require a licensed technician are flagged as such |
| 88 | **Compliance report export** | PDF/HTML compliance reports for AHJ inspection submission |
| 89 | **Device test tagging** | Digital equivalent of physical test tags with last test date and technician |
| 90 | **Sensitivity drift monitoring** | Tracks smoke detector response over time; alerts when approaching out-of-tolerance |
| 91 | **Walk test mode** | Quiet testing mode that suppresses notification appliances during device testing |
| 92 | **Annual functional test scheduler** | Reminds and guides through full annual functional test per NFPA 72 |
| 93 | **Battery discharge test** | Automated 30-minute discharge test with capacity logging |

### Kenya-Optimized SMS (94–101)
| # | Feature | Description |
|---|---------|-------------|
| 94 | **Africa's Talking API** | Direct integration with Africa's Talking for Safaricom, Airtel, Telkom Kenya |
| 95 | **Phone normalization** | Auto-converts 07..., 01..., 254..., and +254 formats to international standard |
| 96 | **Bilingual fire alerts** | English and Swahili fire alert templates with evacuation instructions |
| 97 | **Bilingual maintenance alerts** | English and Swahili maintenance reminders |
| 98 | **Bilingual status reports** | English and Swahili system status summaries |
| 99 | **Bulk SMS** | Send to up to 100 recipients per batch (Africa's Talking limit) with rate limiting |
| 100 | **Delivery tracking** | Per-message delivery status with network identification and failure retry queue |
| 101 | **Daily rate limit** | CAK-compliant 1,000 SMS/day limit with automatic reset |

### USB Data Export for Legal/Insurance (102–112)
| # | Feature | Description |
|---|---------|-------------|
| 102 | **Tamper-evident export** | SHA-256 manifest for every exported file detects any modification |
| 103 | **Digital signature** | Manifest signed to verify package integrity and chain of custody |
| 104 | **Legal hold watermark** | All documents stamped "LEGAL HOLD — DO NOT ALTER" |
| 105 | **Multi-format export** | JSON, CSV, HTML, and PDF outputs for different inspection needs |
| 106 | **Date-range export** | Export only data from a specific incident window (e.g., fire night ± 24 hours) |
| 107 | **Auto-packaging** | All files organized into `logs/`, `audit/`, `config/`, `sensor_data/`, `incident_reports/` |
| 108 | **USB validation** | Pre-export check: sufficient space, writable filesystem, filesystem type detection |
| 109 | **Encryption option** | Password-protected ZIP with AES-256 for sensitive data transport |
| 110 | **Integrity verification** | Post-export verify command confirms no files were corrupted during copy |
|| 111 | **Package listing** | Browse all exported packages on the USB drive with metadata |
|| 112 | **Insurance-ready reports** | Pre-formatted for direct submission to insurance adjusters and fire marshals |

### v0.4.0 — Next-Generation Detection & Audio (113–132)
| # | Feature | Description |
|---|---------|-------------|
| 113 | **Distributed speaker array (AUD-001)** | NFPA 72 §18.4 speakers at 15 ft spacing, 78 dBA each — exceeds compliance with reduced volume |
| 114 | **Directional voice evacuation (AUD-002)** | Per-zone TTS instructions via localized speakers — STI ≥ 0.5 intelligibility |
| 115 | **LiDAR volumetric smoke detection (MOD-003)** | 905 nm LiDAR returns smoke density in meters, 3D plume tracking |
| 116 | **mmWave radar fire detection (MOD-004)** | 60 GHz FMCW radar detects combustion turbulence through smoke |
| 117 | **Acoustic fire signature AI (MOD-005)** | Frequency analysis of crackle/pop/whoosh via FFT, ML classification |
| 118 | **Gas chromatograph (MOD-006)** | Miniaturized GC for precise combustion gas analysis with retention-time matching |
| 119 | **Smart building bridge (MOD-007)** | BACnet/IP + Modbus TCP + KNX integration for elevator/HVAC/door control |
| 120 | **Occupancy-aware detection (MOD-008)** | PIR/ultrasonic/mmwave presence → automatic zone arming & sensitivity |
| 121 | **Drone fire reconnaissance (MOD-009)** | Autonomous thermal drone dispatch, hotspot map, live stream to incident commander |
| 122 | **Blockchain audit logging (MOD-010)** | Immutable SHA-256 Merkle tree for tamper-proof fire records |
| 123 | **Satellite thermal monitoring (MOD-011)** | NASA FIRMS + Copernicus CAMS wildfire detection with smoke plume tracking |
| 124 | **Firefighter PPE bridge (MOD-012)** | BLE SCBA + PASS integration with MAN-Down alerts |
| 125 | **Pressure differential detection (MOD-013)** | Fire room positive pressure → smoke plume validation |
| 126 | **Arc fault detection (MOD-014)** | FFT harmonic analysis of series/parallel arc faults (UL 1699) |
| 127 | **Battery thermal runaway (MOD-015)** | Li-ion early detection: temp rate + gas venting + voltage collapse |
| 128 | **Smart glass opacity (MOD-016)** | NFPA 90A + IRC §R310 emergency window clearing |
| 129 | **Elevator recall (MOD-017)** | NFPA 72 §21.3 Phase I + Phase II recall with firefighter service |
| 130 | **HVAC smoke control (MOD-018)** | NFPA 90A supply shutdown + smoke exhaust + stairwell pressurization |
| 131 | **Mass notification gateway (MOD-019)** | IPAWS/WEA + NOAA + Amber Alert fire dispatch integration |
| 132 | **Post-fire air quality (MOD-020)** | PM2.5/PM10/VOC/CO/NO₂ monitoring with all-clear determination |

### Resilience & Stay-Alive (133–142)
| # | Feature | Description |
|---|---------|-------------|
| 133 | **Sensor health monitoring** | 3-strike degradation with automatic weight redistribution |
| 134 | **Detection timeout guard** | Fusion >2s → threshold fallback, >5x consecutive → camera-only |
| 135 | **SQLite corruption recovery** | PRAGMA integrity_check, auto-rebuild from last-known-good |
| 136 | **Memory leak guard** | Growth >50MB flagged, >100MB triggers gc.collect + alert |
| 137 | **Network partition queue** | Store-and-forward alerts during outage, auto-retry on restoration |
| 138 | **Relay fuse monitor** | Per-relay toggle tracking, >1000 cycles → degradation alert |
| 139 | **Config corruption recovery** | Atomic rename writes with .lkg fallback |
| 140 | **Disk full guard** | <1GB free → log pruning, <500MB → stop non-critical telemetry |
| 141 | **Clock drift monitor** | NTP confidence decay, RTC backup, daily auto-sync |
| 142 | **Process watchdog** | 60s heartbeat — auto-restart with exponential backoff |

### Anti-Tamper & Cryptographic Security (143–157)
| # | Feature | Description |
|---|---------|-------------|
| 143 | **USB update agent (SEC-001)** | Ed25519-signed firmware updates via USB — atomic staging, 3-version rollback |
| 144 | **Ed25519 signature verification** | Every update cryptographically verified before install |
| 145 | **Content hash verification** | Per-file SHA-256 manifest checked before any file is overwritten |
| 146 | **Device ID binding** | Update packages locked to specific Pi serial number or MAC |
| 147 | **Version downgrade protection** | Rejects updates older than current installed version |
| 148 | **Rollback manager** | Automatic backup of last 3 versions with one-command restore |
| 149 | **File integrity monitor (SEC-002)** | Continuous SHA-256 monitoring of all source files — detects unauthorized mods |
| 150 | **Real-time tamper alerts** | FIM violations logged to blockchain + optionally SMS/email |
| 151 | **Baseline management** | Cryptographic baseline recreated after verified authorized changes |
| 152 | **Blockchain audit log (MOD-010-OPT)** | Append-only binary flat file, 112 bytes/block, ~4MB/year |
| 153 | **Merkle tree root** | Incremental computation for single-hash chain verification |
| 154 | **Chain linkage verification** | Every block includes previous block hash — any break detected instantly |
| 155 | **Mock/disk verification** | `verify_chain()` works in-memory (mock) or reads binary file (production) |
| 156 | **Blockchain export to USB** | Full `audit.chain` binary + verification JSON for inspector analysis |
| 157 | **Inspector self-verification** | `./verify.sh` script included in every USB export for field validation |

### USB Export v0.5.0 — Inspector Package (158–170)
| # | Feature | Description |
|---|---------|-------------|
| 158 | **Tamper log export** | All tamper detection events with blockchain proofs |
| 159 | **Blockchain export** | Binary `audit.chain` + `audit.chaindata` + verification JSON |
| 160 | **Update history export** | Complete software update log with signatures and rollback info |
| 161 | **Inspector verification script** | `./verify.sh` — runs hash checks, blockchain validation, tamper scan |
| 162 | **Inspector README** | `README_INSPECTOR.md` explaining every file and how to verify it |
| 163 | **Chain of custody** | Package ID, timestamp, SHA-256 manifest, signature, encryption status |
| 164 | **Legal hold watermark** | All documents stamped "LEGAL HOLD — DO NOT ALTER" |
| 165 | **Multi-format** | JSON + CSV (machine), HTML (human), PDF (formal), binary (forensic) |
| 166 | **Date-range filtering** | Export only data from specific incident window |
| 167 | **USB validation** | Pre-export: space check, writable test, filesystem detection |
| 168 | **Encryption option** | Password-protected ZIP with AES-256 |
| 169 | **Integrity verification** | Post-export verify command confirms no corruption |
| 170 | **Package browsing** | List all exports with metadata |

---

1. **This is not a certified fire alarm system.** It is open-source research software.
2. **NFPA 72**, **NFPA 10**, and local codes govern real fire suppression installations.
3. **Professional certification** by a licensed fire protection engineer is mandatory before connecting suppression hardware.
4. **Insurance** may not cover damages from uncertified fire protection systems.
5. **Liability** rests with the installer and operator, not the authors or contributors.

## License

MIT — See `LICENSE` for full terms. Use responsibly.
