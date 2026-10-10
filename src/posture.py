"""User-calibrated, indirect face-pose posture hints."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from statistics import median

from .config import PostureConfig
from .vision import Features


@dataclass(frozen=True)
class Baseline:
    face_size: float
    face_cy: float
    pitch: float
    yaw: float
    roll: float
    downward_sign: int


def angle_delta(value: float, reference: float) -> float:
    """Shortest signed difference between degree angles across the ±180° seam."""
    return (value - reference + 180) % 360 - 180


def load_baseline(path: Path) -> Baseline | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    baseline = Baseline(**raw)
    if baseline.face_size <= 1 or baseline.downward_sign not in (-1, 1) or not all(
        math.isfinite(getattr(baseline, name)) for name in ("face_size", "face_cy", "pitch", "yaw", "roll")
    ):
        raise ValueError("invalid posture baseline")
    return baseline


def save_baseline(path: Path, baseline: Baseline):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(baseline), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class Calibrator:
    def __init__(self):
        self.neutral: list[Features] = []
        self.head_down: list[Features] = []

    def add(self, features: Features | None, *, down: bool = False):
        if features and features.face_size > 1:
            (self.head_down if down else self.neutral).append(features)

    def finish(self) -> Baseline:
        if len(self.neutral) < 30 or len(self.head_down) < 15:
            raise ValueError("not enough valid face samples for calibration")
        value = lambda field: median(getattr(item, field) for item in self.neutral)
        pitch = value("pitch")
        movement = median(angle_delta(item.pitch, pitch) for item in self.head_down)
        if abs(movement) < 5:
            raise ValueError("head-down movement too small to determine pitch direction")
        return Baseline(value("face_size"), value("face_cy"), pitch,
                        value("yaw"), value("roll"), 1 if movement > 0 else -1)


class Posture:
    def __init__(self, config: PostureConfig, baseline: Baseline | None):
        self.config = config
        self.baseline = baseline
        self.started_at: float | None = None
        self.current_type: str | None = None
        self.cooldown_until = 0.0

    def set_baseline(self, baseline: Baseline | None):
        self.baseline = baseline
        self.started_at = None
        self.current_type = None
        self.cooldown_until = 0.0

    def evaluate(self, features: Features | None, now: float) -> str | None:
        if not self.config.enabled or self.baseline is None or features is None:
            self.started_at = None
            self.current_type = None
            return None
        baseline = self.baseline
        thresholds = self.config.thresholds
        turned = abs(angle_delta(features.yaw, baseline.yaw)) > 25
        deviation = None
        if not turned and features.face_size / baseline.face_size > thresholds.distance_ratio_max:
            deviation = "distance"
        elif not turned and features.face_cy - baseline.face_cy > thresholds.vertical_drop_ratio:
            deviation = "drop"
        elif baseline.downward_sign * angle_delta(features.pitch, baseline.pitch) > thresholds.pitch_deg_max:
            deviation = "pitch"
        elif abs(angle_delta(features.roll, baseline.roll)) > thresholds.roll_deg_max:
            deviation = "roll"
        if deviation is None:
            self.started_at = None
            self.current_type = None
            return None
        if self.current_type != deviation:
            self.started_at = now
            self.current_type = deviation
        if now - self.started_at < self.config.sustained_seconds or now < self.cooldown_until:
            return None
        self.cooldown_until = now + self.config.cooldown_minutes * 60
        return deviation
