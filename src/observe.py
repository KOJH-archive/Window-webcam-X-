"""Five-second numerical observations; no frames, landmarks, titles or app names."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from .posture import Baseline, angle_delta
from .vision import Features

FIELDS = ("ts", "face_detected", "face_size_ratio", "face_cy_delta", "pitch_delta", "yaw_delta",
          "roll_delta", "idle_seconds", "app_switches_last_min", "focus_score_last_min")


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (position - low)


def metrics(features: Features | None, baseline: Baseline | None):
    if features is None or baseline is None:
        return dict.fromkeys(FIELDS[2:7])
    return {"face_size_ratio": features.face_size / baseline.face_size,
            "face_cy_delta": features.face_cy - baseline.face_cy,
            "pitch_delta": baseline.downward_sign * angle_delta(features.pitch, baseline.pitch),
            "yaw_delta": angle_delta(features.yaw, baseline.yaw),
            "roll_delta": angle_delta(features.roll, baseline.roll)}


class Observer:
    def __init__(self, directory: Path, interval_seconds: float, retention_days: int):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.interval_seconds = interval_seconds
        self.last_at: float | None = None
        cutoff = datetime.now().date() - timedelta(days=retention_days)
        for path in self.directory.glob("metrics_????????.csv"):
            try:
                if datetime.strptime(path.stem[8:], "%Y%m%d").date() < cutoff:
                    path.unlink()
            except ValueError:
                continue

    def record(self, now_monotonic: float, at: datetime, features: Features | None,
               baseline: Baseline | None, idle_seconds: float,
               app_switches_last_min: int, focus_score_last_min: float | None) -> bool:
        if self.last_at is not None and now_monotonic - self.last_at < self.interval_seconds:
            return False
        self.last_at = now_monotonic
        path = self.directory / f"metrics_{at:%Y%m%d}.csv"
        is_new = not path.exists()
        row = {"ts": at.astimezone(timezone.utc).isoformat(timespec="seconds"),
               "face_detected": int(features is not None),
               **metrics(features, baseline), "idle_seconds": idle_seconds,
               "app_switches_last_min": app_switches_last_min,
               "focus_score_last_min": focus_score_last_min}
        with path.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
        return True


def summarize(directory: Path, days: int, thresholds) -> dict:
    today = datetime.now().date()
    data = {name: [] for name in ("face_size_ratio", "face_cy_delta", "pitch_delta", "yaw_delta", "roll_delta")}
    for path in Path(directory).glob("metrics_????????.csv"):
        try:
            date = datetime.strptime(path.stem[8:], "%Y%m%d").date()
        except ValueError:
            continue
        if not 0 <= (today - date).days < days:
            continue
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                if row.get("face_detected") != "1":
                    continue
                for name in data:
                    if row.get(name):
                        value = float(row[name])
                        data[name].append(abs(value) if name == "roll_delta" else value)
    limits = {"face_size_ratio": thresholds.distance_ratio_max,
              "face_cy_delta": thresholds.vertical_drop_ratio,
              "pitch_delta": thresholds.pitch_deg_max,
              "roll_delta": thresholds.roll_deg_max}
    return {name: {"count": len(values), "median": median(values) if values else None,
                   "p90": quantile(values, .9), "p95": quantile(values, .95),
                   "max": max(values) if values else None,
                   "threshold_warning": bool(values and name in limits and quantile(values, .95) > limits[name])}
            for name, values in data.items()}
