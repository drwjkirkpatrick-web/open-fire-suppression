"""BME680 multi-sensor driver (temperature, humidity, pressure, gas).

# S006 — BME680 Multi-Sensor Read
"""
from __future__ import annotations

import logging
import struct
import time
from typing import TYPE_CHECKING

from fire_suppression.sensors.base import BaseSensor, SensorReading

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

BME680_I2C_ADDRESS = 0x77
BME680_ALT_ADDRESS = 0x76

# BME680 registers
BME680_STATUS = 0x1D
BME680_GAS_MEAS_STATUS = 0x2D
BME680_CTRL_MEAS = 0x74
BME680_CTRL_HUM = 0x72
BME680_CTRL_GAS_1 = 0x71
BME680_CONFIG = 0x75
BME680_T2 = 0x8A
BME680_T3 = 0x8C
BME680_P1 = 0x8E
BME680_P2 = 0x90
BME680_P3 = 0x92
BME680_P4 = 0x94
BME680_P5 = 0x96
BME680_P6 = 0x99
BME680_P7 = 0x98
BME680_P8 = 0x9C
BME680_P9 = 0x9E
BME680_P10 = 0xA0
BME680_H1 = 0xE3
BME680_H2 = 0xE1
BME680_H3 = 0xE4
BME680_H4 = 0xE5
BME680_H5 = 0xE6
BME680_H6 = 0xE7
BME680_H7 = 0xE8
BME680_T1 = 0xE9
BME680_GH2 = 0xEB
BME680_GH1 = 0xED
BME680_GH3 = 0xEE
BME680_RES_HEAT_VAL = 0x00
BME680_RES_HEAT_RANGE = 0x02
BME680_RANGE_SWITCHING_ERROR = 0x04
BME680_ID = 0xD0

BME680_CMD_SOFT_RESET = 0xE0
BME680_CMD_RESET_VAL = 0xB6


