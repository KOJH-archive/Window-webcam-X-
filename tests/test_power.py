from src.power import SleepController


def test_sleep_order_dry_run_and_failure():
    calls = []
    record = lambda kind, detail=None, at=None: calls.append((kind, detail))
    release = lambda: (calls.append(("release", None)) or True)
    reopen = lambda: calls.append(("reopen", None))
    sleep = lambda locked: (calls.append(("power_call", locked)) or True)
    controller = SleepController(release, reopen, record, sleep_fn=sleep, dry_run=True)
    assert controller.suspend() == "dry_run"
    assert calls == [("sleep_dry_run", None)]
    calls.clear()
    controller.dry_run = False
    assert controller.suspend() == "sleep"
    assert [item[0] for item in calls] == ["sleep_request", "release", "power_call", "sleep"]
    calls.clear()
    controller.sleep_fn = lambda locked: False
    assert controller.suspend() == "failed"
    assert [item[0] for item in calls] == ["sleep_request", "release", "sleep_failed", "reopen"]
