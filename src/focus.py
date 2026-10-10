"""One-second, wall-clock minute aggregation and consecutive focus sessions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import FocusConfig


@dataclass(frozen=True)
class Sample:
    valid: bool
    present: bool
    facing: bool | None
    active_input: bool | None
    process: str | None
    focus_ready: bool = True


@dataclass(frozen=True)
class Minute:
    at: datetime
    present_ratio: float
    facing_screen: float | None
    input_activity: float | None
    app_switches: int | None
    focus_score: float | None
    label: str


class FocusAggregator:
    def __init__(self, config: FocusConfig, store):
        self.config = config
        self.store = store
        self.minute_at: datetime | None = None
        self.started_at_boundary = False
        self.samples: dict[int, Sample] = {}
        self.session_start: datetime | None = None
        self.session_scores: list[float] = []
        self.last_focused_end: datetime | None = None
        self.last_score: float | None = None

    @staticmethod
    def _minute(at: datetime) -> datetime:
        return at.astimezone(timezone.utc).replace(second=0, microsecond=0)

    def add(self, at: datetime, sample: Sample):
        minute = self._minute(at)
        if self.minute_at is None:
            self.minute_at = minute
            self.started_at_boundary = at.second == 0
        elif minute != self.minute_at:
            self.flush()
            self.minute_at = minute
            self.started_at_boundary = at.second == 0
        self.samples[at.astimezone(timezone.utc).second] = sample

    def flush(self, *, partial: bool = False):
        if self.minute_at is None:
            return
        minute = self._summarize() if not partial and self.started_at_boundary else None
        if minute is not None:
            self.store.minute(minute.at, present_ratio=minute.present_ratio,
                              facing_screen=minute.facing_screen,
                              input_activity=minute.input_activity,
                              app_switches=minute.app_switches,
                              focus_score=minute.focus_score, label=minute.label)
            self.last_score = minute.focus_score
            self._session(minute)
        else:
            self._end_session()
        self.samples.clear()
        self.minute_at = None

    def _summarize(self) -> Minute:
        at = self.minute_at
        valid = [sample for sample in self.samples.values() if sample.valid]
        present_ratio = sum(s.present for s in valid) / len(valid) if valid else 0.0
        if len(valid) < 48:
            return Minute(at, present_ratio, None, None, None, None, "unavailable")
        if present_ratio < .5:
            return Minute(at, present_ratio, None, None, None, None, "away")
        present = [s for s in valid if s.present]
        if sum(s.focus_ready for s in present) < .8 * len(present):
            return Minute(at, present_ratio, None, None, None, None, "unavailable")
        facing = sum(s.facing is True for s in valid) / len(valid)
        active = sum(s.active_input is True for s in valid) / len(valid)
        processes = [s.process for s in present if s.process is not None]
        switches = sum(a != b for a, b in zip(processes, processes[1:]))
        weights = self.config.weights
        stability = max(0.0, 1 - self.config.app_switch_penalty_per_switch * switches)
        score = 100 * (weights.facing_screen * facing + weights.input_activity * active +
                       weights.app_stability * stability)
        label = "focused" if score >= 70 - 1e-9 else "neutral" if score >= 40 else "distracted"
        return Minute(at, present_ratio, facing, active, switches, round(score, 2), label)

    def _session(self, minute: Minute):
        if minute.label != "focused":
            self._end_session()
            return
        if self.last_focused_end != minute.at:
            self._end_session()
            self.session_start = minute.at
        self.session_scores.append(minute.focus_score)
        self.last_focused_end = minute.at + timedelta(minutes=1)

    def _end_session(self):
        if self.session_start and self.last_focused_end and len(self.session_scores) >= 5:
            self.store.session(self.session_start, self.last_focused_end,
                               sum(self.session_scores) / len(self.session_scores))
        self.session_start = None
        self.session_scores = []
        self.last_focused_end = None

    def stop(self):
        self.flush(partial=True)
