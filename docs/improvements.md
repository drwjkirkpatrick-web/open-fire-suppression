# 10 Improvement Strategies — open-fire-suppression
## Raspberry Pi 5 Fire Detection & Suppression System

---

## IMP-001 — TFLite Fire/Smoke Detection Model

**Problem**: Current video analysis uses simple HSV color thresholding, which is prone to false positives from orange objects, sunsets, incandescent lighting.

**Solution**: Export a pre-trained YOLOv8 fire/smoke detection model to TensorFlow Lite format for on-device ARM inference. The model runs on Pi 5's VideoCore VII GPU via the delegate.

**Implementation**:
- Add `ultralytics` dependency for training
- Add `tflite_runtime` for inference
- Create `src/fire_suppression/detection/tflite_detector.py`
- Support model download/caching from a trusted source
- Benchmark: target ≥5 FPS at 640×480 on Pi 5

**Test prompt**: Video frame with synthetic fire → model returns bounding boxes with confidence >0.7.

---

## IMP-002 — Kalman Filter Sensor Fusion

**Problem**: Simple threshold comparisons miss gradual fire development and produce noisy state transitions.

**Solution**: Implement a multi-sensor Kalman filter that estimates a hidden "fire intensity" state from all sensors. The filter smooths transient noise and tracks trend direction.

**Implementation**:
- Add `src/fire_suppression/detection/kalman_fusion.py`
- State vector: [fire_intensity, temperature_trend, smoke_trend]
- Observation vector: normalized sensor readings
- Use `filterpy` or custom implementation
- Configurable process noise (aggressive vs. conservative)

**Test prompt**: Gradual smoldering input → filter outputs smooth increasing fire probability with low lag.

---

## IMP-003 — Cellular/WiFi Alert Notification System

**Problem**: Local buzzer only alerts people nearby. Remote monitoring is essential for unoccupied buildings.

**Solution**: Modular notification system supporting multiple channels: local buzzer, Twilio SMS, SMTP email, generic webhook.

**Implementation**:
- Add `src/fire_suppression/telemetry/notifier.py`
- Notification queue with retry logic and rate limiting
- Configurable channels and credentials via environment variables
- Separate notification levels: WARNING (low priority) vs ALERT (immediate)

**Test prompt**: Fire ALERT → verify all configured notification channels are called within 5 seconds.

---

## IMP-004 — Multi-Zone Architecture

**Problem**: Single set of thresholds doesn't work for different environments (kitchen vs. garage vs. server room).

**Solution**: Support multiple independently configured zones, each with its own sensors, thresholds, and actuation relays.

**Implementation**:
- Extend config YAML with `zones:` section
- Each zone has sensors, thresholds, and relay mapping
- Zone-level detection and actuation
- Dashboard shows per-zone status

**Test prompt**: Zone A fire detected → only Zone A relays activate; Zone B remains unaffected.

---

## IMP-005 — Self-Diagnostic Health Check Suite

**Problem**: System may start with faulty sensors or uncalibrated gas detectors, leading to blind spots.

**Solution**: Comprehensive startup diagnostics: I2C scan, sensor communication test, relay dry-run test, MQ-2 auto-calibration, camera test frame capture.

**Implementation**:
- Add `src/fire_suppression/diagnostics/startup_check.py`
- Generates a health report with pass/fail per component
- Blocks arming until all critical checks pass
- Stores report in telemetry DB

**Test prompt**: Run diagnostics with one sensor disconnected → report marks it FAILED; system cannot arm.

---

## IMP-006 — Remote Configuration & OTA Updates

**Problem**: Physical access to Pi may be difficult after deployment. Configuration changes and bug fixes need remote deployment.

**Solution**: Secure config editor via web API + git-based OTA update mechanism.

**Implementation**:
- Add `/api/config` GET/POST endpoints with validation
- Config changes persisted to YAML and hot-reloaded
- OTA via git pull + systemd service restart
- SSH key-based authentication

**Test prompt**: POST new thresholds → system applies without restart; verify detection uses new values.

---

## IMP-007 — Environmental Baseline Learning

**Problem**: Seasonal temperature/humidity changes cause false alarms when thresholds are static.

**Solution**: 24-48 hour baseline learning mode that records normal min/max/avg for each sensor, then auto-adjusts thresholds with configurable margin.

**Implementation**:
- Add `src/fire_suppression/detection/baseline.py`
- Baseline learning mode activated via config or API
- Stores baseline stats in SQLite
- Thresholds computed as: baseline + margin + safety_offset

**Test prompt**: Run baseline learning for 10 simulated "days" → thresholds shift to accommodate higher ambient temps.

---

## IMP-008 — MQTT IoT Integration

**Problem**: No interoperability with existing IoT/smart home ecosystems.

**Solution**: MQTT client that publishes sensor data and subscribes to remote commands (arm/disarm/config).

**Implementation**:
- Add `paho-mqtt` dependency
- Add `src/fire_suppression/telemetry/mqtt_client.py`
- Publish topics: `fire-suppression/sensors/+/values`, `fire-suppression/status`
- Subscribe topics: `fire-suppression/command/arm`, `fire-suppression/command/config`
- Home Assistant MQTT discovery format support

**Test prompt**: Publish arm command via MQTT → system arms; publish sensor data → Home Assistant receives it.

---

## IMP-009 — Water Mist Zone Targeting

**Problem**: Activating all suppression nozzles wastes water and can damage unaffected areas.

**Solution**: Use thermal camera data to estimate fire location, then activate only the suppression nozzles in that zone.

**Implementation**:
- Map thermal camera pixels to physical zones
- Directional nozzle control via servo or zone valves
- Priority: closest nozzle to hotspot centroid first
- Fallback: activate all if targeting fails

**Test prompt**: Hotspot detected in Zone C → only Zone C nozzle activates.

---

## IMP-010 — Comprehensive Audit Log & Compliance Reporting

**Problem**: Fire safety systems require audit trails for insurance and regulatory compliance. Current SQLite logging is basic.

**Solution**: Structured audit log with tamper-evident hashing, exportable PDF/HTML reports, and retention policies.

**Implementation**:
- Add `src/fire_suppression/telemetry/audit.py`
- Each log entry gets SHA-256 hash chaining (like blockchain)
- Daily/weekly/monthly report generation
- PDF export using `reportlab`
- Compliance with NFPA 72-style event logging

**Test prompt**: Log 100 events → verify hash chain integrity; export PDF → verify all events present.

---

## Summary Table

| # | Improvement | Complexity | Impact | Files Added |
|---|------------|------------|--------|-------------|
| 001 | TFLite Fire Model | High | Very High | `detection/tflite_detector.py` |
| 002 | Kalman Filter Fusion | Medium | High | `detection/kalman_fusion.py` |
| 003 | Alert Notifications | Low | Very High | `telemetry/notifier.py` |
| 004 | Multi-Zone Architecture | Medium | High | `detection/zones.py` |
| 005 | Startup Diagnostics | Low | Medium | `diagnostics/startup_check.py` |
| 006 | Remote Config/OTA | Medium | Medium | `web/api_config.py` |
| 007 | Baseline Learning | Medium | High | `detection/baseline.py` |
| 008 | MQTT IoT Integration | Low | High | `telemetry/mqtt_client.py` |
| 009 | Water Mist Targeting | High | Medium | `actuation/targeting.py` |
| 010 | Audit Log/Compliance | Medium | Medium | `telemetry/audit.py` |
