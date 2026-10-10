"""Camera health is distinct from absence; all timing is monotonic seconds."""
from dataclasses import dataclass
from enum import Enum

from .config import PresenceConfig


class Observation(str, Enum):
    FACE = "face"
    NO_FACE = "no_face"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Decision:
    state: str
    warn: bool = False
    sleep: bool = False
    present: bool = False


class Presence:
    def __init__(self, config: PresenceConfig):
        self.config = config
        self.state = "UNAVAILABLE"
        self.absence_since: float | None = None
        self.candidate_since: float | None = None
        self.no_face_streak = 0
        self.warned = False
        self.grace_until = 0.0

    def reset(self, *, unavailable: bool = False):
        self.state = "UNAVAILABLE" if unavailable else "PRESENT"
        self.absence_since = None
        self.candidate_since = None
        self.no_face_streak = 0
        self.warned = False

    def after_resume(self, now: float, grace_seconds: float):
        self.reset(unavailable=True)
        self.grace_until = now + grace_seconds

    def tick(self, observation: Observation, idle_seconds: float, now: float, *, hold: bool = False) -> Decision:
        if observation is Observation.UNAVAILABLE:
            self.reset(unavailable=True)
            return Decision("UNAVAILABLE")
        if hold or now < self.grace_until:
            self.reset()
            return Decision("PRESENT", present=observation is Observation.FACE)
        if observation is Observation.FACE:
            self.reset()
            return Decision("PRESENT", present=True)
        if self.no_face_streak == 0:
            self.candidate_since = now
        self.no_face_streak += 1
        if self.no_face_streak < 3:
            self.state = "PRESENT"
            return Decision("PRESENT", present=True)
        if self.absence_since is None:
            self.absence_since = self.candidate_since
        active_input = self.config.input_override and idle_seconds < self.config.input_override_seconds
        if active_input:
            self.state = "PRESENT"
            self.warned = False
            return Decision("PRESENT", present=True)
        self.state = "AWAY_PENDING"
        absence = now - self.absence_since
        ready = min(absence, idle_seconds)
        if ready < self.config.absence_seconds - self.config.warn_before_seconds:
            self.warned = False
            return Decision("AWAY_PENDING")
        warn = not self.warned
        self.warned = True
        return Decision("AWAY_PENDING", warn=warn,
                        sleep=ready >= self.config.absence_seconds)
