import pytest
import os
import json
from lib.core.calc import SensorCalibrator


def test_apply_calibration(tmp_path):
    cal_file = tmp_path / "cal.json"
    data = {"innen": {"temp_offset": 1.0, "humidity_offset": -2.0}}
    cal_file.write_text(json.dumps(data))
    calib = SensorCalibrator(config_path=str(cal_file))
    temp, hum = calib.apply_calibration("innen", 20.0, 50.0)
    assert temp == pytest.approx(21.0)
    assert hum == pytest.approx(48.0)


def test_set_and_save_calibration(tmp_path):
    cal_file = tmp_path / "cal.json"
    calib = SensorCalibrator(config_path=str(cal_file))
    calib.set_calibration("innen", 0.5, 1.0)
    with open(cal_file, "r") as f:
        saved = json.load(f)
    assert saved["innen"]["temp_offset"] == 0.5
    assert saved["innen"]["humidity_offset"] == 1.0
