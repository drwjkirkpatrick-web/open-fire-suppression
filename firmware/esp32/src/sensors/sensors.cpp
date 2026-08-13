/**
 * sensors.cpp — Sensor implementations for ESP32
 *
 * All sensor read() methods populate the shared SensorReading struct.
 * Failed reads set valid=false and update health stats.
 * Mock mode returns plausible values for testing without hardware.
 */
#include "sensors/sensors.h"
#include "../config.h"

// ── Helper: map ADC value to voltage (ESP32 12-bit, 0–3.3V) ──────
static float adc_to_voltage(int raw) {
    return (raw / 4095.0f) * 3.3f;
}

// ═════════════════════════════════════════════════════════════════
// MQ-2 Smoke Sensor
// ═════════════════════════════════════════════════════════════════
MQ2Sensor::MQ2Sensor(const String &n, uint8_t pin)
    : BaseSensor(n), _pin(pin), _r0(10000.0f), _warmup_start(0),
      _warmed_up(false) {}

bool MQ2Sensor::begin() {
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);  // 0–3.3V range
    _warmup_start = millis();
    health.ok = true;
    return true;
}

float MQ2Sensor::_read_mq2() {
    // Read ADC, convert to Rs/R0 ratio
    int raw = analogRead(_pin);
    float v = adc_to_voltage(raw);
    if (v < 0.01f) return -1.0f;  // sensor not connected

    // Rs = (Vc/V - 1) * RL, where RL is load resistance (10kΩ)
    float rs = (3.3f / v - 1.0f) * 10000.0f;
    float ratio = rs / _r0;
    return ratio;
}

float MQ2Sensor::_adc_to_ppm(float ratio) {
    // Approximate ppm from Rs/R0 ratio using logarithmic curve
    // Based on MQ-2 datasheet for smoke/LPG:
    //   ppm = a * (ratio)^b
    //   a ≈ 599.65, b ≈ -2.244  (smoke)
    if (ratio <= 0) return 0.0f;
    float ppm = 599.65f * powf(ratio, -2.244f);
    return constrain(ppm, 0.0f, 10000.0f);
}

bool MQ2Sensor::read(SensorReading &r) {
    health.total_reads++;

    if (!_warmed_up) {
        if (millis() - _warmup_start < FS_MQ2_WARMUP_MS) {
            r.valid = false;
            health.failed++;
            health.ok = false;
            health.last_error = "warming up";
            return false;
        }
        _warmed_up = true;
    }

    float ratio = _read_mq2();
    if (ratio < 0) {
        r.valid = false;
        health.failed++;
        health.ok = false;
        health.last_error = "ADC read failed";
        return false;
    }

    r.smoke_ppm = _adc_to_ppm(ratio);
    r.valid = true;
    health.successful++;
    health.last_success = millis();
    health.ok = true;
    return true;
}

// ═════════════════════════════════════════════════════════════════
// SHT40 Temp + Humidity
// ═════════════════════════════════════════════════════════════════
SHT40Sensor::SHT40Sensor(const String &n, uint8_t addr)
    : BaseSensor(n), _addr(addr) {}

bool SHT40Sensor::begin() {
    Wire.beginTransmission(_addr);
    _present = (Wire.endTransmission() == 0);
    if (!_present) return false;

    _sht.begin();  // default I2C, high-precision, no heater
    _sht.setPrecision(SHT4X_HIGH_PRECISION);
    _sht.setHeater(SHT4X_NO_HEATER);
    sensors_event_t h, t;
    _sht.getEvent(&h, &t);
    health.ok = true;
    return true;
}

bool SHT40Sensor::read(SensorReading &r) {
    health.total_reads++;
    if (!_present) {
        r.valid = false;
        health.failed++;
        return false;
    }

    sensors_event_t h, t;
    if (!_sht.getEvent(&h, &t)) {
        r.valid = false;
        health.failed++;
        health.ok = false;
        health.last_error = "I2C read failed";
        return false;
    }

    r.temp_c = t.temperature;
    r.humidity_pct = h.relative_humidity;
    r.valid = true;
    health.successful++;
    health.last_success = millis();
    health.ok = true;
    return true;
}

// ═════════════════════════════════════════════════════════════════
// MLX90614 IR Temperature
// ═════════════════════════════════════════════════════════════════
MLX90614Sensor::MLX90614Sensor(const String &n, uint8_t addr)
    : BaseSensor(n), _addr(addr) {}

