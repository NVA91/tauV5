try:
    import st7789
    import vga1_16x16 as font_medium
    from machine import Pin
except ImportError:
    st7789 = None
    font_medium = None
    Pin = None

class DisplayController:
    """Control an ST7789 display."""

    def __init__(self, spi, pins, width, height):
        self.width = width
        self.height = height
        self.is_on = True
        try:
            if st7789:
                self.tft = st7789.ST7789(
                    spi,
                    width,
                    height,
                    reset=Pin(pins['lcd_rst'], Pin.OUT),
                    cs=Pin(pins['lcd_cs'], Pin.OUT),
                    dc=Pin(pins['lcd_dc'], Pin.OUT),
                    backlight=Pin(pins['lcd_bl'], Pin.OUT),
                    rotation=1
                )
                self.font = font_medium
                self.tft.init()
                self.set_backlight(True)
            else:
                self.tft = None
        except Exception as e:
            print('Display-Initialisierungsfehler:', e)
            self.tft = None

    def set_backlight(self, state):
        if self.tft:
            try:
                self.tft.backlight.value(1 if state else 0)
                self.is_on = state
            except Exception:
                pass

    def clear_screen(self, color=0x0000):
        if self.tft:
            self.tft.fill(color)

    def show_main_screen(self, data, trends):
        if not self.tft:
            return
        try:
            self.clear_screen(0x0000)
            self.tft.text(self.font, 'TAUPUNKT-KONTROLLE', 10, 10, 0xFFFF, 0x0000)
            y = 40
            self.tft.text(self.font, 'INNEN:', 10, y, 0x07E0, 0x0000)
            self.tft.text(self.font, f"Temp: {data.get('t_in', 0):.1f}C", 10, y+20, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Feuchte: {data.get('h_in', 0):.1f}%", 10, y+40, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Taupunkt: {data.get('dp_in', 0):.1f}C", 10, y+60, 0xFFE0, 0x0000)
            y = 140
            self.tft.text(self.font, 'AUSSEN:', 10, y, 0x001F, 0x0000)
            self.tft.text(self.font, f"Temp: {data.get('t_out', 0):.1f}C", 10, y+20, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Feuchte: {data.get('h_out', 0):.1f}%", 10, y+40, 0xFFFF, 0x0000)
            self.tft.text(self.font, f"Taupunkt: {data.get('dp_out', 0):.1f}C", 10, y+60, 0xFFE0, 0x0000)
            y = 240
            status = data.get('status', 'unknown')
            risk = data.get('risk_level', 'unknown')
            color = self._get_status_color(status)
            self.tft.text(self.font, f'Status: {status}', 10, y, color, 0x0000)
            self.tft.text(self.font, f'Risiko: {risk}', 10, y+20, color, 0x0000)
        except Exception as e:
            print('Display-Update-Fehler:', e)

    def show_alarm_screen(self, alarm_type, message):
        if not self.tft:
            return
        try:
            self.clear_screen(0xF800)
            self.tft.text(self.font, '!!! ALARM !!!', 10, 50, 0xFFFF, 0xF800)
            self.tft.text(self.font, alarm_type.upper(), 10, 80, 0xFFFF, 0xF800)
            self.tft.text(self.font, message, 10, 110, 0xFFFF, 0xF800)
        except Exception as e:
            print('Alarm-Display-Fehler:', e)

    def _get_status_color(self, status):
        colors = {
            'ok': 0x07E0,
            'warning': 0xFFE0,
            'critical': 0xF800,
            'unknown': 0xFFFF
        }
        return colors.get(status, 0xFFFF)
