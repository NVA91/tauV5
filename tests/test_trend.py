from lib.core.trend import TrendAnalyzer


def test_trend_computation():
    analyzer = TrendAnalyzer(measurement_interval=60)
    for i in range(5):
        analyzer.add_measurement('innen', 20 + i)
    data = analyzer.get_trend_data('innen', 24)
    assert data.trend == 'rising'
    assert data.current == 24
    assert data.avg_5min > 20
