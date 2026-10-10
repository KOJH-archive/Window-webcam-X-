from datetime import datetime, timedelta, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.storage import Store


def test_dashboard_renders_local_records(tmp_path, monkeypatch):
    root = Path(__file__).parents[1]
    config = tmp_path / "config.yaml"
    config.write_text((root / "config.yaml").read_text(encoding="utf-8").replace(
        "%LOCALAPPDATA%/DeskGuardian", tmp_path.as_posix()), encoding="utf-8")
    monkeypatch.setenv("DESK_GUARDIAN_CONFIG", str(config))
    store = Store(tmp_path / "guardian.db")
    at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    store.minute(at, present_ratio=1, facing_screen=1, input_activity=0,
                 app_switches=0, focus_score=70, label="focused")
    store.event("posture_alert", "pitch", at=at)
    store.session(at - timedelta(minutes=5), at, 75)
    store.close()
    app = AppTest.from_file(str(root / "dashboard" / "app.py"), default_timeout=15).run()
    assert not app.exception
    assert len(app.metric) == 5
    assert app.metric[1].value == "70점"
