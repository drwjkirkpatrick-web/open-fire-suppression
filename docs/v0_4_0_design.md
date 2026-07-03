# 20 New Fire Detection Modules + 2 Audio Upgrades + Next-Gen Technology

## Design Document for open-fire-suppression v0.4.0

---

## AUDIO UPGRADES (2 modules)

### AUD-001 — Distributed Speaker Array with Closer Spacing
**NFPA 72 Compliance**: §18.4 public mode (75 dBA), §18.4.5 (15 dB above ambient)
**Problem**: Single loud horn at 110 dBA is disorienting, causes hearing damage, masks voice evac...
**Solution**: 8–16 small speakers spaced 15 ft apart at 82–85 dBA each, maintaining >75 dBA everywhere
**Hardware**: 8-ohm ceiling/wall speakers, Class D amplifiers (TDA7297, PAM8610), Pi GPIO + PWM
**Perks**: Lower per-unit volume, clearer voice evacuation, directional messaging, hearing protection

### AUD-002 — Directional Speaker Zones with Voice Evacuation
**NFPA 72 Compliance**: §24.4 voice messaging required for high-rise, assembly, healthcare
**Problem**: One-size-fits-all alarm; can't tell occupants which direction to evacuate
**Solution**: Per-zone directional speakers with TTS: "Fire detected in Kitchen — evacuate EAST via Main Exit"
**Hardware**: Same speakers as AUD-001 but with zone routing
**Perks**: Occupants hear precise instructions; reduces panic; faster evacuation

---

## NEXT-GENERATION FIRE DETECTION TECHNOLOGY

### NGT-001 — Hyperspectral Fire Signature Detection
**Technology**: Hyperspectral imaging (narrow spectral bands beyond RGB) detects chemical combustion signatures (CO, CO₂, water vapor, soot)
**Status**: Emerging research (NASA, NIST); consumer-grade sensors not available
**Our approach**: Build module architecture that accepts hyperspectral data cubes; integrate when hardware available
**Advantage**: Detects pre-combustion chemical signatures before visible flame

---

## 20 NEW MODULES

### Module 1: `detection/distributed_audio.py` — AUD-001
Distributed speaker array with closer spacing, lower per-unit volume, NFPA 72 compliant.

### Module 2: `alerts/directional_voice_evac.py` — AUD-002
Directional voice evacuation with per-zone TTS instructions.

### Module 3: `sensors/lidar_smoke.py` — MOD-003
LiDAR-based volumetric smoke detection. Smoke scatters 905 nm laser light; return signal intensity = smoke density. No false positives from steam (different scattering profile).

### Module 4: `detection/mmwave_radar.py` — MOD-004
Millimeter-wave (60 GHz) radar detects fire by measuring combustion-induced turbulence and thermal plume motion. Penetrates smoke where cameras fail.

### Module 5: `detection/acoustic_fire_signature.py` — MOD-005
AI analysis of fire acoustic signatures: crackling, popping, whooshing. Frequency analysis distinguishes fire from HVAC, machinery, rain.

### Module 6: `sensors/gas_chromatograph.py` — MOD-006
Miniaturized GC (Gas Chromatograph) separates combustion gases: CO, CO₂, H₂, CH₄. Highest accuracy but highest cost. Used for reference/calibration.

### Module 7: `network/smart_building_bridge.py` — MOD-007
Bridge to BACnet/IP, Modbus TCP, KNX for integration with commercial building management systems (BMS). Send fire events to elevator controllers, HVAC dampers, access control.

### Module 8: `detection/occupancy_aware_detection.py` — MOD-008
PIR/ultrasonic/mmWave occupancy sensors reduce false alarms in unoccupied zones. Arming automatically adjusts based on occupancy schedule.

### Module 9: `network/drone_fire_recon.py` — MOD-009
Integration with autonomous drone API. On fire detection, dispatch drone for thermal reconnaissance, live video feed, victim location. Returns waypoints for first responders.

### Module 10: `telemetry/blockchain_audit.py` — MOD-010
Immutable blockchain logging of all fire events, suppressions, and audit records. Provides tamper-proof chain of custody for legal proceedings. Uses lightweight Merkle tree.

### Module 11: `detection/satellite_thermal_monitoring.py` — MOD-011
Pulls thermal satellite data (Landsat, Sentinel, GOES) for wildfire monitoring. Compares satellite hotspot with local sensor correlation.

### Module 12: `alerts/firefighter_ppe_bridge.py` — MOD-012
Integrates with SCBA (Self-Contained Breathing Apparatus) units and PASS (Personal Alert Safety System) devices via Bluetooth Low Energy. Sends building layout, fire location, and air quality to arriving crews.

### Module 13: `detection/pressure_differential.py` — MOD-013
Differential pressure sensors detect fire-induced airflow changes (positive pressure in fire room, negative in stairwells). Validates smoke plume direction.

### Module 14: `detection/arc_fault_detector.py` — MOD-014
Electrical arc fault detection (AFCI): detects series/parallel arc signatures in current waveform. Prevents electrical fire ignition.

### Module 15: `detection/battery_thermal_runaway.py` — MOD-015
Lithium-ion battery thermal runaway detection: rapid temp rise + gas venting (HF, CO₂) + voltage drop. Critical for EV charging stations and battery storage facilities.

### Module 16: `actuation/smart_glass_opacity.py` — MOD-016
Controls electrochromic/smart glass opacity. In fire: transparent to let firefighters see inside; opaque to block radiant heat. NFPA 5000 compatible.

### Module 17: `actuation/elevator_recall.py` — MOD-017
NFPA 72 §21.3 elevator recall: on fire detection, all elevators return to designated floor, open doors, disconnect from automatic operation. Prevents occupants being trapped in burning shaft.

### Module 18: `actuation/hvac_shutdown.py` — MOD-018
NFPA 90A compliant HVAC smoke control: shuts down supply fans, closes dampers, activates exhaust fans. Prevents smoke migration through ductwork.

### Module 19: `alerts/mass_notification_gateway.py` — MOD-019
Integration with IPAWS/WEA (Wireless Emergency Alerts), NOAA weather radio, and local emergency broadcast systems. Sends building-specific fire alerts to cell towers in area.

### Module 20: `telemetry/post_fire_air_quality.py` — MOD-020
Post-suppression air quality monitoring: PM2.5, PM10, VOCs, CO, formaldehyde. Determines when building is safe to re-enter. Generates "all clear" report.

---

## Resilience Considerations
- Every new sensor has mock mode, health monitoring, and graceful degradation
- Distributed audio fails gracefully: individual speaker failure doesn't cascade
- Blockchain audit falls back to local tamper-evident log if network unavailable
- Drone integration has timeout and offline fallback
- Smart building bridge retries with exponential backoff
- Elevator recall has manual override and watchdog timer
- HVAC shutdown has position feedback confirmation; failure triggers alarm

## Compliance Impact
- All modules reference specific NFPA 72, NFPA 90A, NFPA 5000, and NEC sections
- Elevator recall follows NFPA 72 §21.3 exactly
- HVAC shutdown follows NFPA 90A §6.2
- Mass notification follows IPAWS/FEMA requirements
- Battery thermal runaway addresses new UL 9540A requirements
