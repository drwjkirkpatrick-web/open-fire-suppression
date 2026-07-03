# Fire Detection Sensor Research Report
## For Raspberry Pi 5 (8GB RAM) — open-fire-suppression Project
### Date: July 2026

---

## 1. Smoke Detectors

### 1.1 MQ-2 (Combustible Gas & Smoke)
- **Interface**: Analog (requires ADC like MCP3008 or ADS1115)
- **Voltage**: 5V
- **Cost**: ~$2–4
- **Python library**: `gpiozero`, `Adafruit_GPIO` + custom ADC driver
- **Specs**: Detects LPG, propane, methane, hydrogen, smoke (300–10000 ppm)
- **Fire relevance**: Good for early smoke detection; analog output gives concentration levels; requires warm-up time (~1 min)
- **Note**: Needs external ADC — Pi 5 has no native analog input. Consider MCP3008 (SPI, 10-bit) or ADS1115 (I2C, 16-bit, better resolution).

### 1.2 MQ-135 (Air Quality / Smoke)
- **Interface**: Analog (requires ADC)
- **Voltage**: 5V
- **Cost**: ~$2–4
- **Python library**: Same as MQ-2
- **Specs**: Detects NH3, NOx, alcohol, benzene, smoke, CO2 (10–1000 ppm)
- **Fire relevance**: Good for detecting toxic gases from fire; less specific than MQ-2 for smoke
- **Note**: Also needs ADC; cross-sensitive to humidity/temp — needs calibration

### 1.3 Sharp GP2Y1010AU0F (Optical Dust Sensor)
- **Interface**: Analog output + digital control pin
- **Voltage**: 5V
- **Cost**: ~$8–12
- **Python library**: Custom (read analog via ADC, toggle LED with GPIO)
- **Specs**: 0–580 µg/m³ dust density, 6° detection angle
- **Fire relevance**: Detects particulate matter (smoke particles); active optical method is more reliable than MQ series
- **Note**: Requires ADC; pulse LED on GPIO to take readings; good for indoor air quality monitoring

### 1.4 PPD42NS (Shinyei Optical Dust Sensor)
- **Interface**: Digital pulse (LOW pulse width proportional to dust)
- **Voltage**: 5V
- **Cost**: ~$10–15
- **Python library**: Custom pulse-width measurement with `gpiozero`
- **Specs**: Detects PM2.5/PM10, ~1 µm particle sensitivity
- **Fire relevance**: Digital output easier than analog; pulse width varies with smoke concentration
- **Note**: No ADC needed — just GPIO timing measurement

### 1.5 Recommended: ADS1115 + MQ-2 Combo
- ADS1115 is 16-bit I2C ADC (~$3–5) — far superior to MCP3008 for this use case
- 4 channels = can connect MQ-2, MQ-135, and 2 other analog sensors
- Library: `adafruit-circuitpython-ads1x15`

---

## 2. Temperature Sensors

### 2.1 DS18B20 (1-Wire Digital Thermometer)
- **Interface**: 1-Wire (GPIO with 4.7kΩ pull-up)
- **Voltage**: 3.3V or 5V
- **Cost**: ~$2–4 (waterproof version ~$4–6)
- **Python library**: `w1thermsensor`
- **Specs**: -55°C to +125°C, ±0.5°C accuracy (9–12 bit configurable), up to 12 sensors on one bus
- **Fire relevance**: Waterproof version can be placed in hot zones; multi-drop bus for zone monitoring; accurate enough for thermal thresholds
- **Note**: Requires enabling 1-Wire in `/boot/firmware/config.txt` on Pi 5

### 2.2 DHT22/AM2302 (Temp + Humidity)
- **Interface**: Single-wire digital (GPIO)
- **Voltage**: 3.3V or 5V
- **Cost**: ~$5–8
- **Python library**: `Adafruit_DHT` (deprecated) → `adafruit-circuitpython-dht`
- **Specs**: -40°C to +80°C, ±0.5°C accuracy; humidity 0–100% RH, ±2–5%
- **Fire relevance**: Good for ambient monitoring; slow response time (2–10s) not ideal for fast fire detection
- **Note**: Can be finicky on Linux — timing-sensitive; consider SHT30/40 instead

### 2.3 BME680 (Temp + Humidity + Pressure + Gas IAQ)
- **Interface**: I2C (default 0x76 or 0x77)
- **Voltage**: 3.3V
- **Cost**: ~$8–15
- **Python library**: `adafruit-circuitpython-bme680` or `bme680` (Bosch official)
- **Specs**: -40°C to +85°C, ±1°C accuracy; humidity ±3%; pressure ±0.12 hPa; gas resistance for IAQ
- **Fire relevance**: Multi-sensor in one package; gas resistance changes with combustion byproducts; excellent for ambient baseline monitoring
- **Note**: I2C address must be checked; Bosch BSEC library (proprietary) gives IAQ index; open-source alternatives exist

