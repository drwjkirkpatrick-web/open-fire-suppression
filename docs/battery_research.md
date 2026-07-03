# Battery Backup & UPS Research Report
## For Raspberry Pi 5 (8GB RAM) — open-fire-suppression Project
### Date: July 2026

---

## 1. Raspberry Pi 5 Power Requirements

- **Input**: 5V DC via USB-C (PD — Power Delivery)
- **Current**: ~600mA idle, ~1.2A under load, up to ~2.5A peak (with USB devices, camera, etc.)
- **Power**: ~3W idle, ~6W typical, ~12.5W peak
- **PD Requirement**: 5V @ 3A (15W) minimum; Pi 5 supports USB-C PD up to 5V @ 5A (25W) for downstream USB
- **Power budget for fire suppression system**:
  - Pi 5 + active cooling: ~5W
  - Camera Module 3: ~250mW
  - I2C sensors (7 devices): ~150mW
  - Relay modules (2–4 relays): ~1W (coils active)
  - Pump/valve control (external, via relay): not powered by Pi
  - **Total estimated**: ~6.5W continuous, ~8W peak
- **Battery runtime target**: Minimum 30 minutes; ideally 1–2 hours for fire event coverage

---

## 2. Commercial UPS HATs for Pi 5

### 2.1 PiSugar 3 Plus
- **Model**: PiSugar 3 Plus (UPS for Pi 4/5)
- **Input**: USB-C 5V
- **Battery**: 5000mAh Li-Po (3.7V)
- **Output**: 5V 3A via pogo pins + USB-C passthrough
- **Cost**: ~$45–55
- **GPIO pins**: None (pogo pin contact to Pi GPIO header, no pin consumption)
- **Features**:
  - RTC (Real-Time Clock) with battery
  - Auto power-on when AC restored
  - Safe shutdown via I2C command
  - Battery percentage reporting via I2C
  - Physical power button
  - Configurable low-battery shutdown threshold
- **Python library**: `pisugar-server` (REST API + Python bindings)
- **Safety**: Overcharge, over-discharge, over-current protection built-in
- **Runtime**: 5000mAh @ 3.7V = 18.5Wh → at 80% efficiency → ~14.8Wh usable → ~2.3 hours at 6.5W
- **Fire relevance**: Excellent — purpose-built for Pi, clean integration, safe shutdown, RTC for timestamping fire events
- **Note**: Must be Pi 5 compatible (newer PiSugar 3 Plus version); some older PiSugar models need adapter

### 2.2 PiJuice Zero / PiJuice Solar
- **Model**: PiJuice Zero (pHAT format) or PiJuice HAT
- **Input**: Micro-USB or USB-C (5V)
- **Battery**: BP7X (1820mAh Li-ion) or custom Li-Po via JST connector
- **Output**: 5V 2.5A
- **Cost**: PiJuice HAT ~$50–65, PiJuice Zero ~$40, battery ~$15–25
- **GPIO pins**: Uses I2C (GPIO 2/3) + power pins; stackable
- **Features**:
  - RTC
  - Configurable safe shutdown via GPIO/I2C
  - Battery status via I2C
  - Solar panel input (PiJuice Solar)
  - Customizable power profile via GUI/config
- **Python library**: `pijuice.py` (official, in `pijuice-base` package)
- **Safety**: Built-in protection PCB
- **Runtime**: 1820mAh → ~6.7Wh → ~5.4Wh usable → ~50 minutes at 6.5W (small battery); custom 5000mAh → ~2+ hours
- **Fire relevance**: Very mature ecosystem; well-documented; but battery capacity lower than PiSugar
- **Note**: PiJuice Zero is low-profile; check Pi 5 compatibility (height of PoE header may interfere)

### 2.3 Geekworm X728 (UPS HAT)
- **Model**: X728 (v2.0 or later for Pi 5)
- **Input**: USB-C 5V
- **Battery**: 2× 18650 Li-ion cells (not included) or JST Li-Po
- **Output**: 5V 6A (powerful!)
- **Cost**: ~$40–50 (without batteries)
- **GPIO pins**: Uses I2C + a few GPIO for power management
- **Features**:
  - Dual 18650 holder (series or parallel)
  - Power management via push button
  - Auto shutdown on low battery
  - Battery voltage monitoring
  - RTC
  - Cooling fan header
