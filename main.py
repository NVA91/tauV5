"""
ERWEITERTE TAUFPUNKT-STEUERUNG FÜR RASPBERRY PI PICO 2
-----------------------------------------------------
Optimierte Version mit async/await, Log-Rotation, Kalibrierung,
Trends, Named Tuples und umfassender Dokumentation.
"""


# System-Imports
import time
import math
import gc
import json
import os
import uasyncio as asyncio
from machine import Pin, I2C, SPI, WDT, PWM
from micropython import const
from collections import namedtuple, deque


# Treiber-Imports
try:
    import sdcardio
    import storage
    import st7789
    import vga1_16x16 as font_medium
except ImportError as e:
    print(f"FEHLER: Treiber oder Font nicht im /lib Ordner gefunden: {e}")
    st7789 = None


# =============================================================================
# 1. DATENSTRUKTUREN
# =============================================================================


SensorData = namedtuple('SensorData', ['temperature', 'humidity', 'dew_point', 'timestamp'])
CalibrationData = namedtuple('CalibrationData', ['temp_offset', 'humidity_offset'])
TrendData = namedtuple('TrendData', ['current', 'avg_5min', 'avg_15min', 'trend'])


class RingBuffer:
    """Ringpuffer für gleitende Mittelwerte"""
    def __init__(self, size: int):
        self.size = size
        self.data = deque((), size)
    
    def add(self, value: float) -> None:
        """Fügt einen Wert zum Puffer hinzu"""
        self.data.append(value)
    
    def average(self) -> float:
        """Berechnet den Durchschnitt aller Werte"""
        return sum(self.data) / len(self.data) if self.data else 0.0
    
    def is_full(self) -> bool:
        """Prüft ob der Puffer voll ist"""
        return len(self.data) == self.size


# =============================================================================
# 2. ERWEITERTE CONTROLLER-KLASSEN
# =============================================================================


class EnhancedDataLogger:
    """Erweiterte Logging-Klasse mit Rotation und Kompression"""
    
    def __init__(self, pins: dict, params: dict):
        """
        Initialisiert den Enhanced Data Logger
        
        Args:
            pins: Pin-Konfiguration für SD-Karte
            params: Parameter für Logging-Verhalten
        """
        self.params = params
        self.last_log_time = 0
        self.is_mounted = False
        self.current_file_size = 0
        self.max_file_size = params.get('max_log_file_mb', 5) * 1024 * 1024  # MB zu Bytes
        self.max_files = params.get('max_log_files', 30)
        
        self._init_sd_card(pins)
    
    def _init_sd_card(self, pins: dict) -> None:
        """Initialisiert die SD-Karte"""
        try:
            spi = SPI(pins['sd_spi_id'], 
                     sck=Pin(pins['sd_sck']), 
                     mosi=Pin(pins['sd_mosi']), 
                     miso=Pin(pins['sd_miso']))
            sd = sdcardio.SDCard(spi, Pin(pins['sd_cs'], Pin.OUT))
            vfs = storage.VfsFat(sd)
            storage.mount(vfs, '/sd')
            self.is_mounted = True
            print("SD-Karte erfolgreich gemountet")
            self._cleanup_old_files()
            self._write_header()
        except Exception as e:
            print(f"SD-Karte Initialisierungsfehler: {e}")
    
    def _cleanup_old_files(self) -> None:
        """Löscht alte Log-Dateien nach max_files Prinzip"""
        if not self.is_mounted:
            return
        
        try:
            files = [f for f in os.listdir('/sd') if f.startswith(self.params['log_file_prefix'])]
            files.sort(reverse=True)  # Neueste zuerst
            
            for old_file in files[self.max_files:]:
                try:
                    os.remove(f'/sd/{old_file}')
                    print(f"Alte Log-Datei gelöscht: {old_file}")
                except:
                    pass
        except Exception as e:
            print(f"Fehler beim Aufräumen alter Dateien: {e}")
    
    def _rotate_log_if_needed(self) -> None:
        """Rotiert Log-Datei wenn sie zu groß wird"""
        if not self.is_mounted:
            return
        
        current_path = self._get_current_log_file_path()
        try:
            stat = os.stat(current_path)
            if stat[6] > self.max_file_size:  # Dateigröße
                # Datei mit Zeitstempel umbenennen
                t = time.localtime()
                new_name = f"/sd/{self.params['log_file_prefix']}_{t[0]:04d}-{t[1]:02d}-{t[2]:02d}_{t[3]:02d}{t[4]:02d}.csv"
                os.rename(current_path, new_name)
                print(f"Log-Datei rotiert: {new_name}")
                self._write_header()
        except OSError:
            pass  # Datei existiert noch nicht
    
    def _write_header(self) -> None:
        """Schreibt CSV-Header wenn Datei neu ist"""
        if not self.is_mounted:
            return
        
        file_path = self._get_current_log_file_path()
        try:
            with open(file_path, 'a+') as f:
                if f.tell() == 0:
                    header = ("timestamp,temp_in,hum_in,dp_in,temp_out,hum_out,dp_out,"
                             "temp_in_avg5,temp_out_avg5,status,trend_in,trend_out\n")
                    f.write(header)
        except Exception as e:
            print(f"Header-Schreibfehler: {e}")
    
    def _get_current_log_file_path(self) -> str:
        """Gibt den aktuellen Log-Dateipfad zurück"""
        return f"/sd/{self.params['log_file_prefix']}_current.csv"
    
    async def log_data_async(self, data: dict, trends: dict) -> None:
        """
        Asynchrones Logging von Daten
        
        Args:
            data: Sensor-Daten Dictionary
            trends: Trend-Daten Dictionary
        """
        if not self.is_mounted:
            return
        
        current_time = time.time()
        if current_time - self.last_log_time < self.params['log_interval_sek']:
            return
        
        self._rotate_log_if_needed()
        
        file_path = self._get_current_log_file_path()
        log_line = (f"{current_time},{data['t_in']:.2f},{data['h_in']:.2f},"
                   f"{data['dp_in']:.2f},{data['t_out']:.2f},{data['h_out']:.2f},"
                   f"{data['dp_out']:.2f},{trends['in'].avg_5min:.2f},"
                   f"{trends['out'].avg_5min:.2f},{data['status']},"
                   f"{trends['in'].trend},{trends['out'].trend}\n")
        
        try:
            with open(file_path, 'a') as f:
                f.write(log_line)
            self.last_log_time = current_time
            print(f"Daten geloggt: {current_time}")
        except Exception as e:
            print(f"Logging-Fehler: {e}")