### 2.4 MLX90614 (Infrared Thermometer — Contactless)
- **Interface**: I2C (0x5A default, configurable to 0x5B)
- **Voltage**: 3.3V
- **Cost**: ~$10–18
- **Python library**: `adafruit-circuitpython-mlx90614` or `mlx90614` (SMBus)
- **Specs**: -70°C to +380°C (object temp), ±0.5°C accuracy (medical), ±1°C (industrial), 90° FOV
- **Fire relevance**: CRITICAL — non-contact surface temperature; can detect hot spots without placing sensor in danger zone; 380°C max is sufficient for early fire detection
- **Note**: Multiple versions (BAA = 90° FOV, BCC = 10° FOV); the narrow FOV is better for spot detection

### 2.5 TMP117 (Ultra-Precision Temp)
- **Interface**: I2C (0x48–0x4B configurable)
- **Voltage**: 1.8V–5.5V (3.3V on Pi)
- **Cost**: ~$5–8
- **Python library**: `adafruit-circuitpython-tmp117`
- **Specs**: -55°C to +125°C, ±0.1°C accuracy (excellent!)
- **Fire relevance**: Best accuracy for baseline/reference temperatures; can be placed in controlled zone to detect ambient changes
- **Note**: Expensive but very stable; great for differential temperature calculations

---

## 3. Humidity Sensors

### 3.1 SHT30 / SHT40 (Sensirion — Temp + Humidity)
- **Interface**: I2C (0x44 or 0x45)
- **Voltage**: 3.3V
- **Cost**: SHT30 ~$4–6, SHT40 ~$5–8
- **Python library**: `adafruit-circuitpython-sht31d` (works for SHT30), `adafruit-circuitpython-sht4x`
- **Specs**: SHT30: -40°C to +125°C, ±0.3°C; humidity 0–100% RH, ±2%
- **Fire relevance**: Fast response (~8s); humidity DROP is an early fire indicator (fire consumes moisture); SHT40 has better accuracy
- **Note**: Highly recommended over DHT22 — far more reliable, no timing issues

### 3.2 BME680 (see above)
- Already covers humidity; good all-in-one for baseline monitoring

---

## 4. Infrared Flame Detectors

### 4.1 KY-026 (Flame Sensor Module)
- **Interface**: Analog + Digital (GPIO)
- **Voltage**: 3.3V or 5V
- **Cost**: ~$1–3
- **Python library**: Custom (`gpiozero` for digital, ADC for analog)
- **Specs**: Detects 760–1100 nm IR (flame spectrum), detection angle ~60°, range ~1m
- **Fire relevance**: CHEAP and fast response; detects flame flicker; limited range and angle
- **Note**: Very basic — prone to IR from sunlight, incandescent bulbs; use as supplementary only

### 4.2 RPi IR Flame Sensor (e.g., Keyestudio Flame Sensor)
- **Interface**: Analog + Digital
- **Voltage**: 3.3V
- **Cost**: ~$3–5
- **Python library**: Custom
- **Specs**: Similar to KY-026 with better filtering
- **Fire relevance**: Better filtering than KY-026 but still basic

### 4.3 Recommended: Multiple MLX90614 + Software Detection
- Instead of a dedicated flame sensor, use MLX90614 pointed at potential fire zones
- Combine with algorithmic flicker detection (flames flicker at 1–12 Hz)
- Much more reliable than simple IR detectors

---

## 5. Thermal Camera Modules

### 5.1 AMG8833 (Panasonic 8×8 Thermal Camera)
- **Interface**: I2C (0x68 or 0x69)
- **Voltage**: 3.3V
- **Cost**: ~$25–40
- **Python library**: `adafruit-circuitpython-amg88xx`
- **Specs**: 8×8 pixels (64 thermal points), 0°C to 80°C (high-gain mode: -20°C to 80°C), ±2.5°C accuracy, 60° FOV
- **Fire relevance**: Can detect heat buildup across a grid; good for zone monitoring; low resolution but sufficient for fire hotspot detection
- **Note**: I2C is easy; 8×8 is coarse — works for area monitoring but not detailed imaging

### 5.2 MLX90640 (Melexis 32×24 Thermal Camera)
- **Interface**: I2C (0x33)
- **Voltage**: 3.3V
- **Cost**: ~$50–70
- **Python library**: `adafruit-circuitpython-mlx90640` or `pimoroni` drivers
- **Specs**: 32×24 pixels (768 points), -40°C to +300°C, ±1°C accuracy, 110°×75° FOV, 64 Hz refresh
- **Fire relevance**: MUCH better resolution for fire detection; 300°C max is sufficient; can track fire spread direction
- **Note**: Higher I2C speed recommended (400kHz or 1MHz); may need `smbus2` instead of standard SMBus; processing 768 points takes CPU but Pi 5 handles it easily

