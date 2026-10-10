from src.config import PresenceConfig
from src.presence import Observation, Presence


def tracker():
    return Presence(PresenceConfig(300, 15, True, 30, 0.5))


def test_absence_warning_sleep_and_recent_input():
    state = tracker()
    assert state.tick(Observation.NO_FACE, 0, 0).present
    assert state.tick(Observation.NO_FACE, 1, 1).present
    assert state.tick(Observation.NO_FACE, 2, 2).present
    # First NO_FACE began at t=0; recent input keeps the user present but does not shift that timestamp.
    assert state.tick(Observation.NO_FACE, 284, 284).state == "AWAY_PENDING"
    decision = state.tick(Observation.NO_FACE, 285, 285)
    assert decision.warn and not decision.sleep
    assert not state.tick(Observation.NO_FACE, 286, 286).warn
    assert state.tick(Observation.NO_FACE, 0, 287).present
    assert not state.tick(Observation.NO_FACE, 299, 299).sleep
    assert state.tick(Observation.NO_FACE, 300, 300).sleep


def test_unavailable_hold_face_and_grace():
    state = tracker()
    for second in (0, 1, 2, 290):
        state.tick(Observation.NO_FACE, 400, second)
    assert state.tick(Observation.UNAVAILABLE, 500, 300).state == "UNAVAILABLE"
    for second in (301, 302, 303):
        state.tick(Observation.NO_FACE, 500, second)
    assert not state.tick(Observation.NO_FACE, 500, 400).sleep
    assert state.tick(Observation.NO_FACE, 500, 401, hold=True).present is False
    assert state.tick(Observation.FACE, 500, 500).present
    state.after_resume(600, 60)
    assert not state.tick(Observation.NO_FACE, 800, 659).sleep
    assert not state.tick(Observation.NO_FACE, 800, 660).sleep
