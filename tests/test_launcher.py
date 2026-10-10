import launcher


def test_launcher_builds_explicit_safe_and_real_commands(monkeypatch):
    monkeypatch.setattr(launcher.sys, "executable", "pythonw.exe")
    assert launcher.guardian_command(False) == ["pythonw.exe", "-m", "src.main", "--dry-run"]
    assert launcher.guardian_command(True) == ["pythonw.exe", "-m", "src.main", "--enable-sleep"]


def test_running_check_releases_new_mutex(monkeypatch):
    released = []
    monkeypatch.setattr(launcher, "acquire", lambda: 42)
    monkeypatch.setattr(launcher, "release", released.append)
    assert launcher.guardian_is_running() is False
    assert released == [42]

    monkeypatch.setattr(launcher, "acquire", lambda: None)
    assert launcher.guardian_is_running() is True
    assert released == [42]
