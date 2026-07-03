# open-fire-suppression

An open-source fire detection and suppression control system running on Raspberry Pi 5 (8GB RAM).

> ⚠️ **USE AT YOUR OWN RISK.** This software is provided as-is for educational and research purposes. Any deployment in a real-world fire protection scenario requires professional engineering review, installation by certified technicians, and sign-off by your local Authority Having Jurisdiction (AHJ).
>
> 🏛️ **REGULATORY COMPLIANCE:** Before activating suppression hardware, your system must pass inspection by a licensed fire protection engineer and obtain module installation certification from the appropriate local or national fire safety authority. Failure to do so may violate fire codes, invalidate insurance coverage, and create serious life safety hazards.

---

## Overview

This project provides a complete fire detection and suppression control system with:

| Feature | Status |
|---------|--------|
| Multi-sensor fusion (smoke, temp, humidity, IR, thermal camera) | ✅ Core |
| Pi Camera Module 3 video fire detection | ✅ Core |
| TensorFlow Lite fire/smoke AI model | ✅ IMP-001 |
| Kalman filter sensor fusion | ✅ IMP-002 |
| Battery backup with safe shutdown | ✅ Core |
| Real-time telemetry and web dashboard | ✅ Core |
| Alert notifications (buzzer, SMS, email, webhook) | ✅ IMP-003 |
| Multi-zone detection architecture | ✅ IMP-004 |
| Startup self-diagnostics | ✅ IMP-005 |
| Remote config + OTA updates | ✅ IMP-006 |
| Environmental baseline learning | ✅ IMP-007 |
| MQTT IoT / Home Assistant integration | ✅ IMP-008 |
| Water mist zone targeting | ✅ IMP-009 |
| Tamper-evident audit logging | ✅ IMP-010 |
| Configurable suppression actuation with safety interlocks | ✅ Core |
| Offline-first operation | ✅ Core |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Sensor Layer    │  MQ-2 │ SHT40 │ MLX90614 │ AMG8833 │ ... │
├─────────────────────────────────────────────────────────────┤
│  Detection Engine│  Sensor Fusion → Kalman → TFLite Model  │
├─────────────────────────────────────────────────────────────┤
│  Safety Layer    │  Interlocks │ Arming │ Watchdog │ E-Stop  │
├─────────────────────────────────────────────────────────────┤
│  Actuation Layer │  Relay Control │ Water Mist Targeting     │
├─────────────────────────────────────────────────────────────┤
│  Telemetry       │  SQLite │ Audit Log │ MQTT │ Dashboard    │
├─────────────────────────────────────────────────────────────┤
│  Power           │  UPS Monitoring │ Safe Shutdown │ Baseline  │
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

All tests pass. Run the full suite:

```bash
PYTHONPATH=src pytest tests/ -v
```

The test suite covers:
- **65 core tests** — sensors, detection, safety, power, telemetry
- **41 improvement tests** — TFLite, Kalman, zones, diagnostics, baseline, targeting, audit, notifications

## Compliance & Safety Notice

1. **This is not a certified fire alarm system.** It is open-source research software.
2. **NFPA 72**, **NFPA 10**, and local codes govern real fire suppression installations.
3. **Professional certification** by a licensed fire protection engineer is mandatory before connecting suppression hardware.
4. **Insurance** may not cover damages from uncertified fire protection systems.
5. **Liability** rests with the installer and operator, not the authors or contributors.

## License

MIT — See `LICENSE` for full terms. Use responsibly.
