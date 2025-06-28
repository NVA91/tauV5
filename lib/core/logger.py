import os
import time

try:
    import sdcardio
    import storage
    from machine import SPI, Pin
except ImportError:
    sdcardio = None
    storage = None
    SPI = None
    Pin = None

class EnhancedDataLogger:
    """Simple rotating logger for SD cards."""

    def __init__(self, pins, params):
        self.params = params
        self.last_log_time = 0
        self.is_mounted = False
        self.max_file_size = params.get('max_log_file_mb', 5) * 1024 * 1024
        self.max_files = params.get('max_log_files', 30)
        self._init_sd_card(pins)

    def _init_sd_card(self, pins):
        if not sdcardio:
            print('sdcardio not available')
            return
        try:
            spi = SPI(pins['sd_spi_id'],
                      sck=Pin(pins['sd_sck']),
                      mosi=Pin(pins['sd_mosi']),
                      miso=Pin(pins['sd_miso']))
            sd = sdcardio.SDCard(spi, Pin(pins['sd_cs'], Pin.OUT))
            vfs = storage.VfsFat(sd)
            storage.mount(vfs, '/sd')
            self.is_mounted = True
            self._write_header()
        except Exception as e:
            print('SD-Karte Initialisierungsfehler:', e)

    def _get_current_log_file_path(self):
        return f"/sd/{self.params['log_file_prefix']}_current.csv"

    def _write_header(self):
        if not self.is_mounted:
            return
        path = self._get_current_log_file_path()
        try:
            with open(path, 'a+') as f:
                if f.tell() == 0:
                    f.write('timestamp,temp_in,hum_in,dp_in,temp_out,hum_out,dp_out,'
                            'temp_in_avg5,temp_out_avg5,status,trend_in,trend_out\n')
        except Exception as e:
            print('Header-Schreibfehler:', e)

    async def log_data_async(self, data, trends):
        if not self.is_mounted:
            return
        current_time = time.time()
        if current_time - self.last_log_time < self.params['log_interval_sek']:
            return
        path = self._get_current_log_file_path()
        line = (f"{current_time},{data['t_in']:.2f},{data['h_in']:.2f},"
                f"{data['dp_in']:.2f},{data['t_out']:.2f},{data['h_out']:.2f},"
                f"{data['dp_out']:.2f},{trends['in'].avg_5min:.2f},"
                f"{trends['out'].avg_5min:.2f},{data['status']},"
                f"{trends['in'].trend},{trends['out'].trend}\n")
        try:
            with open(path, 'a') as f:
                f.write(line)
            self.last_log_time = current_time
        except Exception as e:
            print('Logging-Fehler:', e)
