import gc
import uasyncio as asyncio

from lib.core.calc import TaupunktCalculator
from lib.core.trend import TrendAnalyzer

class MockSensor:
    """Simple asynchronous sensor mock."""

    def __init__(self, readings):
        self.readings = readings
        self.index = 0

    async def read_async(self):
        await asyncio.sleep_ms(1)
        value = self.readings[self.index]
        self.index = (self.index + 1) % len(self.readings)
        return value

async def run_tests():
    print("Selftest start. Free mem:", gc.mem_free())

    # Create sensor mocks with two readings each
    sensor_in = MockSensor([(20.0, 50.0), (21.0, 51.0)])
    sensor_out = MockSensor([(5.0, 70.0), (4.5, 72.0)])
    sensors = {'innen': sensor_in, 'aussen': sensor_out}

    calc = TaupunktCalculator()
    trends = TrendAnalyzer(1)

    for i in range(2):
        data = {}
        for name, sensor in sensors.items():
            t, h = await sensor.read_async()
            dp = calc.calculate_dew_point(t, h)
            data[name] = (t, h, dp)
            trends.add_measurement(name, t)
        print(f"Sample {i+1}", data)

    trend_in = trends.get_trend_data('innen', data['innen'][0])
    print('Trend Innen:', trend_in)
    print('Free mem after tests:', gc.mem_free())

    dp_ref = calc.calculate_dew_point(20.0, 50.0)
    if not (9.0 < dp_ref < 10.0):
        raise AssertionError('Dew point calculation outside expected range')
    print('Dew point calculation OK')

async def _main():
    await run_tests()

def run_selftest():
    asyncio.run(_main())

if __name__ == '__main__':
    run_selftest()