### 5.3 MLX90641 (Melexis 16×12 Thermal Camera)
- **Interface**: I2C (0x33)
- **Voltage**: 3.3V
- **Cost**: ~$35–50
- **Python library**: Same as MLX90640
- **Specs**: 16×12 pixels (192 points), -40°C to +300°C, ±1°C accuracy, 100°×75° FOV
- **Fire relevance**: Good middle ground between AMG8833 and MLX90640; lower cost, still effective
- **Note**: Less common than MLX90640 but available from some vendors

### 5.4 Thermal Camera Recommendation for Fire Suppression
- **Best**: MLX90640 — excellent resolution for fire detection algorithms
- **Budget**: AMG8833 — sufficient for basic hotspot detection
- **Alternative**: FLIR Lepton 3.5 (160×120, SPI) — ~$200, much higher resolution but more expensive

---

## 6. Video-Based Fire Detection

### 6.1 Raspberry Pi Camera Module 3
- **Interface**: CSI-2 (dedicated camera connector on Pi 5)
- **Voltage**: 3.3V (powered via CSI cable)
- **Cost**: ~$35–45 (Wide ~$40–50)
- **Python library**: `picamera2` (official, modern), `libcamera`
- **Specs**: 12MP Sony IMX708 sensor, HDR, auto-focus, 75° or 120° FOV (wide)
- **Fire relevance**: High-resolution color video for AI-based fire detection; can detect smoke (gray/white plumes), flame color (orange/red), and movement; HDR helps with bright flames
- **Note**: Pi 5 has two CSI connectors (camera 0 and camera 1) — can run dual cameras

### 6.2 Raspberry Pi Camera Module 3 Wide
- Same as above but 120° FOV — better for monitoring larger areas

### 6.3 USB Camera (e.g., Logitech C920/C270)
- **Interface**: USB 3.0/2.0
- **Voltage**: 5V (USB powered)
- **Cost**: ~$25–80
- **Python library**: `opencv-python` (`cv2`)
- **Specs**: 1080p@30fps, auto-focus
- **Fire relevance**: Easy to set up; OpenCV compatible; can be placed farther from Pi via USB extension
- **Note**: Higher latency than CSI; USB bandwidth limitations with multiple cameras

### 6.4 AI Fire Detection Approaches
- **OpenCV + Color Thresholding**: HSV filtering for orange/red/yellow (flame) and gray/white (smoke) — simple, fast, no ML needed
- **YOLOv8/v9**: Train or use pre-trained fire/smoke detection models — runs on Pi 5 with ONNX or TFLite at ~5–15 FPS
- **Background Subtraction + Motion**: Detect sudden bright areas or smoke plume movement
- **Hybrid**: Color + motion + thermal camera data fusion = highest accuracy