- **Python library**: Custom shell scripts + Python wrappers (x728 Python scripts on GitHub)
- **Safety**: 18650 protection; but quality depends on cell choice
- **Runtime**: 2× 3500mAh 18650 = 25.9Wh → ~20Wh usable → ~3 hours at 6.5W
- **Fire relevance**: Good runtime; high current output; but 18650 cells need quality cells (Samsung/Panasonic/LG)
- **Note**: Battery holder adds height; may need tall case or no case

### 2.4 Waveshare UPS HAT (C)
- **Model**: Waveshare UPS HAT (C) for Pi 5
- **Input**: USB-C 5V
- **Battery**: Li-Po (various sizes)
- **Output**: 5V 3A
- **Cost**: ~$30–40 (without battery)
- **GPIO pins**: I2C + power
- **Features**:
  - Battery voltage monitoring
  - Charging status LED
  - Auto shutdown
  - RTC (some versions)
- **Python library**: Waveshare provides Python examples
- **Safety**: Basic protection
- **Runtime**: Depends on battery size
- **Fire relevance**: Budget option; less mature than PiSugar/PiJuice

### 2.5 Recommended Commercial Solution
- **Best overall**: **PiSugar 3 Plus** — cleanest integration, no GPIO pin blocking, excellent runtime, safe shutdown
- **Best ecosystem**: **PiJuice** — most mature software, solar option, very well documented
- **Best runtime/cost**: **Geekworm X728** — dual 18650, very long runtime, high current

---

## 3. DIY UPS Circuits

### 3.1 TP4056 + MT3608 + Li-ion 18650
- **Components**:
  - TP4056 Li-ion charging module (~$1) — charges from USB/5V
  - MT3608 boost converter (~$1) — boosts 3.7V → 5V
  - 18650 cell + holder (~$5–8 for quality cell)
  - Schottky diode or MOSFET switching circuit (~$2)
- **Cost**: ~$10–15
- **GPIO pins**: None (unless adding voltage monitoring)
- **Features**:
  - Charges battery while powering Pi
  - When mains fails, battery→boost→Pi
  - Simple but effective
- **Python library**: None built-in; can add voltage divider + ADC (ADS1115) for battery monitoring
- **Safety**: TP4056 has overcharge/over-discharge protection; but no temperature monitoring; 18650 fire risk if damaged
- **Runtime**: Depends on cell; 3500mAh → ~1.5–2 hours at 6.5W
- **Fire relevance**: CHEAP but requires electronics knowledge; fire-rated enclosure strongly recommended; TP4056 modules vary in quality
- **Note**: Voltage switching NOT seamless — brief dip when switching; Pi 5 may reset; needs OR-ing diode or ideal diode circuit

### 3.2 IP5306 Power Bank Module (Integrated Charge+Boost)
- **Components**:
  - IP5306-based module (~$3–5) — single-chip Li-ion charge management + 5V boost
  - 18650 or Li-Po cell
  - USB-C connector
- **Cost**: ~$8–12
- **GPIO pins**: None
- **Features**:
  - All-in-one charging + boost
  - Load sharing (charges while powering)
  - Battery level indication (4 LEDs or I2C on some modules)
  - Over-current/over-voltage protection
- **Python library**: None; some modules expose I2C for battery percentage
- **Safety**: Better than bare TP4056 — IP5306 has integrated protection
- **Runtime**: Depends on cell
- **Fire relevance**: Simpler DIY option; many power banks use this chip

