import time
import uasyncio as asyncio

class AsyncSensorAHT20:
    """Asynchronous driver for the AHT20 sensor."""

    def __init__(self, i2c, addr=0x38):
        self.i2c = i2c
        self.addr = addr
        self.last_read_time = 0
        self.min_read_interval = 1.0
        try:
            self.i2c.writeto(self.addr, b'\xBE\x08\x00')
        except Exception:
            pass

    async def read_async(self):
        current_time = time.time()
        if current_time - self.last_read_time < self.min_read_interval:
            await asyncio.sleep_ms(100)
        try:
            self.i2c.writeto(self.addr, b'\xAC\x33\x00')
            await asyncio.sleep_ms(80)
            data = self.i2c.readfrom(self.addr, 7)
            hum_raw = (((data[1] << 16) | (data[2] << 8) | data[3]) >> 4)
            humidity = hum_raw * 100 / 1048576
            temp_raw = (((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5])
            temp = temp_raw * 200 / 1048576 - 50
            self.last_read_time = current_time
            return temp, humidity
        except Exception as e:
            print('AHT20 Lesefehler:', e)
            return None, None