### 6.5 Pre-trained Models
- `fire_detection_yolov5` / `yolov8` — available on Roboflow and Hugging Face (but note user's blocklist preference)
- Train custom with Roboflow → export to TFLite for Pi 5 inference
- **NCNN** framework for ARM inference optimization (Pi 5's VideoCore VII GPU)

---

## 7. Other Useful Sensors

### 7.1 CCS811 / ENS160 (VOC / eCO2 Sensor)
- **Interface**: I2C (0x5A for CCS811, 0x53 for ENS160)
- **Voltage**: 3.3V
- **Cost**: ~$10–15
- **Python library**: `adafruit-circuitpython-ccs811` / `adafruit-circuitpython-ens160` or `ScioSense_ENS160`
- **Specs**: CCS811: eCO2 400–8192 ppm, TVOC 0–1187 ppb; ENS160: better replacement with more stable readings
- **Fire relevance**: Detects volatile organic compounds released during combustion; IAQ degradation early indicator
- **Note**: CCS811 has known stability issues; prefer ENS160

### 7.2 MH-Z19 / SCD4x (CO2 Sensor)
- **Interface**: UART (MH-Z19) or I2C (SCD41)
- **Voltage**: 5V (MH-Z19), 3.3V (SCD41)
- **Cost**: MH-Z19 ~$20, SCD41 ~$25–35
- **Python library**: `mh-z19` / `adafruit-circuitpython-scd4x`
- **Specs**: 0–5000 ppm (MH-Z19B), ±50 ppm accuracy (SCD41)
- **Fire relevance**: CO2 spike during combustion; SCD41 is highly accurate and small
- **Note**: MH-Z19 needs 5V UART level shifter for Pi 3.3V GPIO; SCD41 is 3.3V-native

### 7.3 ADXL345 / MPU6050 (Vibration/Accelerometer)
- **Interface**: I2C (0x53 for ADXL345, 0x68 for MPU6050)
- **Voltage**: 3.3V
- **Cost**: ~$3–6
- **Python library**: `adafruit-circuitpython-adxl34x` / `mpu6050-raspberrypi`
- **Specs**: ±2/4/8/16g (ADXL345), 3-axis accel + gyro (MPU6050)
- **Fire relevance**: Detects structural vibration from explosions, collapsing materials, or suppression system activation
- **Note**: Useful for post-fire structural assessment; optional

### 7.4 RCWL-0516 (Microwave Radar Motion Sensor)
- **Interface**: Digital (GPIO)
- **Voltage**: 3.3V–5V
- **Cost**: ~$2–4
- **Python library**: `gpiozero`
- **Specs**: 360° detection, 5–9m range, penetrates walls (not ideal for fire zones)
- **Fire relevance**: Detects occupant movement for evacuation confirmation; can work through smoke (better than PIR)
- **Note**: May detect through walls — position carefully

---

## 8. Sensor Summary Table

| Sensor | Interface | Voltage | Cost | Library | Key Fire Role |
|--------|-----------|---------|------|---------|---------------|
| MQ-2 (smoke/gas) | Analog via ADS1115 | 5V | $3 | Custom + ADC | Early smoke detection |
| Sharp GP2Y1010AU0F | Analog via ADS1115 | 5V | $10 | Custom + ADC | PM/smoke particles |
| DS18B20 | 1-Wire (GPIO) | 3.3V/5V | $4 | `w1thermsensor` | Zone temperature |
| SHT40 | I2C | 3.3V | $6 | `adafruit-circuitpython-sht4x` | Humidity drop detection |
| BME680 | I2C | 3.3V | $12 | `bme680` | Multi-sensor ambient IAQ |
| MLX90614 | I2C | 3.3V | $14 | `adafruit-circuitpython-mlx90614` | Contactless hotspot detection |
| AMG8833 | I2C | 3.3V | $32 | `adafruit-circuitpython-amg88xx` | 8×8 thermal grid |
| MLX90640 | I2C | 3.3V | $60 | `adafruit-circuitpython-mlx90640` | 32×24 thermal imaging |
| Pi Camera Module 3 | CSI-2 | 3.3V | $40 | `picamera2` | Video fire/smoke AI detection |
| ENS160 | I2C | 3.3V | $12 | `ScioSense_ENS160` | VOC/combustion byproducts |
| SCD41 | I2C | 3.3V | $30 | `adafruit-circuitpython-scd4x` | CO2 spike detection |
| ADS1115 | I2C | 3.3V/5V | $4 | `adafruit-circuitpython-ads1x15` | ADC for analog sensors |

---

## 9. Recommended Minimum Setup

For a **cost-effective but capable** fire suppression system on Pi 5:

1. **ADS1115** ($4) — 4-channel ADC for analog sensors
2. **MQ-2** ($3) — Smoke/gas detection
3. **SHT40** ($6) — Temperature + humidity (fast, reliable)
4. **MLX90614** ($14) — Non-contact IR temperature
5. **Pi Camera Module 3** ($40) — Video fire detection
6. **ENS160** ($12) — VOC/air quality

**Total sensor cost: ~$79** (without cabling, HATs, enclosure)

For a **premium setup**, add:
7. **MLX90640** ($60) — Thermal camera
8. **Sharp GP2Y1010AU0F** ($10) — Optical dust/smoke
9. **DS18B20 waterproof** ($5) — Zone temperature probe
10. **SCD41** ($30) — CO2 monitoring

**Premium total: ~$184**

---

## 10. Wiring Notes for Pi 5

- **I2C**: GPIO 2 (SDA) + GPIO 3 (SCL) — enable with `raspi-config` or `config.txt`
- **1-Wire**: GPIO 4 — enable in `/boot/firmware/config.txt` with `dtoverlay=w1-gpio`
- **SPI**: GPIO 9 (MISO), 10 (MOSI), 11 (SCLK), 8 (CE0) — for MCP3008 if using SPI ADC
- **CSI-2**: Dedicated camera ports (CAM0, CAM1) — use ribbon cable
- **Power**: Pi 5 requires 5V 3A minimum via USB-C; sensors draw minimal current (<200mA total)
- **Level shifting**: Most sensors listed are 3.3V-compatible; only MQ series and Sharp need 5V for heater, but output can be read at 3.3V if using ADS1115 at 5V (use logic level shifter or power ADS1115 at 3.3V)
