import math
import json
from collections import namedtuple

CalibrationData = namedtuple('CalibrationData', ['temp_offset', 'humidity_offset'])

class SensorCalibrator:
    """Manage calibration data for sensors."""

    def __init__(self, config_path='/sd/calibration.json'):
        self.config_path = config_path
        self.calibrations = {}
        self._load_calibrations()

    def _load_calibrations(self):
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            for sensor, cal in data.items():
                self.calibrations[sensor] = CalibrationData(
                    temp_offset=cal.get('temp_offset', 0.0),
                    humidity_offset=cal.get('humidity_offset', 0.0)
                )
        except (OSError, ValueError):
            self.calibrations = {
                'innen': CalibrationData(0.0, 0.0),
                'aussen': CalibrationData(0.0, 0.0)
            }

    def save_calibrations(self):
        data = {
            name: {'temp_offset': cal.temp_offset,
                   'humidity_offset': cal.humidity_offset}
            for name, cal in self.calibrations.items()
        }
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print('Calibration save error:', e)

    def apply_calibration(self, sensor_name, temp, humidity):
        cal = self.calibrations.get(sensor_name, CalibrationData(0.0, 0.0))
        temp = temp + cal.temp_offset
        hum = max(0, min(100, humidity + cal.humidity_offset))
        return temp, hum

    def set_calibration(self, sensor_name, temp_offset, humidity_offset):
        self.calibrations[sensor_name] = CalibrationData(temp_offset, humidity_offset)
        self.save_calibrations()


class TaupunktCalculator:
    """Utility for dew point calculations and risk evaluation."""

    @staticmethod
    def calculate_dew_point(temp, humidity):
        if humidity <= 0 or humidity > 100:
            return float('nan')
        a = 17.27
        b = 237.7
        alpha = ((a * temp) / (b + temp)) + math.log(humidity / 100.0)
        dew_point = (b * alpha) / (a - alpha)
        return round(dew_point, 2)

    @staticmethod
    def evaluate_condensation_risk(indoor_dp, outdoor_temp, threshold=2.0):
        if math.isnan(indoor_dp) or math.isnan(outdoor_temp):
            return 'unknown', 'Sensor-Daten ungültig'
        diff = outdoor_temp - indoor_dp
        if diff > threshold + 1.0:
            return 'ok', 'Kein Kondensationsrisiko'
        if diff > threshold:
            return 'warning', 'Erhöhte Aufmerksamkeit'
        if diff > 0:
            return 'critical', 'Hohes Kondensationsrisiko!'
        return 'critical', 'KONDENSATION MÖGLICH!'
