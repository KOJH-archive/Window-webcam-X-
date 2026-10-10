from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.config import load_settings
from src.storage import Store, read_only

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def test_config_defaults_and_invalid_weights(tmp_path):
    source = (ROOT / "config.yaml").read_text(encoding="utf-8")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(source, encoding="utf-8")
    settings = load_settings(config_file)
    assert settings.camera.index == 0
    assert settings.camera.fps_active == 5
    assert settings.presence.absence_seconds == 300
    assert settings.focus.weights.facing_screen == 0.4
    config_file.write_text(source.replace("facing_screen: 0.40", "facing_screen: 0.50"), encoding="utf-8")
    with pytest.raises(ValueError, match="sum to 1"):
        load_settings(config_file)


def test_storage_upsert_events_and_retention(tmp_path):
    path = tmp_path / "guardian.db"
    old = datetime(2026, 1, 1, tzinfo=UTC)
    now = old + timedelta(days=91)
    store = Store(path, retention_days=90)
    store.minute(old, present_ratio=1, facing_screen=1, input_activity=1,
                 app_switches=0, focus_score=90, label="focused")
    store.minute(old, present_ratio=0, facing_screen=0, input_activity=0,
                 app_switches=0, focus_score=None, label="away")
    store.event("sleep_request", at=old)
    store.session(old, old + timedelta(minutes=5), 90)
    assert store.connection.execute("SELECT COUNT(*) FROM minute_stats").fetchone()[0] == 1
    assert store.connection.execute("SELECT label,focus_score FROM minute_stats").fetchone() == ("away", None)
    with pytest.raises(ValueError):
        store.event("sleep", "window title")
    store.cleanup(now)
    assert store.connection.execute("SELECT COUNT(*) FROM minute_stats").fetchone()[0] == 0
    assert store.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert store.connection.execute("SELECT COUNT(*) FROM focus_sessions").fetchone()[0] == 0
    store.close()
    with read_only(path) as reader:
        assert reader.execute("SELECT COUNT(*) FROM minute_stats").fetchone()[0] == 0
