from datetime import datetime, timedelta, timezone

from src.config import load_settings
from src.focus import FocusAggregator, Sample


class MemoryStore:
    def __init__(self):
        self.minutes = []
        self.sessions = []

    def minute(self, at, **values):
        self.minutes.append((at, values))

    def session(self, start, end, score):
        self.sessions.append((start, end, score))


def make_aggregator():
    from pathlib import Path
    config = load_settings(Path(__file__).parents[1] / "config.yaml").focus
    store = MemoryStore()
    return FocusAggregator(config, store), store


def minute_samples(aggregator, start, *, valid=60, present=True, facing=True,
                   active=False, process="editor.exe"):
    for second in range(60):
        aggregator.add(start + timedelta(seconds=second),
                       Sample(second < valid, present, facing, active, process))


def test_time_weighting_and_unavailable():
    aggregator, store = make_aggregator()
    start = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
    minute_samples(aggregator, start, valid=47)
    minute_samples(aggregator, start + timedelta(minutes=1))
    aggregator.add(start + timedelta(minutes=2), Sample(True, True, True, False, "editor.exe"))
    assert store.minutes[0][1]["label"] == "unavailable"
    assert store.minutes[1][1]["focus_score"] == 70
    assert store.minutes[1][1]["label"] == "focused"
    aggregator.stop()
    assert len(store.minutes) == 2


def test_switches_and_five_minute_session():
    aggregator, store = make_aggregator()
    start = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
    for index in range(5):
        minute_samples(aggregator, start + timedelta(minutes=index))
    minute_samples(aggregator, start + timedelta(minutes=5), present=False)
    aggregator.add(start + timedelta(minutes=6), Sample(True, False, None, None, None))
    assert len(store.sessions) == 1
    assert store.sessions[0][:2] == (start, start + timedelta(minutes=5))
    assert store.minutes[5][1]["label"] == "away"


def test_process_switch_penalty_and_partial_minute():
    aggregator, store = make_aggregator()
    start = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
    for second in range(60):
        process = "a.exe" if second < 30 else "b.exe"
        aggregator.add(start + timedelta(seconds=second), Sample(True, True, True, False, process))
    aggregator.add(start + timedelta(minutes=1), Sample(True, True, True, False, "b.exe"))
    assert store.minutes[0][1]["app_switches"] == 1
    assert store.minutes[0][1]["focus_score"] == 65.5
    aggregator.stop()
    assert len(store.minutes) == 1


def test_presence_still_counted_before_posture_calibration():
    aggregator, store = make_aggregator()
    start = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
    for second in range(60):
        aggregator.add(start + timedelta(seconds=second),
                       Sample(True, True, None, False, "editor.exe", focus_ready=False))
    aggregator.add(start + timedelta(minutes=1), Sample(True, True, None, False, "editor.exe", False))
    assert store.minutes[0][1]["present_ratio"] == 1
    assert store.minutes[0][1]["focus_score"] is None
    assert store.minutes[0][1]["label"] == "unavailable"


def test_half_minute_present_uses_full_minute_denominator():
    aggregator, store = make_aggregator()
    start = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
    for second in range(60):
        present = second < 30
        aggregator.add(start + timedelta(seconds=second),
                       Sample(True, present, present, False, "editor.exe"))
    aggregator.add(start + timedelta(minutes=1), Sample(True, True, True, False, "editor.exe"))
    assert store.minutes[0][1]["present_ratio"] == .5
    assert store.minutes[0][1]["focus_score"] == 50
    assert store.minutes[0][1]["label"] == "neutral"
