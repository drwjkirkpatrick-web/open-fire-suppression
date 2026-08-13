/**
 * sensors.h — Sensor abstraction layer for ESP32
 *
 * Ports the Python BaseSensor / SensorManager pattern to C++.
 * Each sensor has a begin() and read() method. SensorReading
 * mirrors the Python SensorReading dataclass.
 *
 * Supported sensors:
 *   MQ-2     — smoke (analog ADC)
 *   SHT40    — temp + humidity (I2C)
 *   MLX90614 — IR object temp (I2C)
 *   BME680   — temp + humidity + pressure + gas (I2C)
 *   AMG8833  — 8×8 thermal array (I2C)
 *   DS18B20  — external temp probe (OneWire)
 */
#ifndef FIRE_SUPPRESSION_SENSORS_H
#define FIRE_SUPPRESSION_SENSORS_H

#include <Arduino.h>
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_SHT4x.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_BME680.h>
#include <Adafruit_AMG88xx.h>
#include "../types.h"

// ── Base Sensor ──────────────────────────────────────────────────
class BaseSensor {
public:
    String name;
    SensorHealth health;

    BaseSensor(const String &n) : name(n) {}
    virtual ~BaseSensor() {}

    virtual bool begin() = 0;
    virtual bool read(SensorReading &r) = 0;
    virtual bool is_present() = 0;
};

// ── MQ-2 Smoke Sensor (ADC) ──────────────────────────────────────
class MQ2Sensor : public BaseSensor {
public:
    MQ2Sensor(const String &n, uint8_t pin);
    bool begin() override;
    bool read(SensorReading &r) override;
    bool is_present() override { return true; }  // always on ADC

private:
    uint8_t  _pin;
    float    _r0;            // calibrated clean-air resistance
    uint32_t _warmup_start;
    bool     _warmed_up;
    float    _read_mq2();
    float    _adc_to_ppm(float ratio);
};

// ── SHT40 Temp + Humidity (I2C) ──────────────────────────────────
class SHT40Sensor : public BaseSensor {
public:
    SHT40Sensor(const String &n, uint8_t addr);
    bool begin() override;
    bool read(SensorReading &r) override;
    bool is_present() override { return _present; }

private:
    uint8_t            _addr;
    bool               _present = false;
    Adafruit_SHT4x     _sht;
};

// ── MLX90614 IR Temp (I2C) ───────────────────────────────────────
class MLX90614Sensor : public BaseSensor {
public:
    MLX90614Sensor(const String &n, uint8_t addr);
    bool begin() override;
    bool read(SensorReading &r) override;
    bool is_present() override { return _present; }

private:
    uint8_t              _addr;
    bool                 _present = false;
    Adafruit_MLX90614    _mlx;
};

// ── BME680 Environmental (I2C) ──────────────────────────────────
class BME680Sensor : public BaseSensor {
public:
    BME680Sensor(const String &n, uint8_t addr);
    bool begin() override;
    bool read(SensorReading &r) override;
    bool is_present() override { return _present; }

private:
    uint8_t           _addr;
    bool              _present = false;
    Adafruit_BME680   _bme;
};

// ── AMG8833 8×8 Thermal Array (I2C) ──────────────────────────────
class AMG8833Sensor : public BaseSensor {
public:
    AMG8833Sensor(const String &n, uint8_t addr);
    bool begin() override;
    bool read(SensorReading &r) override;
    bool is_present() override { return _present; }

private:
    uint8_t            _addr;
    bool               _present = false;
    Adafruit_AMG88xx   _amg;
    float              _pixels[64];
};

// ── DS18B20 External Temp (OneWire) ──────────────────────────────
class DS18B20Sensor : public BaseSensor {
public:
    DS18B20Sensor(const String &n, uint8_t pin);
    bool begin() override;
    bool read(SensorReading &r) override;
    bool is_present() override { return _present; }

private:
    uint8_t              _pin;
    bool                 _present = false;
    OneWire              _oneWire;
    DallasTemperature    _ds;
};

// ── Sensor Manager (mirrors Python SensorManager) ────────────────
class SensorManager {
public:
    SensorManager();
    ~SensorManager();

    void   begin();                          // init all sensors
    void   poll_all(SensorReading &r);       // read all into one struct
    size_t count() const { return _count; }
    size_t healthy_count() const;
    void   print_status() const;             // serial debug

private:
    static const size_t MAX_SENSORS = 6;
    BaseSensor *_sensors[MAX_SENSORS];
    size_t       _count = 0;
    void _add(BaseSensor *s);
};

#endif // FIRE_SUPPRESSION_SENSORS_H