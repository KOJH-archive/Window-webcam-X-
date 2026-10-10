from datetime import datetime, timezone

import pytest

from src.config import PostureConfig, PostureThresholds
from src.observe import FIELDS, Observer, metrics, quantile, summarize
from src.posture import Baseline, Calibrator, Posture, angle_delta, load_baseline, save_baseline
from src.vision import Features


def settings():
    return PostureConfig(True, 60, 10, PostureThresholds(1.25, .12, 20, 15))


def test_calibration_pitch_direction_and_persistence(tmp_path):
    c = Calibrator()
    neutral = Features(100, .5, 10, 0, 0)
    down = Features(100, .5, -8, 0, 0)
    for _ in range(30):
        c.add(neutral)
    with pytest.raises(ValueError):
        c.finish()
    for _ in range(15):
        c.add(down, down=True)
    baseline = c.finish()
    assert baseline.downward_sign == -1
    path = tmp_path / "baseline.json"
    save_baseline(path, baseline)
    assert load_baseline(path) == baseline


def test_angle_wrap_does_not_trigger_false_posture_or_observation():
    assert angle_delta(179, -177) == -4
    assert angle_delta(-179, 177) == 4
    baseline = Baseline(100, .5, -177, -179, 179, 1)
    features = Features(100, .5, 179, 179, -179)
    detector = Posture(settings(), baseline)
    assert detector.evaluate(features, 0) is None
    assert detector.evaluate(features, 60) is None
    observed = metrics(features, baseline)
    assert observed["pitch_delta"] == -4
    assert observed["yaw_delta"] == -2
    assert observed["roll_delta"] == 2


def test_calibration_pitch_direction_across_angle_wrap():
    calibrator = Calibrator()
    for _ in range(30):
        calibrator.add(Features(100, .5, 177, 0, 0))
    for _ in range(15):
        calibrator.add(Features(100, .5, -171, 0, 0), down=True)
    assert calibrator.finish().downward_sign == 1


def test_posture_sustained_cooldown_and_missing_face():
    baseline = Baseline(100, .5, 10, 0, 0, -1)
    detector = Posture(settings(), baseline)
    too_close = Features(130, .5, 10, 0, 0)
    assert detector.evaluate(too_close, 0) is None
    assert detector.evaluate(too_close, 59) is None
    assert detector.evaluate(too_close, 60) == "distance"
    assert detector.evaluate(too_close, 120) is None
    assert detector.evaluate(None, 121) is None
    assert detector.evaluate(Features(100, .5, -15, 0, 0), 700) is None
    assert detector.evaluate(Features(100, .5, -15, 0, 0), 760) == "pitch"
    assert detector.evaluate(Features(130, .5, 10, 40, 0), 1400) is None


def test_posture_type_change_restarts_sustained_timer():
    detector = Posture(settings(), Baseline(100, .5, 10, 0, 0, 1))
    close = Features(130, .5, 10, 0, 0)
    tilted = Features(100, .5, 10, 0, 20)
    assert detector.evaluate(close, 0) is None
    assert detector.evaluate(close, 30) is None
    assert detector.evaluate(tilted, 31) is None
    assert detector.evaluate(tilted, 60) is None
    assert detector.evaluate(tilted, 91) == "roll"


def test_observation_interval_columns_and_summary(tmp_path):
    baseline = Baseline(100, .5, 10, 0, 0, 1)
    observer = Observer(tmp_path, 5, 90)
    at = datetime.now(timezone.utc)
    features = Features(130, .6, 35, 0, 17)
    assert observer.record(0, at, features, baseline, 5, 2, 70)
    assert not observer.record(4.9, at, features, baseline, 5, 2, 70)
    assert observer.record(5, at, features, baseline, 5, 2, 70)
    path = next(tmp_path.glob("metrics_*.csv"))
    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(FIELDS)
    summary = summarize(tmp_path, 1, settings().thresholds)
    assert summary["face_size_ratio"]["p95"] == pytest.approx(1.3)
    assert summary["face_size_ratio"]["threshold_warning"]
    assert quantile([1, 2, 3], .95) == pytest.approx(2.9)
