import math
import pytest

from lib.core.calc import TaupunktCalculator


def test_dew_point_value():
    dp = TaupunktCalculator.calculate_dew_point(20.0, 50.0)
    assert 9.0 < dp < 10.0


def test_invalid_humidity():
    assert math.isnan(TaupunktCalculator.calculate_dew_point(25.0, 0))
    assert math.isnan(TaupunktCalculator.calculate_dew_point(25.0, 150))


def test_condensation_risk_levels():
    calc = TaupunktCalculator()
    level, _ = calc.evaluate_condensation_risk(10.0, 15.0, 2.0)
    assert level == 'ok'
    level, _ = calc.evaluate_condensation_risk(10.0, 12.5, 2.0)
    assert level == 'warning'
    level, _ = calc.evaluate_condensation_risk(10.0, 11.0, 2.0)
    assert level == 'critical'
