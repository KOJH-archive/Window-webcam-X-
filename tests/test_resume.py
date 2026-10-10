import src.main as main_module
from src.main import Guardian
from types import SimpleNamespace


def test_duplicate_resume_clears_suspended_flag():
    guardian = object.__new__(Guardian)
    guardian.suspended = True
    guardian.resume_handled_at = 100
    guardian._resume(101, record=True)
    assert guardian.suspended is False


def test_resume_does_not_reopen_camera_while_paused():
    guardian = object.__new__(Guardian)
    calls = []
    guardian.suspended = True
    guardian.resume_handled_at = 0
    guardian.manual_pause = True
    guardian.focus = SimpleNamespace(stop=lambda: calls.append("focus_stop"))
    guardian.switches = SimpleNamespace(reset=lambda: calls.append("switch_reset"))
    guardian._release_camera = lambda: calls.append("release")
    guardian._open_camera = lambda: calls.append("open")
    guardian.presence = SimpleNamespace(after_resume=lambda now, grace: calls.append("grace"))
    guardian.settings = SimpleNamespace(power=SimpleNamespace(resume_grace_seconds=60))
    guardian.store = SimpleNamespace(event=lambda kind: calls.append(kind))
    guardian._resume(100, record=True)
    assert "open" not in calls
    assert calls[-1] == "wake"


def test_resume_reopens_camera_and_starts_grace_before_wake_event():
    guardian = object.__new__(Guardian)
    calls = []
    guardian.suspended = True
    guardian.resume_handled_at = 0
    guardian.manual_pause = False
    guardian.focus = SimpleNamespace(stop=lambda: calls.append("focus_stop"))
    guardian.switches = SimpleNamespace(reset=lambda: calls.append("switch_reset"))
    guardian._release_camera = lambda: calls.append("release")
    guardian._open_camera = lambda: calls.append("open")
    guardian.presence = SimpleNamespace(after_resume=lambda now, grace: calls.append(("grace", now, grace)))
    guardian.settings = SimpleNamespace(power=SimpleNamespace(resume_grace_seconds=60))
    guardian.store = SimpleNamespace(event=lambda kind: calls.append(kind))

    guardian._resume(100, record=True)

    assert calls == ["focus_stop", "switch_reset", "release", "open", ("grace", 100, 60), "wake"]
    guardian._resume(101, record=True)
    assert calls.count("open") == 1
    assert calls.count("wake") == 1


def test_camera_failure_notifies_once_per_failure_period(monkeypatch):
    guardian = object.__new__(Guardian)
    notifications = []
    guardian.vision = object()
    guardian.camera = SimpleNamespace(open=lambda: False)
    guardian.logger = SimpleNamespace(warning=lambda *args: None)
    guardian.camera_retry_at = 0
    guardian.camera_error_notified = False
    monkeypatch.setattr(main_module, "notify", lambda title, message: notifications.append((title, message)))

    assert guardian._open_camera() is False
    assert guardian._open_camera() is False
    assert len(notifications) == 1

    guardian.camera.open = lambda: True
    assert guardian._open_camera() is True
    guardian.camera.open = lambda: False
    assert guardian._open_camera() is False
    assert len(notifications) == 2
