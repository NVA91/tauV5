from collections import deque, namedtuple

TrendData = namedtuple('TrendData', ['current', 'avg_5min', 'avg_15min', 'trend'])

class RingBuffer:
    """Fixed-size buffer for average calculations."""

    def __init__(self, size):
        self.size = size
        self.data = deque((), size)

    def add(self, value):
        self.data.append(value)

    def average(self):
        return sum(self.data) / len(self.data) if self.data else 0.0

    def is_full(self):
        return len(self.data) == self.size


class TrendAnalyzer:
    """Compute short term trends for temperature values."""

    def __init__(self, measurement_interval=900):
        self.measurement_interval = measurement_interval
        self.buffers = {
            'innen': {
                '5min': RingBuffer(max(1, 300 // measurement_interval)),
                '15min': RingBuffer(max(1, 900 // measurement_interval)),
            },
            'aussen': {
                '5min': RingBuffer(max(1, 300 // measurement_interval)),
                '15min': RingBuffer(max(1, 900 // measurement_interval)),
            }
        }

    def add_measurement(self, sensor_name, value):
        if sensor_name in self.buffers:
            for buf in self.buffers[sensor_name].values():
                buf.add(value)

    def get_trend_data(self, sensor_name, current_value):
        if sensor_name not in self.buffers:
            return TrendData(current_value, current_value, current_value, 'stable')

        buffers = self.buffers[sensor_name]
        avg5 = buffers['5min'].average()
        avg15 = buffers['15min'].average()

        if not buffers['5min'].is_full():
            trend = 'initializing'
        elif current_value > avg5 + 0.5:
            trend = 'rising'
        elif current_value < avg5 - 0.5:
            trend = 'falling'
        else:
            trend = 'stable'

        return TrendData(current_value, avg5, avg15, trend)
