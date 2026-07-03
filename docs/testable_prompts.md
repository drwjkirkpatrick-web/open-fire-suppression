# Testable Prompts — open-fire-suppression
## Raspberry Pi 5 Fire Detection & Suppression System

These are the testable requirements and prompts that define the project's acceptance criteria. Each prompt has a test file in `tests/unit/` or `tests/integration/`.

---

## SENSORS

### S001 — I2C Bus Discovery
"The system shall scan the I2C bus and report all connected device addresses on startup."
- **Test**: `test_i2c_scan.py`
- **Validation**: Mock I2C bus returns expected addresses; system logs detected sensors.

### S002 — ADS1115 ADC Reading
"The ADS1115 shall read all 4 analog channels and return 16-bit values with configurable gain."
- **Test**: `test_ads1115.py`
- **Validation**: Mock SMBus reads; verify gain scaling; verify all 4 channels.

### S003 — MQ-2 Smoke Sensor Calibration
"The MQ-2 shall report calibrated ppm values for smoke, LPG, and methane after a 60-second warm-up."
- **Test**: `test_mq2.py`
- **Validation**: Mock ADC values → verify Rs/R0 ratio → verify ppm lookup.

### S004 — SHT40 Temperature & Humidity
"The SHT40 shall return temperature (±0.3°C) and relative humidity (±2%) readings at 2 Hz."
- **Test**: `test_sht40.py`
- **Validation**: Mock CRC-validated I2C data → verify temp/humidity calculation.

### S005 — MLX90614 Non-Contact Temperature
"The MLX90614 shall return object temperature from -70°C to +380°C via SMBus at 1 Hz."
- **Test**: `test_mlx90614.py`
- **Validation**: Mock SMBus reads; verify temperature conversion from raw data.

### S006 — BME680 Multi-Sensor Read
"The BME680 shall return temperature, humidity, pressure, and gas resistance in a single burst read."
- **Test**: `test_bme680.py`
- **Validation**: Mock I2C burst read; verify all 4 values extracted correctly.

### S007 — ENS160 VOC / Air Quality
"The ENS160 shall return TVOC (ppb) and eCO2 (ppm) after initial warm-up."
- **Test**: `test_ens160.py`
- **Validation**: Mock I2C reads; verify warm-up state handling; verify AQI calculation.

### S008 — AMG8833 Thermal Grid
"The AMG8833 shall return an 8×8 grid of temperatures at 10 Hz."
- **Test**: `test_amg8833.py`
- **Validation**: Mock 128-byte I2C read → verify 64 temperature values.

### S009 — MLX90640 Thermal Camera
"The MLX90640 shall return a 32×24 thermal frame with ±1°C accuracy at 1 Hz."
- **Test**: `test_mlx90640.py`
- **Validation**: Mock frame data → verify EEPROM compensation → verify 768 temperature values.

### S010 — Pi Camera Module 3 Capture
"The Pi Camera Module 3 shall capture 1080p frames at 10 FPS via picamera2."
- **Test**: `test_picamera.py`
- **Validation**: Mock picamera2 capture → verify frame dimensions and rate.

### S011 — DS18B20 1-Wire Temperature
"The DS18B20 shall return temperature from 1-Wire bus at 1 Hz with ±0.5°C accuracy."
- **Test**: `test_ds18b20.py`
- **Validation**: Mock sysfs `/sys/bus/w1/devices/` → verify CRC and temperature parse.

### S012 — Sensor Health Monitoring
"Each sensor shall report a health status (OK, WARN, ERROR) based on communication success rate over 10 seconds."
- **Test**: `test_sensor_health.py`
- **Validation**: Mock failures; verify degraded sensors are flagged.

---

## DETECTION ENGINE

### D001 — Single-Sensor Threshold Fire Detection
"The system shall trigger a FIRE WARNING when any single sensor exceeds its configured threshold."
- **Test**: `test_single_threshold.py`
- **Validation**: Feed sensor data above threshold → verify FIRE WARNING state.

### D002 — Multi-Sensor Fusion Fire Detection
"The system shall trigger a FIRE ALERT when ≥2 independent sensors confirm fire signatures within 5 seconds."
- **Test**: `test_sensor_fusion.py`
- **Validation**: Feed correlated multi-sensor data → verify FIRE ALERT state.

### D003 — False Positive Suppression
"The system shall NOT trigger fire alerts when only one sensor type activates (e.g., hot day + normal cooking)."
- **Test**: `test_false_positive_suppression.py`
- **Validation**: Feed isolated high-temp data → verify NO ALERT.

### D004 — Thermal Hotspot Detection
"The thermal camera shall detect ≥1 hotspot ≥60°C in any 2×2 pixel region."
- **Test**: `test_thermal_hotspot.py`
- **Validation**: Inject thermal frame with 70°C cluster → verify hotspot detected.

### D005 — Flame Flicker Detection
"Video analysis shall detect flame-colored flickering (1–12 Hz) in region of interest."
- **Test**: `test_flame_flicker.py`
- **Validation**: Feed synthetic flickering ROI → verify flame confidence > threshold.