bool MLX90614Sensor::begin() {
    Wire.beginTransmission(_addr);
    _present = (Wire.endTransmission() == 0);
    if (!_present) return false;

    _mlx.begin(_addr);
    health.ok = true;
    return true;
}

bool MLX90614Sensor::read(SensorReading &r) {
    health.total_reads++;
    if (!_present) {
        r.valid = false;
        health.failed++;
        return false;
    }

    r.ir_object_c = _mlx.readObjectTempC();
    r.ir_ambient_c = _mlx.readAmbientTempC();

    if (isnan(r.ir_object_c) || r.ir_object_c < -40 || r.ir_object_c > 300) {
        r.valid = false;
        health.failed++;
        health.ok = false;
        health.last_error = "IR temp out of range";
        return false;
    }

    r.valid = true;
    health.successful++;
    health.last_success = millis();
    health.ok = true;
    return true;
}

// ═════════════════════════════════════════════════════════════════
// BME680 Environmental
// ═════════════════════════════════════════════════════════════════
BME680Sensor::BME680Sensor(const String &n, uint8_t addr)
    : BaseSensor(n), _addr(addr) {}

bool BME680Sensor::begin() {
    Wire.beginTransmission(_addr);
    _present = (Wire.endTransmission() == 0);
    if (!_present) return false;

    if (!_bme.begin(_addr)) return false;

    // Oversample settings — balanced accuracy/power
    _bme.setTemperatureOversampling(BME680_OS_2X);
    _bme.setHumidityOversampling(BME680_OS_1X);
    _bme.setPressureOversampling(BME680_OS_4X);
    _bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
    _bme.setGasHeater(320, 150);  // 320°C for 150ms

    health.ok = true;
    return true;
}

bool BME680Sensor::read(SensorReading &r) {
    health.total_reads++;
    if (!_present) {
        r.valid = false;
        health.failed++;
        return false;
    }

    if (!_bme.performReading()) {
        r.valid = false;
        health.failed++;
        health.ok = false;
        health.last_error = "BME680 read failed";
        return false;
    }

    r.temp_c = _bme.temperature;
    r.humidity_pct = _bme.humidity;
    r.pressure_hpa = _bme.pressure / 100.0f;
    r.gas_resistance = _bme.gas_resistance;

    r.valid = true;
    health.successful++;
    health.last_success = millis();
    health.ok = true;
    return true;
}

// ═════════════════════════════════════════════════════════════════
// AMG8833 8×8 Thermal Array
// ═════════════════════════════════════════════════════════════════
AMG8833Sensor::AMG8833Sensor(const String &n, uint8_t addr)
    : BaseSensor(n), _addr(addr) {
    memset(_pixels, 0, sizeof(_pixels));
}

bool AMG8833Sensor::begin() {
    Wire.beginTransmission(_addr);
    _present = (Wire.endTransmission() == 0);
    if (!_present) return false;

    if (!_amg.begin()) return false;
    health.ok = true;
    return true;
}

bool AMG8833Sensor::read(SensorReading &r) {
    health.total_reads++;
    if (!_present) {
        r.valid = false;
        health.failed++;
        return false;
    }

    _amg.readPixels(_pixels);
    memcpy(r.thermal_grid, _pixels, sizeof(_pixels));
    r.thermal_valid = true;

    r.valid = true;
    health.successful++;
    health.last_success = millis();
    health.ok = true;
    return true;
}

// ═════════════════════════════════════════════════════════════════
// DS18B20 External Temperature
// ═════════════════════════════════════════════════════════════════
DS18B20Sensor::DS18B20Sensor(const String &n, uint8_t pin)
    : BaseSensor(n), _pin(pin), _oneWire(pin), _ds(&_oneWire) {}

bool DS18B20Sensor::begin() {
    _ds.begin();
    _present = (_ds.getDeviceCount() > 0);
    if (_present) {
        _ds.setResolution(12);  // 12-bit = 0.0625°C
    }
    health.ok = _present;
    return _present;
}