### 3.3 Adafruit PowerBoost 1000C
- **Model**: Adafruit PowerBoost 1000C (product #2465)
- **Input**: 3.7V Li-Po + USB charge
- **Output**: 5.2V @ 1A+ (up to 2A with good battery)
- **Cost**: ~$15–20
- **GPIO pins**: None
- **Features**:
  - Built-in load sharing
  - Low battery detection pin (LBO) — connect to GPIO for shutdown
  - Power path management
  - JST connector for standard Li-Po
- **Python library**: None needed; LBO pin can trigger GPIO interrupt for shutdown
- **Safety**: Adafruit quality; over-current protection
- **Runtime**: 2500mAh Li-Po → ~9.25Wh → ~7Wh usable → ~1 hour at 6.5W (tight; needs bigger battery)
- **Fire relevance**: Reliable; LBO pin perfect for safe shutdown; but current limited for Pi 5 under full load
- **Note**: 1A may be insufficient for Pi 5 with peripherals; consider PowerBoost 5000 (if available) or multiple cells

### 3.4 DIY UPS with Relay Switching (Advanced)
- **Components**:
  - 5V power supply (mains)
  - Li-ion/LiFePO4 battery bank
  - BMS (Battery Management System) with balance charging
  - 5V buck converter from battery
  - DPDT relay or solid-state relay for automatic switching
  - ADS1115 for voltage monitoring
- **Cost**: ~$30–60
- **GPIO pins**: GPIO for relay control + ADC for monitoring
- **Features**:
  - True UPS — seamless switching via relay
  - Battery voltage/current monitoring
  - Configurable thresholds
  - LiFePO4 option for safer chemistry (lower fire risk)
- **Python library**: Custom (GPIO + ADC)
- **Safety**: BMS protects cells; LiFePO4 much safer than Li-ion (higher thermal runaway threshold)
- **Runtime**: Configurable by battery capacity
- **Fire relevance**: IRONIC — building a Li-ion backup for a fire suppression system; **LiFePO4 strongly recommended** for safety

---

## 4. Battery Monitoring & Safe Shutdown

### 4.1 Voltage Monitoring via ADC
- **ADS1115** (I2C ADC, already in sensor list) — read battery voltage via voltage divider
- Voltage divider: two resistors (e.g., 10kΩ + 10kΩ) to scale battery voltage (up to 4.2V) to 3.3V for ADC
- **Python**: `adafruit-circuitpython-ads1x15` — read differential or single-ended
- **Alert logic**:
  - 4.2V = 100% (Li-ion fully charged)
  - 3.7V = ~50%
  - 3.3V = ~10% — **trigger safe shutdown**
  - 3.0V = 0% — **emergency shutdown to protect battery**

### 4.2 Safe Shutdown Implementation
```python
import os
import sys

def safe_shutdown(reason="low_battery"):
    # Log shutdown reason
    # Close all files
    # Trigger any suppression system safeties
    # Sync filesystem
    os.system("sync")
    # Initiate shutdown
    os.system("sudo shutdown -h now")
```

### 4.3 GPIO-Triggered Shutdown (Hardware)
- Connect LBO (low battery output) from PowerBoost or similar to GPIO (with pull-up)
- When battery drops, LBO goes LOW → trigger GPIO interrupt → execute safe shutdown
- **Python**: `gpiozero.Button(pin, pull_up=True)` with `when_pressed` callback

### 4.4 PiSugar / PiJuice Software Shutdown
- Both HATs provide software APIs to configure auto-shutdown at configurable battery percentage
- PiSugar: `pisugar-server` REST API — `GET /api/settings` and `POST /api/settings`
- PiJuice: `pijuice.SetPowerOff(delay)` and battery level callbacks

---

## 5. Battery Chemistry Safety (Critical for Fire Suppression System)

| Chemistry | Nominal | Fully Charged | Thermal Runaway | Safety Notes |
|-----------|---------|---------------|-----------------|--------------|
| Li-ion (18650) | 3.7V | 4.2V | ~130–150°C | Higher energy density; fire risk if punctured/overcharged |
| Li-Po (pouch) | 3.7V | 4.2V | ~130–150°C | Same risk; can swell; needs protection PCB |
| **LiFePO4** | **3.2V** | **3.6V** | **~270°C** | **MUCH safer**; lower voltage needs boost; heavier; longer cycle life |

### Recommendation for Fire Suppression System
- **If using commercial HAT**: Use as-is (built-in protections are adequate) — PiSugar 3 Plus or PiJuice
- **If building DIY**: **Strongly prefer LiFePO4 cells** for the irony of a fire-safe system having a fire-risk battery
- **Alternative**: Place battery in separate fire-resistant enclosure, away from suppression zone
- **Never**: Leave bare Li-ion cells without BMS/protection PCB in the same enclosure as the Pi

---

## 6. Relay Switching for Mains vs Battery

### 6.1 Automatic Switching with Schottky Diode (Simple)
- Connect mains 5V → cathode of Schottky diode (e.g., SS34, 1N5822) → Pi 5V rail
- Connect battery 5V → cathode of second Schottky diode → same Pi 5V rail
- When mains present, mains voltage is slightly higher → powers Pi, diode blocks battery
- When mains fails, battery takes over seamlessly (with 0.3–0.5V diode drop)
- **Cost**: ~$1
- **Note**: Diode drop wastes power; mains supply needs to be 5.2–5.5V to compensate

### 6.2 P-Channel MOSFET Ideal Diode (Better)
- Use P-channel MOSFET (e.g., AO3401, FQP27P06) + comparator for near-zero-drop switching
- When mains > battery, MOSFET off, mains powers Pi
- When mains < battery, MOSFET on, battery powers Pi
- **Cost**: ~$3–5
- **Note**: More efficient; no voltage drop; but requires circuit design

### 6.3 Relay-Based Switching (Isolated)
- Use 5V SPDT relay — coil powered by mains via adapter
- When mains on: relay energized, connects mains → Pi
- When mains off: relay de-energized, connects battery → Pi
- **Cost**: ~$2–4
- **Note**: Mechanical switching — may have 10–20ms dropout; Pi 5's power hold-up may handle it; use large input capacitor (1000µF+) on Pi power rail

---

## 7. Recommended Battery Backup Configuration

### Option A: Commercial HAT (Recommended for Reliability)
- **PiSugar 3 Plus** (~$50)
- **Runtime**: ~2+ hours at system load
- **Monitoring**: I2C battery percentage
- **Shutdown**: Configurable safe shutdown
- **Pros**: Cleanest, safest, best runtime
- **Cons**: Higher cost

### Option B: Budget DIY with Safety
- **IP5306 module** (~$4)
- **2× LiFePO4 18650 cells** in parallel (~$12)
- **Small BMS** (~$3)
- **ADS1115** (already in sensor budget) for voltage monitoring
- **GPIO safe shutdown script**
- **Runtime**: ~1.5–2 hours
- **Pros**: Lower cost, safer LiFePO4 chemistry
- **Cons**: More wiring, less elegant, needs enclosure

### Option C: Dual Power Supply (Most Robust)
- **Primary**: Pi 5 USB-C from mains adapter
- **Secondary**: PiJuice or PiSugar always connected ("online UPS" mode)
- **Behavior**: HAT handles all switching transparently; Pi never sees power interruption
- **Runtime**: Same as HAT capacity
- **Pros**: True UPS, simplest software
- **Cons**: Highest cost

---

## 8. Battery Backup Summary Table

| Option | Cost | Runtime | GPIO Used | Safe Shutdown | Safety | Best For |
|--------|------|---------|-----------|---------------|--------|----------|
| PiSugar 3 Plus | $50 | 2+ hrs | I2C only | Yes | Excellent | Most users |
| PiJuice + 5000mAh | $55 | 2+ hrs | I2C only | Yes | Excellent | Ecosystem maturity |
| Geekworm X728 | $45+ | 3+ hrs | I2C + GPIO | Yes | Good (cell-dependent) | Long runtime |
| DIY TP4056+MT3608 | $12 | 1.5 hrs | None | No (add ADC) | Moderate | Budget builds |
| DIY IP5306+LiFePO4 | $20 | 1.5 hrs | Optional | No (add ADC) | Good | Safe DIY |
| Adafruit PowerBoost | $18 | 1 hr | 1 GPIO (LBO) | Yes (via LBO) | Good | Simple/small |

---

## 9. Final Recommendation

For the **open-fire-suppression** project, recommend **PiSugar 3 Plus** as the primary UPS solution because:
1. Zero GPIO pin blocking (pogo pins)
2. 2+ hour runtime at system load
3. Built-in safe shutdown + RTC
4. Excellent Python API
5. No DIY soldering or circuit design needed
6. Built-in protections (overcharge, over-discharge, over-current)
7. Cleanest integration with Pi 5

If budget-constrained, the **IP5306 + LiFePO4 + ADS1115** DIY option provides a safe, affordable alternative.