### D006 — Smoke Plume Detection
"Video analysis shall detect gray/white smoke plumes via background subtraction + upward motion."
- **Test**: `test_smoke_plume.py`
- **Validation**: Feed synthetic smoke frames → verify smoke confidence > threshold.

### D007 — Fire Spread Direction
"The system shall estimate fire spread direction from sequential thermal frames."
- **Test**: `test_fire_spread.py`
- **Validation**: Inject moving hotspot sequence → verify direction vector.

### D008 — Confidence Scoring
"Each fire detection shall produce a confidence score (0.0–1.0) from sensor fusion weights."
- **Test**: `test_confidence_scoring.py`
- **Validation**: Verify score increases with more confirming sensors.

### D009 — Detection Latency
"Fire detection shall complete within 2 seconds of sensor data arrival."
- **Test**: `test_detection_latency.py`
- **Validation**: Time detection pipeline end-to-end.

---

## SUPPRESSION ACTUATION

### A001 — Relay Control
"The system shall control up to 4 relay channels via GPIO with configurable active-high/low logic."
- **Test**: `test_relay_control.py`
- **Validation**: Mock GPIO writes → verify relay states; verify active-high/low inversion.

### A002 — Pre-Activation Warning
"The system shall emit a 10-second audible/visual warning before activating suppression."
- **Test**: `test_pre_activation_warning.py`
- **Validation**: Verify 10-second countdown; verify buzzer GPIO toggles; verify relay NOT activated.

### A003 — Suppression Activation
"After pre-activation warning, the system shall activate suppression relays for configured duration."
- **Test**: `test_suppression_activation.py`
- **Validation**: Verify relay GPIO activates; verify auto-deactivation after duration.

### A004 — Suppression Feedback
"The system shall read a flow sensor or pressure switch to confirm suppression delivery."
- **Test**: `test_suppression_feedback.py`
- **Validation**: Mock digital input → verify SUPPRESSION CONFIRMED vs FAILED.

### A005 — Manual Override
"A physical button shall allow immediate manual activation or cancellation of suppression."
- **Test**: `test_manual_override.py`
- **Validation**: Mock GPIO button press → verify immediate activation/cancel.

---

## SAFETY INTERLOCKS

### F001 — System Arming
"The system shall only be ARMED after a 2-person authentication or physical key switch."
- **Test**: `test_system_arm.py`
- **Validation**: Verify ARMED state requires authentication; suppression blocked when DISARMED.

### F002 — Disarm Safety
"When DISARMED, all suppression actuation shall be electrically and logically inhibited."
- **Test**: `test_disarm_inhibit.py`
- **Validation**: Verify relays cannot activate when DISARMED; verify GPIO stays LOW.

### F003 — Maintenance Mode
"Maintenance mode shall disable all actuation and log as "MAINTENANCE" in telemetry."
- **Test**: `test_maintenance_mode.py`
- **Validation**: Verify suppression blocked; verify telemetry mode field.

### F004 — Tamper Detection
"The system shall detect enclosure tamper (door open, cover removed) via magnetic switch."
- **Test**: `test_tamper_detection.py`
- **Validation**: Mock GPIO input → verify TAMPER alert; verify suppression inhibited.

### F005 — Watchdog Timer
"The system shall have a software watchdog that resets the Pi if the main loop hangs for >30 seconds."
- **Test**: `test_watchdog.py`
- **Validation**: Verify watchdog file is written in loop; verify timeout triggers action.

### F006 — Emergency Stop
"A physical emergency stop button shall immediately cut all actuation power and log the event."
- **Test**: `test_emergency_stop.py`
- **Validation**: Mock E-stop GPIO → verify immediate relay deactivation; verify event log.

---

## POWER MANAGEMENT

### P001 — Battery Voltage Monitoring
"The system shall read battery voltage via ADS1115 voltage divider every 5 seconds."
- **Test**: `test_battery_voltage.py`
- **Validation**: Mock ADC value → verify voltage calculation; verify percentage.

### P002 — Low Battery Warning
"At ≤20% battery, the system shall emit low-battery warnings every 60 seconds."
- **Test**: `test_low_battery_warning.py`
- **Validation**: Mock 15% battery → verify warning log; verify buzzer pattern.

### P003 — Safe Shutdown on Low Battery
"At ≤5% battery, the system shall initiate safe shutdown after logging the event."
- **Test**: `test_low_battery_shutdown.py`
- **Validation**: Mock 4% battery → verify shutdown script called; verify filesystem sync.

### P004 — AC Power Loss Detection
"The system shall detect AC power loss within 1 second and switch to battery telemetry mode."
- **Test**: `test_ac_loss.py`
- **Validation**: Mock power status GPIO → verify AC_LOST event; verify UPS mode.

### P005 — AC Power Restore
"When AC power returns, the system shall log restoration and resume normal charging telemetry."
- **Test**: `test_ac_restore.py`
- **Validation**: Mock power status → verify AC_RESTORED event.