class SensorCalibrator:
    """Verwaltet Sensor-Kalibrierungen und -Korrekturen"""
    
    def __init__(self, config_path: str = '/sd/calibration.json'):
        """
        Initialisiert den Sensor-Kalibrator
        
        Args:
            config_path: Pfad zur Kalibrierungs-Konfigurationsdatei
        """
        self.config_path = config_path
        self.calibrations = {}
        self._load_calibrations()
    
    def _load_calibrations(self) -> None:
        """Lädt Kalibrierungsdaten aus Datei"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                for sensor, cal_data in data.items():
                    self.calibrations[sensor] = CalibrationData(
                        temp_offset=cal_data.get('temp_offset', 0.0),
                        humidity_offset=cal_data.get('humidity_offset', 0.0)
                    )
            print("Kalibrierungsdaten geladen")
        except (OSError, ValueError):
            print("Keine Kalibrierungsdaten gefunden, verwende Defaults")
            self.calibrations = {
                'innen': CalibrationData(0.0, 0.0),
                'aussen': CalibrationData(0.0, 0.0)
            }
    
    def save_calibrations(self) -> None:
        """Speichert aktuelle Kalibrierungsdaten"""
        data = {}
        for sensor, cal in self.calibrations.items():
            data[sensor] = {
                'temp_offset': cal.temp_offset,
                'humidity_offset': cal.humidity_offset
            }
        
        try:
            with open(self.config_path, 'w') as f:
                json.dump(data, f)
            print("Kalibrierungsdaten gespeichert")
        except Exception as e:
            print(f"Fehler beim Speichern der Kalibrierung: {e}")
    
    def apply_calibration(self, sensor_name: str, temp: float, humidity: float) -> tuple:
        """
        Wendet Kalibrierung auf Sensor-Werte an
        
        Args:
            sensor_name: Name des Sensors
            temp: Rohe Temperatur
            humidity: Rohe Luftfeuchtigkeit
            
        Returns:
            Tuple aus kalibrierter Temperatur und Luftfeuchtigkeit
        """
        cal = self.calibrations.get(sensor_name, CalibrationData(0.0, 0.0))
        return (
            temp + cal.temp_offset,
            max(0, min(100, humidity + cal.humidity_offset))
        )
    
    def set_calibration(self, sensor_name: str, temp_offset: float, humidity_offset: float) -> None:
        """
        Setzt neue Kalibrierungswerte für einen Sensor
        
        Args:
            sensor_name: Name des Sensors
            temp_offset: Temperatur-Offset in °C
            humidity_offset: Luftfeuchtigkeits-Offset in %
        """
        self.calibrations[sensor_name] = CalibrationData(temp_offset, humidity_offset)
        self.save_calibrations()




class TrendAnalyzer:
    """Analysiert Trends in Sensor-Daten"""
    
    def __init__(self, measurement_interval: int = 900):
        """
        Initialisiert den Trend-Analyzer
        
        Args:
            measurement_interval: Messintervall in Sekunden
        """
        self.measurement_interval = measurement_interval
        # Ringpuffer für verschiedene Zeiträume
        self.buffers = {
            'innen': {
                '5min': RingBuffer(max(1, 300 // measurement_interval)),
                '15min': RingBuffer(max(1, 900 // measurement_interval)),
                '1h': RingBuffer(max(1, 3600 // measurement_interval))
            },
            'aussen': {
                '5min': RingBuffer(max(1, 300 // measurement_interval)),
                '15min': RingBuffer(max(1, 900 // measurement_interval)),
                '1h': RingBuffer(max(1, 3600 // measurement_interval))
            }
        }
    
    def add_measurement(self, sensor_name: str, value: float) -> None:
        """
        Fügt eine neue Messung hinzu
        
        Args:
            sensor_name: Name des Sensors
            value: Gemessener Wert
        """
        if sensor_name in self.buffers:
            for buffer in self.buffers[sensor_name].values():
                buffer.add(value)
    
    def get_trend_data(self, sensor_name: str, current_value: float) -> TrendData:
        """
        Berechnet Trend-Daten für einen Sensor
        
        Args:
            sensor_name: Name des Sensors
            current_value: Aktueller Messwert
            
        Returns:
            TrendData mit aktuellen Werten und Trends
        """
        if sensor_name not in self.buffers:
            return TrendData(current_value, current_value, current_value, "stable")
        
        buffers = self.buffers[sensor_name]
        avg_5min = buffers['5min'].average()
        avg_15min = buffers['15min'].average()
        
        # Trend bestimmen
        if not buffers['5min'].is_full():
            trend = "initializing"
        elif current_value > avg_5min + 0.5:
            trend = "rising"
        elif current_value < avg_5min - 0.5:
            trend = "falling"
        else:
            trend = "stable"
        
        return TrendData(current_value, avg_5min, avg_15min, trend)




# =============================================================================
# 3. ERWEITERTE SENSOR-KLASSEN MIT ASYNC
# =============================================================================


class AsyncSensorSHT41:
    """Asynchroner SHT41 Sensor-Treiber"""
    
    def __init__(self, i2c: I2C, addr: int = 0x44):
        """
        Initialisiert den SHT41 Sensor
        
        Args:
            i2c: I2C-Bus Instanz
            addr: I2C-Adresse des Sensors
        """
        self.i2c = i2c
        self.addr = addr
        self.last_read_time = 0
        self.min_read_interval = 1.0  # Mindestens 1 Sekunde zwischen Messungen
    
    async def read_async(self) -> tuple:
        """
        Liest Temperatur und Luftfeuchtigkeit asynchron
        
        Returns:
            Tuple (Temperatur, Luftfeuchtigkeit) oder (None, None) bei Fehler
        """
        current_time = time.time()
        if current_time - self.last_read_time < self.min_read_interval:
            await asyncio.sleep_ms(100)
        
        try:
            # Messung starten
            self.i2c.writeto(self.addr, b'\xFD')
            await asyncio.sleep_ms(10)  # Warten auf Messung
            
            # Daten lesen
            data = self.i2c.readfrom(self.addr, 6)
            
            # Temperatur berechnen
            temp_raw = (data[0] << 8) | data[1]
            temp = -45 + 175 * temp_raw / 65535.0
            
            # Luftfeuchtigkeit berechnen
            hum_raw = (data[3] << 8) | data[4]
            humidity = -6 + 125 * hum_raw / 65535.0
            humidity = max(0, min(100, humidity))
            
            self.last_read_time = current_time
            return temp, humidity
            
        except Exception as e:
            print(f"SHT41 Lesefehler: {e}")
            return None, None




class AsyncSensorAHT20:
    """Asynchroner AHT20 Sensor-Treiber"""
    
    def __init__(self, i2c: I2C, addr: int = 0x38):
        """
        Initialisiert den AHT20 Sensor
        
        Args:
            i2c: I2C-Bus Instanz
            addr: I2C-Adresse des Sensors
        """
        self.i2c = i2c
        self.addr = addr
        self.last_read_time = 0
        self.min_read_interval = 1.0
        
        # Sensor initialisieren
        try:
            self.i2c.writeto(self.addr, b'\xBE\x08\x00')
        except:
            pass
    
    async def read_async(self) -> tuple:
        """
        Liest Temperatur und Luftfeuchtigkeit asynchron
        
        Returns:
            Tuple (Temperatur, Luftfeuchtigkeit) oder (None, None) bei Fehler
        """
        current_time = time.time()
        if current_time - self.last_read_time < self.min_read_interval:
            await asyncio.sleep_ms(100)
        
        try:
            # Messung triggern
            self.i2c.writeto(self.addr, b'\xAC\x33\x00')
            await asyncio.sleep_ms(80)  # Warten auf Messung
            
            # Daten lesen
            data = self.i2c.readfrom(self.addr, 7)
            
            # Luftfeuchtigkeit berechnen
            hum_raw = (((data[1] << 16) | (data[2] << 8) | data[3]) >> 4)
            humidity = hum_raw * 100 / 1048576
            
            # Temperatur berechnen
            temp_raw = (((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5])
            temp = temp_raw * 200 / 1048576 - 50
            
            self.last_read_time = current_time
            return temp, humidity
            
        except Exception as e:
            print(f"AHT20 Lesefehler: {e}")
            return None, None




# =============================================================================
# 4. HAUPTKLASSE MIT ASYNC UNTERSTÜTZUNG
# =============================================================================


class EnhancedTaupunktController:
    """Erweiterte Taupunkt-Steuerung mit async/await und allen Optimierungen"""
    
    def __init__(self):
        """Initialisiert den erweiterten Taupunkt-Controller"""
        self.config = self._load_config()
        self.params = self.config['params']
        self.pins = self.config['pins']
        
        # Hardware initialisieren
        self._init_hardware()
        
        # Erweiterte Komponenten
        self.calibrator = SensorCalibrator()
        self.trend_analyzer = TrendAnalyzer(self.params['mess_intervall_sek'])
        self.enhanced_logger = EnhancedDataLogger(self.pins, self.params)
        
        # Status-Tracking
        self.is_display_on = True
        self.last_user_activity = time.time()
        self.system_status = "initializing"
        
        print("Enhanced Taupunkt Controller initialisiert")
    
    def _load_config(self) -> dict:
        """
        Lädt Konfiguration aus JSON-Datei
        
        Returns:
            Konfiguration als Dictionary
        """
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            print(f"Konfigurationsfehler: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> dict:
        """Gibt eine Standard-Konfiguration zurück"""
        return {
            "pins": {
                "i2c_bus_id": 0, "i2c_sda": 0, "i2c_scl": 1,
                "spi_bus_id": 1, "spi_sck": 10, "spi_mosi": 11,
                "lcd_cs": 9, "lcd_dc": 8, "lcd_rst": 12, "lcd_bl": 13,
                "led_rot": 15, "led_gelb": 14, "led_gruen": 16,  # Pin-Konflikt behoben
                "wakeup_button": 22, "buzzer": 28,
                "sd_spi_id": 0, "sd_sck": 6, "sd_mosi": 7, "sd_miso": 4, "sd_cs": 5
            },
            "params": {
                "mess_intervall_sek": 900, "log_interval_sek": 3600,
                "log_file_prefix": "taupunkt_log", "max_log_file_mb": 5,
                "max_log_files": 30, "taupunkt_grenze_c": 2.0,
                "alarm_taupunkt_abstand_c": 1.5, "watchdog_timeout_ms": 8000,
                "display_timeout_sek": 60
            }
        }
    
    def _init_hardware(self) -> None:
        """Initialisiert alle Hardware-Komponenten"""
        # Watchdog
        self.wdt = WDT(timeout=self.params['watchdog_timeout_ms'])
        
        # I2C und SPI
        self.i2c = I2C(self.pins['i2c_bus_id'], 
                      scl=Pin(self.pins['i2c_scl']), 
                      sda=Pin(self.pins['i2c_sda']))
        self.spi = SPI(self.pins['spi_bus_id'], 
                      baudrate=30_000_000,
                      sck=Pin(self.pins['spi_sck']), 
                      mosi=Pin(self.pins['spi_mosi']))
        
        # LEDs
        self.leds = {
            'rot': Pin(self.pins['led_rot'], Pin.OUT),
            'gelb': Pin(self.pins['led_gelb'], Pin.OUT),
            'gruen': Pin(self.pins['led_gruen'], Pin.OUT)
        }
        
        # Display, Alarm, Wake-up Button
        self.display = DisplayController(self.spi, self.pins, 172, 320)
        self.alarm = AlarmController(self.pins.get('buzzer'))
        
        wakeup_pin = self.pins.get('wakeup_button')
        if wakeup_pin:
            self.wakeup_button = Pin(wakeup_pin, Pin.IN, Pin.PULL_UP)
            self.wakeup_button.irq(trigger=Pin.IRQ_FALLING, handler=self._handle_wakeup)
        
        # Sensoren initialisieren
        self._init_sensors()
    
    def _init_sensors(self) -> None:
        """Initialisiert die Sensoren"""
        i2c_devices = self.i2c.scan()
        self.sensors = {}
        
        sensor_map = {
            'innen': (AsyncSensorSHT41, 0x44),
            'aussen': (AsyncSensorAHT20, 0x38)
        }
        
        for name, (SensorClass, addr) in sensor_map.items():
            if addr in i2c_devices:
                self.sensors[name] = SensorClass(self.i2c, addr)
                print(f"Sensor '{name}' gefunden und initialisiert")
            else:
                print(f"WARNUNG: Sensor '{name}' nicht gefunden (Adresse: 0x{addr:02X})")
    
    def _handle_wakeup(self, pin) -> None:
        """Interrupt-Handler für Wake-up Button"""
        self.last_user_activity = time.time()
        if not self.is_display_on:
            self.display.set_backlight(True)
            sel




# =============================================================================
# FEHLENDE KRITISCHE KOMPONENTEN - ERGÄNZUNG ZU IHREM PROGRAMM
# =============================================================================


import math
import time
import uasyncio as asyncio
from machine import Pin, PWM
from micropython import const


# =============================================================================
# 1. DISPLAY CONTROLLER
# =============================================================================


class DisplayController:
    """Erweiterte Display-Steuerung für ST7789 TFT"""
    
    def __init__(self, spi, pins: dict, width: int, height: int):
        """
        Initialisiert den Display Controller
        
        Args:
            spi: SPI-Bus Instanz
            pins: Pin-Konfiguration
            width: Display-Breite
            height: Display-Höhe
        """
        self.width = width
        self.height = height
        self.is_on = True
        
        try:
            if st7789:
                self.tft = st7789.ST7789(
                    spi, 
                    width, height,
                    reset=Pin(pins['lcd_rst'], Pin.OUT),
                    cs=Pin(pins['lcd_cs'], Pin.OUT),
                    dc=Pin(pins['lcd_dc'], Pin.OUT),
                    backlight=Pin(pins['lcd_bl'], Pin.OUT),
                    rotation=1
                )
                self.font = font_medium
                self.tft.init()
                self.set_backlight(True)
                print("Display initialisiert")
            else:
                print("WARNUNG: st7789 Treiber nicht verfügbar")
                self.tft = None
        except Exception as e:
            print(f"Display-Initialisierungsfehler: {e}")
            self.tft = None
    
    def set_backlight(self, state: bool) -> None:
        """
        Steuert die Hintergrundbeleuchtung
        
        Args:
            state: True für an, False für aus
        """
        if self.tft:
            try:
                self.tft.backlight.value(1 if state else 0)
                self.is_on = state
            except:
                pass
    
    def clear_screen(self, color: int = 0x0000) -> None:
        """Löscht den Bildschirm mit angegebener Farbe"""
        if self.tft:
            self.tft.fill(color)
    
    def show_main_screen(self, data: dict, trends: dict) -> None:
        """
        Zeigt den Hauptbildschirm mit Sensor-Daten
        
        Args:
            data: Dictionary mit Sensor-Daten
            trends: Dictionary mit Trend-Daten
        """
        if not self.tft:
            return
        
        try:
            # Hintergrund löschen
            self.clear_screen(0x0000)  # Schwarz
            
            # Titel
            self.tft.text(self.font, "TAUPUNKT-KONTROLLE", 10, 10, 0xFFFF, 0x0000)
            
            # Innen-Werte
            y_pos = 40
            self.tft.text(self.font, "INNEN:", 10, y_pos, 0x07E0, 0x0000)  # Grün
            self.tft.text(self.font, f"Temp: {data.get('t_in', 0):.1f}°C", 10, y_pos + 20, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Feuchte: {data.get('h_in', 0):.1f}%", 10, y_pos + 40, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Taupunkt: {data.get('dp_in', 0):.1f}°C", 10, y_pos + 60, 0xFFE0, 0x0000)  # Gelb
            
            # Außen-Werte
            y_pos = 140
            self.tft.text(self.font, "AUSSEN:", 10, y_pos, 0x001F, 0x0000)  # Blau
            self.tft.text(self.font, f"Temp: {data.get('t_out', 0):.1f}°C", 10, y_pos + 20, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Feuchte: {data.get('h_out', 0):.1f}%", 10, y_pos + 40, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Taupunkt: {data.get('dp_out', 0):.1f}°C", 10, y_pos + 60, 0xFFE0, 0x0000)
            
            # Status und Risiko
            y_pos = 240
            status = data.get('status', 'unknown')
            risk_level = data.get('risk_level', 'unknown')
            
            status_color = self._get_status_color(status)
            self.tft.text(self.font, f"Status: {status}", 10, y_pos, status_color, 0x0000)
            self.tft.text(self.font, f"Risiko: {risk_level}", 10, y_pos + 20, status_color, 0x0000)
            
            # Trends anzeigen
            if trends:
                trend_in = trends.get('in', {}).get('trend', 'stable')
                trend_out = trends.get('out', {}).get('trend', 'stable')
                self.tft.text(self.font, f"Trend I/A: {trend_in}/{trend_out}", 10, y_pos + 40, 0xF81F, 0x0000)  # Magenta
            
        except Exception as e:
            print(f"Display-Update-Fehler: {e}")
    
    def show_alarm_screen(self, alarm_type: str, message: str) -> None:
        """
        Zeigt Alarm-Bildschirm
        
        Args:
            alarm_type: Art des Alarms
            message: Alarm-Nachricht
        """
        if not self.tft:
            return
        
        try:
            self.clear_screen(0xF800)  # Rot
            self.tft.text(self.font, "!!! ALARM !!!", 10, 50, 0xFFFF, 0xF800)
            self.tft.text(self.font, alarm_type.upper(), 10, 80, 0xFFFF, 0xF800)
            self.tft.text(self.font, message, 10, 110, 0xFFFF, 0xF800)
            self.tft.text(self.font, "Taste drücken zum", 10, 180, 0xFFFF, 0xF800)
            self.tft.text(self.font, "Bestätigen", 10, 200, 0xFFFF, 0xF800)
        except Exception as e:
            print(f"Alarm-Display-Fehler: {e}")
    
    def _get_status_color(self, status: str) -> int:
        """Gibt Farbe basierend auf Status zurück"""
        colors = {
            'ok': 0x07E0,        # Grün
            'warning': 0xFFE0,   # Gelb
            'critical': 0xF800,  # Rot
            'unknown': 0xFFFF    # Weiß
        }
        return colors.get(status, 0xFFFF)




# =============================================================================
# 2. ALARM CONTROLLER
# =============================================================================


class AlarmController:
    """Alarm-System für akustische und visuelle Warnungen"""
    
    def __init__(self, buzzer_pin: int = None):
        """
        Initialisiert den Alarm Controller
        
        Args:
            buzzer_pin: Pin für Buzzer (optional)
        """
        self.buzzer = None
        self.is_alarm_active = False
        self.alarm_type = None
        self.alarm_start_time = 0
        
        if buzzer_pin:
            try:
                self.buzzer = PWM(Pin(buzzer_pin))
                self.buzzer.freq(2000)  # 2kHz Standard-Frequenz
                self.buzzer.duty_u16(0)  # Aus
                print("Buzzer initialisiert")
            except Exception as e:
                print(f"Buzzer-Initialisierungsfehler: {e}")
    
    def trigger_alarm(self, alarm_type: str, message: str = "") -> None:
        """
        Löst einen Alarm aus
        
        Args:
            alarm_type: Art des Alarms ('condensation', 'sensor_failure', etc.)
            message: Zusätzliche Alarm-Nachricht
        """
        if self.is_alarm_active and self.alarm_type == alarm_type:
            return  # Bereits aktiver Alarm desselben Typs
        
        self.is_alarm_active = True
        self.alarm_type = alarm_type
        self.alarm_start_time = time.time()
        
        print(f"ALARM: {alarm_type} - {message}")
        
        # Alarm-spezifische Töne
        if alarm_type == 'condensation':
            self._play_condensation_alarm()
        elif alarm_type == 'sensor_failure':
            self._play_sensor_failure_alarm()
        else:
            self._play_generic_alarm()
    
    def stop_alarm(self) -> None:
        """Stoppt den aktiven Alarm"""
        self.is_alarm_active = False
        self.alarm_type = None
        if self.buzzer:
            self.buzzer.duty_u16(0)
        print("Alarm gestoppt")
    
    def _play_condensation_alarm(self) -> None:
        """Spielt Kondensations-Alarm (kontinuierlicher Ton)"""
        if self.buzzer:
            self.buzzer.freq(1500)
            self.buzzer.duty_u16(32768)  # 50% Duty-Cycle
    
    def _play_sensor_failure_alarm(self) -> None:
        """Spielt Sensor-Ausfall-Alarm (intermittierend)"""
        if self.buzzer:
            self.buzzer.freq(2500)
            self.buzzer.duty_u16(16384)  # 25% Duty-Cycle
    
    def _play_generic_alarm(self) -> None:
        """Spielt generischen Alarm"""
        if self.buzzer:
            self.buzzer.freq(2000)
            self.buzzer.duty_u16(32768)
    
    async def alarm_pattern_task(self) -> None:
        """Async Task für Alarm-Muster (intermittierend)"""
        while True:
            if self.is_alarm_active and self.alarm_type == 'sensor_failure':
                if self.buzzer:
                    self.buzzer.duty_u16(32768)  # An
                await asyncio.sleep_ms(500)
                if self.buzzer:
                    self.buzzer.duty_u16(0)      # Aus
                await asyncio.sleep_ms(500)
            else:
                await asyncio.sleep_ms(100)




# =============================================================================
# 3. TAUPUNKT-BERECHNUNGEN UND KERN-LOGIK
# =============================================================================


class TaupunktCalculator:
    """Taupunkt-Berechnungen und Kondensations-Risiko-Bewertung"""
    
    @staticmethod
    def calculate_dew_point(temp: float, humidity: float) -> float:
        """
        Berechnet Taupunkt mit Magnus-Formel
        
        Args:
            temp: Temperatur in °C
            humidity: Relative Luftfeuchtigkeit in %
            
        Returns:
            Taupunkt in °C
        """
        if humidity <= 0 or humidity > 100:
            return float('nan')
        
        try:
            # Magnus-Formel Konstanten
            a = 17.27
            b = 237.7
            
            # Hilfsvariable
            alpha = ((a * temp) / (b + temp)) + math.log(humidity / 100.0)
            
            # Taupunkt berechnen
            dew_point = (b * alpha) / (a - alpha)
            return round(dew_point, 2)
            
        except (ValueError, ZeroDivisionError):
            return float('nan')
    
    @staticmethod
    def evaluate_condensation_risk(indoor_dp: float, outdoor_temp: float, 
                                 threshold: float = 2.0) -> tuple:
        """
        Bewertet Kondensationsrisiko
        
        Args:
            indoor_dp: Innen-Taupunkt in °C
            outdoor_temp: Außentemperatur in °C
            threshold: Sicherheitsabstand in °C
            
        Returns:
            Tuple (risk_level, risk_message)
        """
        if math.isnan(indoor_dp) or math.isnan(outdoor_temp):
            return 'unknown', 'Sensor-Daten ungültig'
        
        temp_diff = outdoor_temp - indoor_dp
        
        if temp_diff > threshold + 1.0:
            return 'ok', 'Kein Kondensationsrisiko'
        elif temp_diff > threshold:
            return 'warning', 'Erhöhte Aufmerksamkeit'
        elif temp_diff > 0:
            return 'critical', 'Hohes Kondensationsrisiko!'
        else:
            return 'critical', 'KONDENSATION MÖGLICH!'




# =============================================================================
# 4. ERWEITERTE HAUPTKLASSE - FEHLENDE METHODEN
# =============================================================================


# Ergänzung zur EnhancedTaupunktController Klasse:


def _complete_handle_wakeup(self, pin) -> None:
    """Vollständiger Interrupt-Handler für Wake-up Button"""
    self.last_user_activity = time.time()
    if not self.is_display_on:
        self.display.set_backlight(True)
        self.is_display_on = True
        print("Display aktiviert durch Benutzer")
    
    # Alarm bestätigen falls aktiv
    if self.alarm.is_alarm_active:
        self.alarm.stop_alarm()
        print("Alarm durch Benutzer bestätigt")




async def control_loop(self) -> None:
    """Hauptsteuerungsschleife"""
    self.system_status = "running"
    print("Hauptsteuerungsschleife gestartet")
    
    while True:
        try:
            # Watchdog füttern
            self.wdt.feed()
            
            # Sensor-Daten lesen
            sensor_data = await self._read_all_sensors()
            
            # Taupunkte berechnen
            processed_data = self._process_sensor_data(sensor_data)
            
            # Trends aktualisieren
            trend_data = self._update_trends(processed_data)
            
            # Kondensationsrisiko bewerten
            risk_data = self._evaluate_risks(processed_data)
            
            # Vollständige Daten kombinieren
            complete_data = {**processed_data, **risk_data}
            
            # LEDs aktualisieren
            self._update_led_status(risk_data['risk_level'])
            
            # Display aktualisieren
            if self.is_display_on:
                self.display.show_main_screen(complete_data, trend_data)
            
            # Alarms prüfen
            await self._check_alarms(complete_data)
            
            # Display-Timeout prüfen
            self._check_display_timeout()
            
            # Daten loggen
            await self.enhanced_logger.log_data_async(complete_data, trend_data)
            
            # Speicher-Management
            if time.time() % 300 < 1:  # Alle 5 Minuten
                gc.collect()
            
            await asyncio.sleep(self.params['mess_intervall_sek'])
            
        except Exception as e:
            print(f"Fehler in Hauptschleife: {e}")
            self.system_status = "error"
            await asyncio.sleep(10)  # Kurze Pause bei Fehlern




async def _read_all_sensors(self) -> dict:
    """Liest alle verfügbaren Sensoren asynchron"""
    sensor_data = {}
    
    for name, sensor in self.sensors.items():
        try:
            temp, humidity = await sensor.read_async()
            if temp is not None and humidity is not None:
                # Kalibrierung anwenden
                temp_cal, hum_cal = self.calibrator.apply_calibration(name, temp, humidity)
                sensor_data[name] = {'temp': temp_cal, 'humidity': hum_cal, 'valid': True}
            else:
                sensor_data[name] = {'temp': None, 'humidity': None, 'valid': False}
        except Exception as e:
            print(f"Sensor {name} Lesefehler: {e}")
            sensor_data[name] = {'temp': None, 'humidity': None, 'valid': False}
    
    return sensor_data




def _process_sensor_data(self, sensor_data: dict) -> dict:
    """Verarbeitet Sensor-Daten und berechnet Taupunkte"""
    processed = {}
    calc = TaupunktCalculator()
    
    for location in ['innen', 'aussen']:
        key_temp = f't_{location[:2]}'  # t_in, t_out
        key_hum = f'h_{location[:2]}'   # h_in, h_out  
        key_dp = f'dp_{location[:2]}'   # dp_in, dp_out
        
        if location in sensor_data and sensor_data[location]['valid']:
            temp = sensor_data[location]['temp']
            humidity = sensor_data[location]['humidity']
            dew_point = calc.calculate_dew_point(temp, humidity)
            
            processed[key_temp] = temp
            processed[key_hum] = humidity
            processed[key_dp] = dew_point
        else:
            processed[key_temp] = None
            processed[key_hum] = None
            processed[key_dp] = None
    
    return processed




def _update_trends(self, data: dict) -> dict:
    """Aktualisiert Trend-Analysen"""
    trends = {}
    
    if data.get('t_in') is not None:
        self.trend_analyzer.add_measurement('innen', data['t_in'])
        trends['in'] = self.trend_analyzer.get_trend_data('innen', data['t_in'])
    
    if data.get('t_out') is not None:
        self.trend_analyzer.add_measurement('aussen', data['t_out'])
        trends['out'] = self.trend_analyzer.get_trend_data('aussen', data['t_out'])
    
    return trends




def _evaluate_risks(self, data: dict) -> dict:
    """Bewertet Kondensationsrisiko"""
    calc = TaupunktCalculator()
    
    indoor_dp = data.get('dp_in')
    outdoor_temp = data.get('t_out')
    
    if indoor_dp is not None and outdoor_temp is not None:
        risk_level, risk_message = calc.evaluate_condensation_risk(
            indoor_dp, outdoor_temp, self.params['taupunkt_grenze_c']
        )
    else:
        risk_level, risk_message = 'unknown', 'Sensordaten unvollständig'
    
    return {
        'risk_level': risk_level,
        'risk_message': risk_message,
        'status': risk_level
    }




def _update_led_status(self, risk_level: str) -> None:
    """Aktualisiert LED-Status basierend auf Risiko"""
    # Alle LEDs aus
    for led in self.leds.values():
        led.off()
    
    # Status-spezifische LED
    led_map = {
        'ok': 'gruen',
        'warning': 'gelb', 
        'critical': 'rot',
        'unknown': 'gelb'
    }
    
    led_name = led_map.get(risk_level, 'gelb')
    if led_name in self.leds:
        self.leds[led_name].on()




async def _check_alarms(self, data: dict) -> None:
    """Prüft Alarm-Bedingungen"""
    risk_level = data.get('risk_level', 'unknown')
    
    # Kondensations-Alarm
    if risk_level == 'critical' and not self.alarm.is_alarm_active:
        message = data.get('risk_message', 'Kondensationsrisiko!')
        self.alarm.trigger_alarm('condensation', message)
        if self.display:
            self.display.show_alarm_screen('KONDENSATION', message)
    
    # Sensor-Ausfall-Alarm
    if data.get('t_in') is None or data.get('t_out') is None:
        if not self.alarm.is_alarm_active or self.alarm.alarm_type != 'sensor_failure':
            self.alarm.trigger_alarm('sensor_failure', 'Sensor-Ausfall erkannt')




def _check_display_timeout(self) -> None:
    """Prüft Display-Timeout"""
    if (self.is_display_on and 
        time.time() - self.last_user_activity > self.params['display_timeout_sek']):
        self.display.set_backlight(False)
        self.is_display_on = False
        print("Display wegen Inaktivität ausgeschaltet")




async def run_system(self) -> None:
    """Haupteinstiegspunkt des Systems"""
    print("System wird gestartet...")
    
    # Initialisierungs-Screen
    if self.display:
        self.display.clear_screen()
        self.display.show_main_screen({'status': 'initializing'}, {})
    
    # Tasks starten
    tasks = [
        asyncio.create_task(self.control_loop()),
        asyncio.create_task(self.alarm.alarm_pattern_task())
    ]
    
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("System wird beendet...")
    finally:
        self.alarm.stop_alarm()
        if self.display:
            self.display.set_backlight(False)




# =============================================================================
# 5. HAUPTPROGRAMM-EINSTIEGSPUNKT
# =============================================================================


async def main():
    """Hauptprogramm-Einstiegspunkt"""
    controller = EnhancedTaupunktController()
    await controller.run_system()


# Für den Start
if __name__ == "__main__":
    asyncio.run(main())






# Fehlende Komponenten Ihres Taupunkt-Steuerungs-Programms


## 1. **Kritische fehlende Klassen**


### DisplayController
```python
class DisplayController:
    def __init__(self, spi, pins, width, height):
        # Display-Initialisierung
        pass
    
    def set_backlight(self, state):
        # Hintergrundbeleuchtung steuern
        pass
    
    def show_main_screen(self, data):
        # Hauptbildschirm anzeigen
        pass
```


### AlarmController
```python
class AlarmController:
    def __init__(self, buzzer_pin):
        # Alarm-System initialisieren
        pass
    
    def trigger_alarm(self, alarm_type):
        # Alarm auslösen
        pass
```


## 2. **Unvollständige Methoden**


### In der Hauptklasse `EnhancedTaupunktController`:
- `_handle_wakeup()` - Methode ist abgeschnitten
- **Hauptschleife fehlt komplett** - `run()` oder `main_loop()`
- Taupunkt-Berechnungslogik
- LED-Steuerungslogik basierend auf Messwerten
- Display-Update-Routinen


## 3. **Fehlende Core-Funktionalität**


### Taupunkt-Berechnung
```python
def calculate_dew_point(self, temp, humidity):
    """Magnus-Formel für Taupunkt-Berechnung"""
    pass
```


### Hauptsteuerungslogik
```python
async def control_loop(self):
    """Hauptsteuerungsschleife"""
    pass


async def process_measurements(self):
    """Messwerte verarbeiten und Entscheidungen treffen"""
    pass
```


## 4. **Configuration Management**


### config.json Datei
- Die Konfigurationsdatei wird referenziert, aber nicht bereitgestellt
- Standard-Konfiguration ist definiert, aber möglicherweise unvollständig


## 5. **Display-Funktionalität**


### Bildschirm-Layouts
- Hauptanzeige mit aktuellen Werten
- Trend-Anzeige
- Kalibrierungs-Menü
- Alarm-/Status-Anzeigen


### Display-Energieverwaltung
- Auto-Abschaltung nach Timeout
- Wake-up Funktionalität


## 6. **Alarm-System**


### Alarm-Bedingungen
- Taupunkt-Grenzwert-Überwachung
- Verschiedene Alarm-Typen (visuell, akustisch)
- Alarm-Bestätigung und -Reset


## 7. **Fehlerbehandlung & Robustheit**


### Sensor-Ausfälle
- Fallback-Strategien wenn Sensoren nicht verfügbar
- Sensor-Gesundheitsüberwachung
- Automatische Wiederherstellung


### System-Stabilität
- Watchdog-Fütterung in der Hauptschleife
- Memory-Management
- Exception-Handling in kritischen Pfaden


## 8. **Benutzerinteraktion**


### Button-Handling
- Wake-up Button ist implementiert, aber abgeschnitten
- Menü-Navigation (falls geplant)
- Kalibrierungs-Interface


## 9. **Performance-Optimierungen**


### Async/Await Pattern
- Vollständige Integration des async-Patterns
- Task-Scheduling
- Cooperative Multitasking


### Memory Management
- Garbage Collection in kritischen Bereichen
- Buffer-Größen-Optimierung


## 10. **Spezifische Taupunkt-Logik**


### Entscheidungslogik
```python
def evaluate_condensation_risk(self, indoor_dp, outdoor_temp):
    """Bewertung des Kondensationsrisikos"""
    pass


def update_led_status(self, risk_level):
    """LED-Status basierend auf Risiko aktualisieren"""
    pass
```


## 11. **Initialisierungs-Sequenz**


### Startup-Routine
```python
async def initialize_system(self):
    """Vollständige System-Initialisierung"""
    pass


async def run_system(self):
    """Hauptprogramm-Einstiegspunkt"""
    pass
```




.