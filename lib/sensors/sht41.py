import time
import uasyncio as asyncio

class AsyncSensorSHT41:
    """Asynchronous driver for the SHT41 sensor."""

    def __init__(self, i2c, addr=0x44):
        self.i2c = i2c
        self.addr = addr
        self.last_read_time = 0
        self.min_read_interval = 1.0

    async def read_async(self):
        current_time = time.time()
        if current_time - self.last_read_time < self.min_read_interval:
            await asyncio.sleep_ms(100)
        try:
            self.i2c.writeto(self.addr, b'\xFD')
            await asyncio.sleep_ms(10)
            data = self.i2c.readfrom(self.addr, 6)
            temp_raw = (data[0] << 8) | data[1]
            temp = -45 + 175 * temp_raw / 65535.0
            hum_raw = (data[3] << 8) | data[4]
            humidity = -6 + 125 * hum_raw / 65535.0
            humidity = max(0, min(100, humidity))
            self.last_read_time = current_time
            return temp, humidity
        except Exception as e:
            print('SHT41 Lesefehler:', e)
            return None, None
