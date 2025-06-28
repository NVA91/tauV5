"""Taupunkt controller entry point."""

import json
import time
import gc
import uasyncio as asyncio
from machine import Pin, I2C, SPI, WDT

from lib.core.calc import TaupunktCalculator, SensorCalibrator
from lib.core.trend import TrendAnalyzer
from lib.core.logger import EnhancedDataLogger
from lib.ui.display import DisplayController
from lib.ui.alarm import AlarmController
from lib.sensors.sht41 import AsyncSensorSHT41
from lib.sensors.aht20 import AsyncSensorAHT20

class EnhancedTaupunktController:
    def __init__(self):
        self.config = self._load_config()
        self.params = self.config['params']
        self.pins = self.config['pins']
        self._init_hardware()
        self.calibrator = SensorCalibrator()
        self.trend_analyzer = TrendAnalyzer(self.params['mess_intervall_sek'])
        self.logger = EnhancedDataLogger(self.pins, self.params)
        self.is_display_on = True
        self.last_user_activity = time.time()
        self.system_status = 'initializing'

    def _load_config(self):
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except Exception:
            return self._get_default_config()

    def _get_default_config(self):
        return {
            'pins': {
                'i2c_bus_id': 0, 'i2c_sda': 0, 'i2c_scl': 1,
                'spi_bus_id': 1, 'spi_sck': 10, 'spi_mosi': 11,
                'lcd_cs': 9, 'lcd_dc': 8, 'lcd_rst': 12, 'lcd_bl': 13,
                'led_rot': 15, 'led_gelb': 14, 'led_gruen': 16,
                'wakeup_button': 22, 'buzzer': 28,
                'sd_spi_id': 0, 'sd_sck': 6, 'sd_mosi': 7, 'sd_miso': 4, 'sd_cs': 5
            },
            'params': {
                'mess_intervall_sek': 900, 'log_interval_sek': 3600,
                'log_file_prefix': 'taupunkt_log', 'max_log_file_mb': 5,
                'max_log_files': 30, 'taupunkt_grenze_c': 2.0,
                'alarm_taupunkt_abstand_c': 1.5, 'watchdog_timeout_ms': 8000,
                'display_timeout_sek': 60
            }
        }

    def _init_hardware(self):
        self.wdt = WDT(timeout=self.params['watchdog_timeout_ms'])
        self.i2c = I2C(self.pins['i2c_bus_id'],
                       scl=Pin(self.pins['i2c_scl']),
                       sda=Pin(self.pins['i2c_sda']))
        self.spi = SPI(self.pins['spi_bus_id'],
                       baudrate=30_000_000,
                       sck=Pin(self.pins['spi_sck']),
                       mosi=Pin(self.pins['spi_mosi']))
        self.leds = {
            'rot': Pin(self.pins['led_rot'], Pin.OUT),
            'gelb': Pin(self.pins['led_gelb'], Pin.OUT),
            'gruen': Pin(self.pins['led_gruen'], Pin.OUT)
        }
        self.display = DisplayController(self.spi, self.pins, 172, 320)
        self.alarm = AlarmController(self.pins.get('buzzer'))
        wake = self.pins.get('wakeup_button')
        if wake:
            self.wakeup_button = Pin(wake, Pin.IN, Pin.PULL_UP)
            self.wakeup_button.irq(trigger=Pin.IRQ_FALLING, handler=self._handle_wakeup)
        self._init_sensors()

    def _init_sensors(self):
        self.sensors = {}
        devices = self.i2c.scan()
        if 0x44 in devices:
            self.sensors['innen'] = AsyncSensorSHT41(self.i2c, 0x44)
        if 0x38 in devices:
            self.sensors['aussen'] = AsyncSensorAHT20(self.i2c, 0x38)

    def _handle_wakeup(self, pin):
        self.last_user_activity = time.time()
        if not self.is_display_on:
            self.display.set_backlight(True)
            self.is_display_on = True
        if self.alarm.is_alarm_active:
            self.alarm.stop_alarm()

    async def control_loop(self):
        self.system_status = 'running'
        while True:
            try:
                self.wdt.feed()
                sensor_data = await self._read_all_sensors()
                processed = self._process_sensor_data(sensor_data)
                trends = self._update_trends(processed)
                risk = self._evaluate_risks(processed)
                data = {**processed, **risk}
                self._update_led_status(risk['risk_level'])
                if self.is_display_on:
                    self.display.show_main_screen(data, trends)
                await self._check_alarms(data)
                self._check_display_timeout()
                await self.logger.log_data_async(data, trends)
                if time.time() % 300 < 1:
                    gc.collect()
                await asyncio.sleep(self.params['mess_intervall_sek'])
            except Exception as e:
                print('Fehler in Hauptschleife:', e)
                self.system_status = 'error'
                await asyncio.sleep(10)

    async def _read_all_sensors(self):
        result = {}
        for name, sensor in self.sensors.items():
            try:
                temp, hum = await sensor.read_async()
                if temp is not None and hum is not None:
                    t_cal, h_cal = self.calibrator.apply_calibration(name, temp, hum)
                    result[name] = {'temp': t_cal, 'humidity': h_cal, 'valid': True}
                else:
                    result[name] = {'temp': None, 'humidity': None, 'valid': False}
            except Exception as e:
                print('Sensor', name, 'Lesefehler:', e)
                result[name] = {'temp': None, 'humidity': None, 'valid': False}
        return result

    def _process_sensor_data(self, sensor_data):
        processed = {}
        calc = TaupunktCalculator()
        for loc in ['innen', 'aussen']:
            key_t = f't_{loc[:2]}'
            key_h = f'h_{loc[:2]}'
            key_dp = f'dp_{loc[:2]}'
            if loc in sensor_data and sensor_data[loc]['valid']:
                t = sensor_data[loc]['temp']
                h = sensor_data[loc]['humidity']
                dp = calc.calculate_dew_point(t, h)
                processed[key_t] = t
                processed[key_h] = h
                processed[key_dp] = dp
            else:
                processed[key_t] = None
                processed[key_h] = None
                processed[key_dp] = None
        return processed

    def _update_trends(self, data):
        trends = {}
        if data.get('t_in') is not None:
            self.trend_analyzer.add_measurement('innen', data['t_in'])
            trends['in'] = self.trend_analyzer.get_trend_data('innen', data['t_in'])
        if data.get('t_out') is not None:
            self.trend_analyzer.add_measurement('aussen', data['t_out'])
            trends['out'] = self.trend_analyzer.get_trend_data('aussen', data['t_out'])
        return trends

    def _evaluate_risks(self, data):
        calc = TaupunktCalculator()
        dp_in = data.get('dp_in')
        t_out = data.get('t_out')
        if dp_in is not None and t_out is not None:
            level, msg = calc.evaluate_condensation_risk(dp_in, t_out, self.params['taupunkt_grenze_c'])
        else:
            level, msg = 'unknown', 'Sensordaten unvollständig'
        return {'risk_level': level, 'risk_message': msg, 'status': level}

    def _update_led_status(self, risk_level):
        for led in self.leds.values():
            led.off()
        led_map = {'ok': 'gruen', 'warning': 'gelb', 'critical': 'rot', 'unknown': 'gelb'}
        name = led_map.get(risk_level, 'gelb')
        if name in self.leds:
            self.leds[name].on()

    async def _check_alarms(self, data):
        level = data.get('risk_level', 'unknown')
        if level == 'critical' and not self.alarm.is_alarm_active:
            self.alarm.trigger_alarm('condensation', data.get('risk_message', ''))
            if self.display:
                self.display.show_alarm_screen('KONDENSATION', data.get('risk_message', ''))
        if data.get('t_in') is None or data.get('t_out') is None:
            if not self.alarm.is_alarm_active or self.alarm.alarm_type != 'sensor_failure':
                self.alarm.trigger_alarm('sensor_failure', 'Sensor-Ausfall erkannt')

    def _check_display_timeout(self):
        if (self.is_display_on and time.time() - self.last_user_activity > self.params['display_timeout_sek']):
            self.display.set_backlight(False)
            self.is_display_on = False

    async def run_system(self):
        if self.display:
            self.display.clear_screen()
            self.display.show_main_screen({'status': 'initializing'}, {})
        tasks = [
            asyncio.create_task(self.control_loop()),
            asyncio.create_task(self.alarm.alarm_pattern_task())
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            self.alarm.stop_alarm()
            if self.display:
                self.display.set_backlight(False)

async def main():
    controller = EnhancedTaupunktController()
    await controller.run_system()

if __name__ == '__main__':
    asyncio.run(main())