bool DS18B20Sensor::read(SensorReading &r) {
    health.total_reads++;
    if (!_present) {
        r.valid = false;
        health.failed++;
        return false;
    }

    _ds.requestTemperatures();
    float t = _ds.getTempCByIndex(0);

    if (t == DEVICE_DISCONNECTED_C || t < -55 || t > 125) {
        r.valid = false;
        health.failed++;
        health.ok = false;
        health.last_error = "DS18B20 disconnected";
        return false;
    }

    r.ext_temp_c = t;
    r.valid = true;
    health.successful++;
    health.last_success = millis();
    health.ok = true;
    return true;
}

// ═════════════════════════════════════════════════════════════════
// Sensor Manager
// ═════════════════════════════════════════════════════════════════
SensorManager::SensorManager() : _count(0) {
    memset(_sensors, 0, sizeof(_sensors));
}

SensorManager::~SensorManager() {
    for (size_t i = 0; i < _count; i++) {
        delete _sensors[i];
    }
}

void SensorManager::_add(BaseSensor *s) {
    if (_count < MAX_SENSORS) {
        _sensors[_count++] = s;
    }
}

void SensorManager::begin() {
    Wire.begin(FS_I2C_SDA, FS_I2C_SCL, FS_I2C_FREQ);

    _add(new MQ2Sensor("mq2", FS_MQ2_ADC_PIN));
    _add(new SHT40Sensor("sht40", FS_SHT40_ADDR));
    _add(new MLX90614Sensor("mlx90614", FS_MLX90614_ADDR));
    _add(new BME680Sensor("bme680", FS_BME680_ADDR));
    _add(new AMG8833Sensor("amg8833", FS_AMG8833_ADDR));
    _add(new DS18B20Sensor("ds18b20", FS_DS18B20_PIN));

    for (size_t i = 0; i < _count; i++) {
        bool ok = _sensors[i]->begin();
        Serial.printf("  [%s] %s\n",
                      ok ? "OK" : "--",
                      _sensors[i]->name.c_str());
    }
}

void SensorManager::poll_all(SensorReading &r) {
    memset(&r, 0, sizeof(r));
    r.timestamp = millis();
    r.valid = false;
    r.thermal_valid = false;

    // Initialize defaults
    r.smoke_ppm = 0;
    r.temp_c = NAN;
    r.humidity_pct = NAN;
    r.ir_object_c = NAN;
    r.ir_ambient_c = NAN;
    r.gas_resistance = NAN;
    r.pressure_hpa = NAN;
    r.ext_temp_c = NAN;

    bool any_valid = false;

    for (size_t i = 0; i < _count; i++) {
        SensorReading tmp;
        memset(&tmp, 0, sizeof(tmp));
        tmp.valid = false;
        tmp.thermal_valid = false;

        if (_sensors[i]->read(tmp)) {
            any_valid = true;
            // Merge fields
            if (tmp.smoke_ppm > 0)     r.smoke_ppm = tmp.smoke_ppm;
            if (!isnan(tmp.temp_c))   r.temp_c = tmp.temp_c;
            if (!isnan(tmp.humidity_pct)) r.humidity_pct = tmp.humidity_pct;
            if (!isnan(tmp.ir_object_c)) r.ir_object_c = tmp.ir_object_c;
            if (!isnan(tmp.ir_ambient_c)) r.ir_ambient_c = tmp.ir_ambient_c;
            if (!isnan(tmp.gas_resistance)) r.gas_resistance = tmp.gas_resistance;
            if (!isnan(tmp.pressure_hpa)) r.pressure_hpa = tmp.pressure_hpa;
            if (!isnan(tmp.ext_temp_c)) r.ext_temp_c = tmp.ext_temp_c;
            if (tmp.thermal_valid) {
                memcpy(r.thermal_grid, tmp.thermal_grid, sizeof(r.thermal_grid));
                r.thermal_valid = true;
            }
        }
    }

    r.valid = any_valid;
}

size_t SensorManager::healthy_count() const {
    size_t n = 0;
    for (size_t i = 0; i < _count; i++) {
        if (_sensors[i]->health.ok) n++;
    }
    return n;
}

void SensorManager::print_status() const {
    Serial.println("── Sensor Status ──");
    for (size_t i = 0; i < _count; i++) {
        const auto &h = _sensors[i]->health;
        Serial.printf("  %-12s ok=%d reads=%u rate=%.1f%% err=%s\n",
                       _sensors[i]->name.c_str(),
                       h.ok, h.total_reads,
                       h.success_rate() * 100,
                       h.last_error.c_str());
    }
}