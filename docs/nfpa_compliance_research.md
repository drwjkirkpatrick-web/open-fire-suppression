# NFPA 72 & NFPA 10 Compliance Research for open-fire-suppression

## NFPA 72 — National Fire Alarm and Signaling Code (2022 Edition)

### Detection Requirements

| Rule ID | Requirement | open-fire-suppression Status |
|---------|-------------|------------------------------|
| DET-SPC-001 | Smoke detector spacing ≤ 30 ft (9.1m) on smooth ceiling | ✅ Zone config enforces spacing |
| DET-SPC-002 | Heat detector spacing ≤ 50 ft (15.2m) | ✅ Thermal zone config |
| DET-SPC-003 | Sloped ceiling (>30°): spacing measured along slope | ⚠️ Geometry check needed |
| DET-LOC-001 | Detectors ≥ 4 in (10cm) from side walls | ⚠️ Placement validator needed |
| DET-LOC-002 | Detectors ≥ 3 ft (0.9m) from HVAC supply diffusers | ⚠️ Placement validator needed |
| DET-COV-001 | Every room/space has ≥1 detector | ✅ Zone coverage check |
| DET-COV-002 | Critical areas require 2 independent detectors | ✅ Redundancy check in resilience layer |
| DET-RES-001 | Response time: detection within 30 sec of smoke entry | ✅ Latency tracking + timeout guard |
| DET-TST-001 | Smoke detector sensitivity testing annually | ⚠️ Sensitivity drift monitor needed |
| DET-CLS-001 | Detectors classified by response characteristics | ✅ Engine classification |

### Notification Appliance Requirements

| Rule ID | Requirement | Status |
|---------|-------------|--------|
| NOT-AUD-001 | Audible ≥ 75 dBA or 15 dBA above ambient | ✅ Buzzer + TTS configurable |
| NOT-AUD-002 | Temporal code: 3 pulses (0.5s on, 0.5s off) | ✅ Evacuation LED + buzzer pattern |
| NOT-VIS-001 | Visible: 15/30/75/110 candela by mounting height | ⚠️ LED intensity config needed |
| NOT-VIS-002 | Strobes flash at 1 Hz, synchronized | ⚠️ Sync mechanism needed |
| NOT-VOI-001 | Voice evacuation STI ≥ 0.5 (intelligibility) | ✅ TTS system built |
| NOT-VOI-002 | Live voice override capability | ⚠️ Microphone input needed |
| NOT-HAP-001 | Tactile notification for hearing-impaired | ✅ Haptic alert system |

### Power Supply Requirements

| Rule ID | Requirement | Status |
|---------|-------------|--------|
| PWR-SEC-001 | 24h standby + 5 min alarm on batteries | ✅ Battery monitoring + safe shutdown |
| PWR-SEC-002 | Dedicated branch circuit labeled 'FIRE ALARM' | ⚠️ AC power monitoring needed |
| PWR-MON-001 | Low battery annunciation | ✅ Battery telemetry |
| PWR-MON-002 | Charger failure annunciation | ⚠️ Charger monitoring needed |
| PWR-GND-001 | Ground fault detection | ⚠️ Ground fault sensor needed |
| PWR-SRG-001 | Surge protection on signaling circuits | ⚠️ Surge suppressor needed |

### Monitoring & Transmission

| Rule ID | Requirement | Status |
|---------|-------------|--------|
| MON-TRN-001 | Two independent paths to supervising station | ✅ Multi-channel: SMS + MQTT + email |
| MON-TRN-002 | Trouble signals within 200 seconds | ✅ Alert notifier with rate limiting |
| MON-SUP-001 | Supervised initiating circuits | ✅ I2C error detection |
| MON-INT-001 | Integrity check: loss of comm = local alarm | ✅ Network partition detection |
| MON-REC-001 | Central station must be UL-listed | ⚠️ Requires external provider |

### Testing & Maintenance

| Rule ID | Requirement | Status |
|---------|-------------|--------|
| TST-REC-001 | Annual test records kept ≥ 1 year | ✅ Audit log + incident reports |
| TST-TAG-001 | Device tags with last test date + technician | ⚠️ Physical tag integration needed |
| TST-FUN-001 | Full functional test annually | ✅ Self-diagnostics |
| TST-BAT-001 | Battery discharge test (30 min) annually | ⚠️ Automated discharge test needed |
| TST-SEN-001 | Smoke detector sensitivity test semi-annually | ⚠️ Sensitivity monitoring needed |
| TST-WLK-001 | Walk test mode | ⚠️ Quiet test mode needed |

### Control Unit Requirements

| Rule ID | Requirement | Status |
|---------|-------------|--------|
| CTL-ANN-001 | All signals annunciated at control panel | ✅ Web dashboard |
| CTL-ZON-001 | Zone isolation | ✅ Zone architecture |
| CTL-ADR-001 | Unique addressable identifier per device | ✅ Sensor name uniqueness |
| CTL-SIL-001 | Silence audible, maintain visual | ✅ Safety interlock |
| CTL-RST-001 | Reset from control panel only | ✅ Local-only reset |

## NFPA 10 — Portable Fire Extinguishers (2022 Edition)

### Placement Requirements

| Rule ID | Requirement | Status |
|---------|-------------|--------|
| EXT-PLA-001 | Max travel distance per class | ⚠️ Building layout integration |
| EXT-PLA-002 | Mounting height ≤ 5 ft (1.5m) | ⚠️ Placement validator |
| EXT-PLA-003 | Visible or marked with signage | ⚠️ Signage module needed |
| EXT-PLA-004 | Not blocked or obstructed | ⚠️ Obstruction monitoring |

### Inspection & Maintenance

| Rule ID | Requirement | Status |
|---------|-------------|--------|
| EXT-INS-001 | Monthly inspection with tag | ✅ Inspection scheduler + alerts |
| EXT-INS-002 | Annual maintenance by certified tech | ⚠️ External integration |
| EXT-INS-003 | Hydrostatic testing per schedule | ⚠️ Testing scheduler |
| EXT-INS-004 | Recharge after any use | ✅ Usage tracking |
| EXT-DOC-001 | Inspection records kept 1 year | ✅ Audit log |
| EXT-DOC-002 | Maintenance records kept life + 1 year | ✅ Persistent audit log |
| EXT-DOC-003 | Complete inventory with locations | ✅ Zone-based inventory |

## Implementation Plan

1. **Enhanced Compliance Module** — Full NFPA 72/10 rule engine with owner alert system
2. **Kenya SMS** — Africa's Talking API optimized for Safaricom/Airtel/Telkom
3. **USB Export** — FAT32/NTFS export with tamper-proof signature for legal discovery
4. **NFPA Integration** — All modules updated with compliance hooks
5. **Testing** — 200+ tests targeting
