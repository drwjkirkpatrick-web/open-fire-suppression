"""open-fire-suppression sensors package."""
from fire_suppression.sensors.ads1115 import ADS1115Sensor
from fire_suppression.sensors.amg8833 import AMG8833Sensor
from fire_suppression.sensors.base import BaseSensor, MockSensor, SensorHealth, SensorReading, SensorStatus
from fire_suppression.sensors.bme680 import BME680Sensor
from fire_suppression.sensors.ds18b20 import DS18B20Sensor
from fire_suppression.sensors.ens160 import ENS160Sensor
from fire_suppression.sensors.i2c import i2c_device_present, scan_i2c_bus
from fire_suppression.sensors.mlx90614 import MLX90614Sensor
from fire_suppression.sensors.mlx90640 import MLX90640Sensor
from fire_suppression.sensors.mq2 import MQ2Sensor
from fire_suppression.sensors.picamera import PiCameraSensor
from fire_suppression.sensors.sht40 import SHT40Sensor

__all__ = [
    "BaseSensor",
    "MockSensor",
    "SensorReading",
    "SensorHealth",
    "SensorStatus",
    "ADS1115Sensor",
    "MQ2Sensor",
    "SHT40Sensor",
    "MLX90614Sensor",
    "BME680Sensor",
    "ENS160Sensor",
    "AMG8833Sensor",
    "MLX90640Sensor",
    "DS18B20Sensor",
    "PiCameraSensor",
    "scan_i2c_bus",
    "i2c_device_present",
    "SensorManager",
]