### P006 — PiSugar / PiJuice Integration
"If using PiSugar or PiJuice, the system shall read battery percentage via I2C API."
- **Test**: `test_ups_hat_api.py`
- **Validation**: Mock I2C API response → verify battery percentage parse.

---

## TELEMETRY & LOGGING

### T001 — SQLite Event Logging
"All fire events, sensor readings, and actuation states shall be logged to SQLite with timestamps."
- **Test**: `test_sqlite_logging.py`
- **Validation**: Verify table schema; verify insert; verify timestamp format.

### T002 — Real-Time Dashboard API
"The system shall expose a FastAPI endpoint `/api/status` returning current sensor values and system state."
- **Test**: `test_api_status.py`
- **Validation**: HTTP GET → verify JSON with all sensor values and state.

### T003 — Dashboard WebSocket
"The dashboard shall push real-time updates via WebSocket at 1 Hz."
- **Test**: `test_websocket_updates.py`
- **Validation**: Connect WebSocket → verify messages received at ~1 Hz.

### T004 — Historical Data Query
"The API shall support querying sensor history by sensor name, start/end time, and limit."
- **Test**: `test_api_history.py`
- **Validation**: HTTP GET with query params → verify filtered results.

### T005 — Alert Notification
"On FIRE ALERT, the system shall send notifications via configurable channels (local buzzer, optional SMS/webhook)."
- **Test**: `test_alert_notification.py`
- **Validation**: Mock notification backends → verify all configured channels called.

### T006 — Log Rotation
"SQLite logs shall rotate automatically when exceeding 100 MB, keeping the last 10 archives."
- **Test**: `test_log_rotation.py`
- **Validation**: Mock large database → verify rotation trigger; verify archive exists.

---

## CONFIGURATION

### C001 — YAML Configuration Loading
"The system shall load all thresholds, pins, and timings from a YAML configuration file on startup."
- **Test**: `test_config_load.py`
- **Validation**: Verify YAML parse; verify all required keys present.

### C002 — Configuration Validation
"Invalid configuration (missing keys, out-of-range values) shall raise a clear error on startup."
- **Test**: `test_config_validation.py`
- **Validation**: Feed invalid YAML → verify specific error message.

### C003 — Runtime Config Reload
"The system shall support SIGUSR1-triggered configuration reload without restart."
- **Test**: `test_config_reload.py`
- **Validation**: Send SIGUSR1 → verify new thresholds applied.

---

## SYSTEM & INTEGRATION

### I001 — System Startup Sequence
"On boot, the system shall: init sensors → run health check → enter monitoring loop in ≤30 seconds."
- **Test**: `test_startup_sequence.py`
- **Validation**: Verify each phase completes; verify total time ≤30s (mocked sensors).

### I002 — Graceful Shutdown
"On SIGTERM, the system shall: close sensors → sync logs → release relays → shutdown."
- **Test**: `test_graceful_shutdown.py`
- **Validation**: Send SIGTERM → verify clean teardown sequence.

### I003 — End-to-End Fire Detection
"Given a simulated fire (multi-sensor), the system shall detect, warn, and activate suppression in sequence."
- **Test**: `test_e2e_fire_detection.py`
- **Validation**: Full pipeline test with mocked hardware.

### I004 — End-to-End Power Loss
"Given AC power loss, the system shall continue monitoring on battery, log events, and shut down safely at low battery."
- **Test**: `test_e2e_power_loss.py`
- **Validation**: Simulate AC loss → battery drain → verify safe shutdown.

### I005 — Recovery After Restart
"After unexpected restart, the system shall resume monitoring and report the last known state from database."
- **Test**: `test_recovery_restart.py`
- **Validation**: Pre-populate DB → simulate restart → verify state recovery.

---

## MOCK MODE (Offline Development)

### M001 — Mock Hardware Layer
"All sensor/actuation hardware shall be mockable for development on non-Pi machines."
- **Test**: `test_mock_mode.py`
- **Validation**: Verify system runs with `MOCK_HARDWARE=true` without GPIO/I2C errors.

### M002 — Simulated Fire Scenarios
"Mock mode shall provide pre-defined fire scenarios (smoldering, flashover, false alarm) for testing."
- **Test**: `test_mock_scenarios.py`
- **Validation**: Load scenario → verify sensor values follow fire profile → verify detection.

---

## Total Prompt Count

| Category | Count |
|----------|-------|
| Sensors (S) | 12 |
| Detection (D) | 9 |
| Actuation (A) | 5 |
| Safety (F) | 6 |
| Power (P) | 6 |
| Telemetry (T) | 6 |
| Configuration (C) | 3 |
| Integration (I) | 5 |
| Mock Mode (M) | 2 |
| **Total** | **54** |

---

## Test File Naming Convention

- Unit tests: `tests/unit/test_{prompt_code.lower()}.py`
- Integration tests: `tests/integration/test_{prompt_code.lower()}.py`
- Each test file maps 1:1 to a prompt above.
