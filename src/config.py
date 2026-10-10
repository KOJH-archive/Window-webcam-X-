"""Validated user configuration. No environment-dependent work on import."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import Any

import yaml


def _number(name: str, value: Any, *, minimum: float = 0, strict: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if (strict and value <= minimum) or (not strict and value < minimum):
        raise ValueError(f"{name} must be {'>' if strict else '>='} {minimum}")
    return float(value)


def _integer(name: str, value: Any, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _path(value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("storage path must be a nonempty string")
    expanded = os.path.expandvars(value)
    if "%LOCALAPPDATA%" in expanded:
        expanded = expanded.replace("%LOCALAPPDATA%", str(Path.home() / "AppData" / "Local"))
    return Path(expanded).expanduser().resolve()


@dataclass(frozen=True)
class CameraConfig:
    index: int
    backend: str
    fps_active: float
    fps_idle: float
    width: int
    height: int
    stale_seconds: float


@dataclass(frozen=True)
class PresenceConfig:
    absence_seconds: float
    warn_before_seconds: float
    input_override: bool
    input_override_seconds: float
    min_face_confidence: float


@dataclass(frozen=True)
class PowerConfig:
    lock_before_sleep: bool
    resume_grace_seconds: float
    skip_if_processes: tuple[str, ...]


@dataclass(frozen=True)
class PostureThresholds:
    distance_ratio_max: float
    vertical_drop_ratio: float
    pitch_deg_max: float
    roll_deg_max: float


@dataclass(frozen=True)
class PostureConfig:
    enabled: bool
    sustained_seconds: float
    cooldown_minutes: float
    thresholds: PostureThresholds


@dataclass(frozen=True)
class FocusWeights:
    facing_screen: float
    input_activity: float
    app_stability: float


@dataclass(frozen=True)
class FocusConfig:
    enabled: bool
    window_seconds: int
    weights: FocusWeights
    yaw_deg_limit: float
    pitch_deg_limit: float
    app_switch_penalty_per_switch: float


@dataclass(frozen=True)
class Settings:
    camera: CameraConfig
    presence: PresenceConfig
    power: PowerConfig
    posture: PostureConfig
    focus: FocusConfig
    pause_when_fullscreen: bool
    db_path: Path
    retention_days: int
    observe_interval_seconds: float
    observe_csv_dir: Path


def _section(root: dict, name: str) -> dict:
    section = root.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"{name} must be a mapping")
    return section


def load_settings(path: str | Path) -> Settings:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config root must be a mapping")
    c = _section(raw, "camera")
    p = _section(raw, "presence")
    power = _section(raw, "power")
    posture = _section(raw, "posture")
    focus = _section(raw, "focus")
    quiet = _section(raw, "quiet")
    storage = _section(raw, "storage")
    observe = _section(raw, "observe")
    backend = c.get("backend")
    if backend not in ("DSHOW", "MSMF"):
        raise ValueError("camera.backend must be DSHOW or MSMF")
    camera = CameraConfig(_integer("camera.index", c.get("index")), backend,
                          _number("camera.fps_active", c.get("fps_active"), strict=True),
                          _number("camera.fps_idle", c.get("fps_idle"), strict=True),
                          _integer("camera.width", c.get("width"), minimum=1),
                          _integer("camera.height", c.get("height"), minimum=1),
                          _number("camera.stale_seconds", c.get("stale_seconds"), strict=True))
    if camera.fps_idle > camera.fps_active:
        raise ValueError("idle FPS cannot exceed active FPS")
    absence = _number("presence.absence_seconds", p.get("absence_seconds"), strict=True)
    warning = _number("presence.warn_before_seconds", p.get("warn_before_seconds"), strict=True)
    if warning >= absence:
        raise ValueError("warning must precede sleep")
    if not isinstance(p.get("input_override"), bool):
        raise ValueError("presence.input_override must be boolean")
    conf = _number("presence.min_face_confidence", p.get("min_face_confidence"))
    if conf > 1:
        raise ValueError("face confidence must be <= 1")
    presence = PresenceConfig(absence, warning, p["input_override"],
                              _number("presence.input_override_seconds", p.get("input_override_seconds")), conf)
    if not isinstance(power.get("lock_before_sleep"), bool):
        raise ValueError("power.lock_before_sleep must be boolean")
    skip = power.get("skip_if_processes")
    if not isinstance(skip, list) or any(not isinstance(x, str) or not x for x in skip):
        raise ValueError("power.skip_if_processes must be a list of names")
    power_config = PowerConfig(power["lock_before_sleep"],
                               _number("power.resume_grace_seconds", power.get("resume_grace_seconds")),
                               tuple(x.lower() for x in skip))
    if not isinstance(posture.get("enabled"), bool) or not isinstance(focus.get("enabled"), bool):
        raise ValueError("enabled must be boolean")
    t = _section(posture, "thresholds")
    thresholds = PostureThresholds(_number("distance ratio", t.get("distance_ratio_max"), minimum=1, strict=True),
                                   _number("vertical drop", t.get("vertical_drop_ratio")),
                                   _number("pitch max", t.get("pitch_deg_max")),
                                   _number("roll max", t.get("roll_deg_max")))
    posture_config = PostureConfig(posture["enabled"],
                                   _number("posture.sustained_seconds", posture.get("sustained_seconds"), strict=True),
                                   _number("posture.cooldown_minutes", posture.get("cooldown_minutes")), thresholds)
    w = _section(focus, "weights")
    weights = FocusWeights(*(_number(f"focus.weights.{name}", w.get(name))
                            for name in ("facing_screen", "input_activity", "app_stability")))
    if abs(sum((weights.facing_screen, weights.input_activity, weights.app_stability)) - 1) > 1e-9:
        raise ValueError("focus weights must sum to 1")
    focus_config = FocusConfig(focus["enabled"], _integer("focus.window_seconds", focus.get("window_seconds"), minimum=60),
                               weights, _number("focus.yaw_deg_limit", focus.get("yaw_deg_limit")),
                               _number("focus.pitch_deg_limit", focus.get("pitch_deg_limit")),
                               _number("focus.app_switch_penalty_per_switch", focus.get("app_switch_penalty_per_switch")))
    if focus_config.window_seconds != 60:
        raise ValueError("minute statistics require a 60-second window")
    if not isinstance(quiet.get("pause_when_fullscreen"), bool):
        raise ValueError("quiet.pause_when_fullscreen must be boolean")
    return Settings(camera, presence, power_config, posture_config, focus_config,
                    quiet["pause_when_fullscreen"], _path(storage.get("db_path")),
                    _integer("storage.retention_days", storage.get("retention_days"), minimum=1),
                    _number("observe.interval_seconds", observe.get("interval_seconds"), strict=True),
                    _path(observe.get("csv_dir")))
