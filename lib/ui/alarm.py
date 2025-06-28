import time
try:
    from machine import Pin, PWM
except ImportError:
    Pin = None
    PWM = None
import uasyncio as asyncio

class AlarmController:
    """Handle buzzer alarms."""

    def __init__(self, buzzer_pin=None):
        self.is_alarm_active = False
        self.alarm_type = None
        self.alarm_start_time = 0
        if buzzer_pin is not None and PWM:
            self.buzzer = PWM(Pin(buzzer_pin))
            self.buzzer.duty_u16(0)
        else:
            self.buzzer = None

    def trigger_alarm(self, alarm_type, message=''):
        if self.is_alarm_active and self.alarm_type == alarm_type:
            return
        self.is_alarm_active = True
        self.alarm_type = alarm_type
        self.alarm_start_time = time.time()
        print('ALARM:', alarm_type, message)
        if alarm_type == 'condensation':
            self._play_condensation_alarm()
        elif alarm_type == 'sensor_failure':
            self._play_sensor_failure_alarm()
        else:
            self._play_generic_alarm()

    def stop_alarm(self):
        self.is_alarm_active = False
        self.alarm_type = None
        if self.buzzer:
            self.buzzer.duty_u16(0)
        print('Alarm gestoppt')

    def _play_condensation_alarm(self):
        if self.buzzer:
            self.buzzer.freq(1500)
            self.buzzer.duty_u16(32768)

    def _play_sensor_failure_alarm(self):
        if self.buzzer:
            self.buzzer.freq(2500)
            self.buzzer.duty_u16(16384)

    def _play_generic_alarm(self):
        if self.buzzer:
            self.buzzer.freq(2000)
            self.buzzer.duty_u16(32768)

    async def alarm_pattern_task(self):
        while True:
            if self.is_alarm_active and self.alarm_type == 'sensor_failure':
                if self.buzzer:
                    self.buzzer.duty_u16(32768)
                await asyncio.sleep_ms(500)
                if self.buzzer:
                    self.buzzer.duty_u16(0)
                await asyncio.sleep_ms(500)
            else:
                await asyncio.sleep_ms(100)