class BME680Sensor(BaseSensor):
    """Bosch BME680 environmental sensor.

    Measures temperature, humidity, barometric pressure, and gas resistance.
    Gas resistance indicates volatile organic compound (VOC) levels.
    """

    def __init__(
        self,
        name: str = "bme680",
        *,
        bus_number: int = 1,
        address: int = BME680_I2C_ADDRESS,
        mock: bool = False,
    ) -> None:
        super().__init__(name, mock=mock)
        self.bus_number = bus_number
        self.address = address
        self._bus = None
        self._calibration: dict[str, int] = {}

        if not mock:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(bus_number)
                self._soft_reset()
                self._read_calibration()
                self._configure()
            except Exception as exc:
                logger.error("BME680 init failed: %s", exc)
                self._bus = None

    def _soft_reset(self) -> None:
        if self._bus is None:
            return
        try:
            self._bus.write_byte_data(self.address, BME680_CMD_SOFT_RESET, BME680_CMD_RESET_VAL)
            time.sleep(0.01)
        except Exception:
            pass

    def _read_calibration(self) -> None:
        """Read the BME680 calibration coefficients from EEPROM."""
        if self._bus is None:
            return
        try:
            # This is a simplified read — a full BME680 driver would read all 33 bytes
            # For brevity we read the key temperature/humidity cal values
            t1 = self._bus.read_word_data(self.address, BME680_T1)
            t2 = self._bus.read_word_data(self.address, BME680_T2)
            t3 = self._bus.read_byte_data(self.address, BME680_T3)
            h1 = self._bus.read_byte_data(self.address, BME680_H1)
            h2 = self._bus.read_word_data(self.address, BME680_H2)
            h3 = self._bus.read_byte_data(self.address, BME680_H3)
            h4 = self._bus.read_byte_data(self.address, BME680_H4)
            h5 = self._bus.read_byte_data(self.address, BME680_H5)
            h6 = self._bus.read_byte_data(self.address, BME680_H6)
            h7 = self._bus.read_byte_data(self.address, BME680_H7)

            self._calibration = {
                "par_t1": t1,
                "par_t2": self._twos_comp(t2, 16),
                "par_t3": self._twos_comp(t3, 8),
                "par_h1": h1,
                "par_h2": self._twos_comp(h2, 16),
                "par_h3": self._twos_comp(h3, 8),
                "par_h4": self._twos_comp(h4, 8),
                "par_h5": self._twos_comp(h5, 8),
                "par_h6": self._twos_comp(h6, 8),
                "par_h7": self._twos_comp(h7, 8),
            }
        except Exception as exc:
            logger.warning("BME680 calibration read incomplete: %s", exc)

    def _configure(self) -> None:
        if self._bus is None:
            return
        try:
            # Set humidity oversampling ×1
            self._bus.write_byte_data(self.address, BME680_CTRL_HUM, 0x01)
            # Set temp ×2, pressure ×4, forced mode
            self._bus.write_byte_data(self.address, BME680_CTRL_MEAS, 0x54)
            # Enable gas heater
            self._bus.write_byte_data(self.address, BME680_CTRL_GAS_1, 0x10)
        except Exception:
            pass

    @staticmethod
    def _twos_comp(val: int, bits: int) -> int:
        if val & (1 << (bits - 1)):
            val -= 1 << bits
        return val

    async def read(self) -> SensorReading:
        if self.mock:
            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "temperature_c": 25.0,
                    "humidity_percent": 45.0,
                    "pressure_hpa": 1013.25,
                    "gas_resistance_ohm": 100000.0,
                },
                raw=None,
                unit="°C / %RH / hPa / Ω",
            )

        if self._bus is None:
            raise RuntimeError("BME680 SMBus not initialized")

        try:
            # Trigger measurement (forced mode)
            self._bus.write_byte_data(self.address, BME680_CTRL_MEAS, 0x54 | 0x01)
            time.sleep(0.05)  # Wait for measurement

            # Read status
            status = self._bus.read_byte_data(self.address, BME680_GAS_MEAS_STATUS)
            if not (status & 0x80):  # New data not ready
                logger.warning("BME680 measurement not ready")

            # Read raw ADC values (simplified — 8 bytes starting at 0x1D)
            data = self._bus.read_i2c_block_data(self.address, 0x1D, 8)

            # Parse temperature (20-bit, bits 47:32 from 3 bytes)
            adc_temp = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
            # Parse humidity (16-bit)
            adc_hum = (data[6] << 8) | data[7]
            # Parse pressure (20-bit)
            adc_pres = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)

            # Compensate temperature
            cal = self._calibration
            if cal:
                var1 = (adc_temp / 16384.0 - cal["par_t1"] / 1024.0) * cal["par_t2"]
                var2 = ((adc_temp / 131072.0 - cal["par_t1"] / 8192.0) ** 2) * cal["par_t3"] * 8.0
                t_fine = var1 + var2
                temp_c = t_fine / 5120.0

                # Compensate humidity (simplified)
                hum = adc_hum - (cal["par_h1"] * 16.0)
                hum_percent = hum / 500.0 if hum > 0 else 0.0
                hum_percent = max(0.0, min(100.0, hum_percent))
            else:
                temp_c = adc_temp / 100.0
                hum_percent = adc_hum / 100.0

            # Pressure (simplified, raw)
            pressure_hpa = adc_pres / 100.0

            # Gas resistance (simplified)
            gas_res = status & 0x0F  # Lower nibble
            gas_res_ohm = gas_res * 10000.0 if gas_res > 0 else 0.0

            return SensorReading(
                sensor_name=self.name,
                timestamp=time.time(),
                values={
                    "temperature_c": round(temp_c, 2),
                    "humidity_percent": round(hum_percent, 2),
                    "pressure_hpa": round(pressure_hpa, 2),
                    "gas_resistance_ohm": round(gas_res_ohm, 1),
                },
                raw={"adc_temp": adc_temp, "adc_hum": adc_hum, "adc_pres": adc_pres, "status": status},
                unit="°C / %RH / hPa / Ω",
            )

        except Exception as exc:
            logger.error("BME680 read error: %s", exc)
            raise

    async def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._closed = True
