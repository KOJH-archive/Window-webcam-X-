"""Desk Guardian worker, tray and safe-by-default command line."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from . import activity
from .capture import Camera
from .config import load_settings
from .focus import FocusAggregator, Sample
from .logging_setup import configure
from .notifier import notify
from .observe import Observer
from .posture import Calibrator, Posture, angle_delta, load_baseline, save_baseline
from .power import PowerMonitor, SleepController
from .presence import Observation, Presence
from .storage import Store
from .single_instance import acquire, release
from .tray import Tray
from .vision import FaceVision

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT / ("config.local.yaml" if (PROJECT / "config.local.yaml").exists() else "config.yaml")


class Guardian:
    def __init__(self, config_path: Path, *, enable_sleep: bool, observe: bool):
        self.config_path = Path(config_path).resolve()
        self.settings = load_settings(config_path)
        self.enable_sleep = enable_sleep
        self.observe_mode = observe
        self.logger = configure(self.settings.db_path.parent / "logs")
        self.store = Store(self.settings.db_path, self.settings.retention_days)
        self.baseline_path = self.settings.db_path.parent / "baseline.json"
        try:
            baseline = load_baseline(self.baseline_path)
        except (ValueError, OSError) as exc:
            self.logger.warning("baseline_unavailable %s", type(exc).__name__)
            baseline = None
        self.posture = Posture(self.settings.posture, baseline)
        self.presence = Presence(self.settings.presence)
        self.focus = FocusAggregator(self.settings.focus, self.store)
        self.observer = (Observer(self.settings.observe_csv_dir, self.settings.observe_interval_seconds,
                                  self.settings.retention_days) if observe else None)
        self.camera = Camera(self.settings.camera)
        self.vision: FaceVision | None = None
        self.power: PowerMonitor | None = None
        self.commands: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.tray = Tray(self.commands)
        self.sleep = SleepController(self._release_camera, self._open_camera, self.store.event,
                                     dry_run=not enable_sleep,
                                     lock_before=self.settings.power.lock_before_sleep)
        self.running = True
        self.paused_until = 0.0
        self.manual_pause = False
        self.last_inferred = 0.0
        self.inference_count = 0
        self.face_count = 0
        self.last_sequence = -1
        self.observation = Observation.UNAVAILABLE
        self.features = None
        self.camera_retry_at = 0.0
        self.camera_error_notified = False
        self.last_activity_at = 0.0
        self.last_sample_at = -1
        self.idle = None
        self.process = None
        self.fullscreen = False
        self.protected = False
        self.switches = activity.ForegroundSwitches()
        self.last_loop = time.monotonic()
        self.suspended = False
        self.resume_handled_at = 0.0

    def _open_camera(self) -> bool:
        try:
            if self.vision is None:
                self.vision = FaceVision(PROJECT / "models" / "face_landmarker.task",
                                         self.settings.presence.min_face_confidence)
            if self.camera.open():
                self.last_sequence = -1
                self.last_inferred = 0
                self.camera_retry_at = 0
                self.camera_error_notified = False
                return True
        except Exception as exc:
            self.logger.warning("camera_open_error %s", type(exc).__name__)
        self.camera_retry_at = time.monotonic() + 30
        if not self.camera_error_notified:
            notify("카메라 확인 필요", "카메라를 사용할 수 없어 감지와 자동 절전을 보류합니다.")
            self.camera_error_notified = True
        return False

    def _release_camera(self) -> bool:
        try:
            ok = self.camera.close()
            if ok and self.vision is not None:
                self.vision.close()
                self.vision = None
            self.observation = Observation.UNAVAILABLE
            self.features = None
            self.last_inferred = 0
            return ok
        except Exception as exc:
            self.logger.warning("camera_release_error %s", type(exc).__name__)
            return False

    def _resume(self, now: float, *, record: bool):
        self.suspended = False
        if now - self.resume_handled_at < 10:
            return
        self.resume_handled_at = now
        self.focus.stop()
        self.switches.reset()
        self._release_camera()
        if not self.manual_pause:
            self._open_camera()
        self.presence.after_resume(now, self.settings.power.resume_grace_seconds)
        if record:
            self.store.event("wake")

    def _activity(self, now: float):
        if now - self.last_activity_at < 1:
            return
        self.last_activity_at = now
        try:
            self.idle = activity.idle_seconds()
            self.process = activity.foreground_process()
            self.fullscreen = self.settings.pause_when_fullscreen and activity.foreground_fullscreen()
            self.protected = activity.protected_process_running(self.settings.power.skip_if_processes)
            self.switches.update(now, self.process)
        except Exception as exc:
            self.idle = None
            self.process = None
            self.protected = True
            self.logger.warning("activity_error %s", type(exc).__name__)

    def _infer(self, now: float):
        if self.camera.cap is None:
            if now >= self.camera_retry_at:
                self._open_camera()
            return
        frame, sequence, errors = self.camera.latest()
        if errors >= 10:
            self.logger.warning("camera_read_restart")
            self._release_camera()
            self.camera_retry_at = now + 1
            return
        period = 1 / (self.settings.camera.fps_active if self.presence.state == "PRESENT"
                      else self.settings.camera.fps_idle)
        if frame is None or sequence == self.last_sequence or now - self.last_inferred < period:
            return
        self.last_sequence = sequence
        self.last_inferred = now
        try:
            face, features = self.vision.infer(frame, int(now * 1000))
            self.inference_count += 1
            self.face_count += int(face)
            self.observation = Observation.FACE if face else Observation.NO_FACE
            self.features = features
        except Exception as exc:
            self.observation = Observation.UNAVAILABLE
            self.features = None
            self.logger.warning("inference_error %s", type(exc).__name__)
        finally:
            del frame
        hold = self.fullscreen or self.protected or self.idle is None
        decision = self.presence.tick(self.observation, self.idle or 0, now, hold=hold)
        if decision.warn:
            self.store.event("sleep_warn")
            notify("자리 비움 감지", "15초 뒤 절전 예정입니다. 자리에 돌아오거나 입력하면 취소됩니다.")
        if decision.sleep:
            result = self.sleep.suspend()
            self.presence.after_resume(time.monotonic(), self.settings.power.resume_grace_seconds)
            if result == "sleep":
                self._resume(time.monotonic(), record=True)
        if not self.observe_mode and not hold and decision.present and self.features:
            deviation = self.posture.evaluate(self.features, now)
            if deviation:
                self.store.event("posture_alert", deviation)
                labels = {"distance": "화면에 너무 가까운 자세", "drop": "고개가 내려간 자세",
                          "pitch": "고개를 숙인 자세", "roll": "고개가 기울어진 자세"}
                notify("자세 알림", labels[deviation] + "가 1분 이상 지속되었습니다.")
        else:
            self.posture.evaluate(None, now)

    def _sample(self, now: float):
        second = int(now)
        if second == self.last_sample_at:
            return
        self.last_sample_at = second
        fresh = now - self.last_inferred <= self.settings.camera.stale_seconds
        valid = fresh and self.observation is not Observation.UNAVAILABLE and self.idle is not None
        present = valid and self.presence.state == "PRESENT"
        facing = None
        if present and self.features and self.posture.baseline:
            base = self.posture.baseline
            facing = (abs(angle_delta(self.features.yaw, base.yaw)) <= self.settings.focus.yaw_deg_limit and
                      abs(angle_delta(self.features.pitch, base.pitch)) <= self.settings.focus.pitch_deg_limit)
        if self.settings.focus.enabled:
            self.focus.add(datetime.now(timezone.utc), Sample(valid, present, facing,
                            self.idle < 5 if self.idle is not None else None, self.process,
                            self.posture.baseline is not None))
        if self.observer:
            self.observer.record(now, datetime.now(timezone.utc), self.features if fresh else None,
                                 self.posture.baseline, self.idle or 0,
                                 len(self.switches.events), self.focus.last_score)

    def _calibrate(self):
        if self.camera.cap is None:
            notify("기준 설정", "카메라를 사용할 수 없습니다.")
            return
        self.focus.stop()
        self.presence.reset(unavailable=True)
        calibrator = Calibrator()
        notify("자세 기준 설정", "10초간 평소 자세로 화면을 보세요. 이어서 5초간 고개를 숙입니다.")
        begin = time.monotonic()
        latest = -1
        down_notified = False
        while time.monotonic() - begin < 15 and self.running:
            elapsed = time.monotonic() - begin
            if elapsed >= 10 and not down_notified:
                notify("자세 기준 설정", "지금부터 5초간 고개를 숙여 주세요.")
                down_notified = True
            frame, sequence, _ = self.camera.latest()
            if frame is not None and sequence != latest and self.vision is not None:
                latest = sequence
                try:
                    _, features = self.vision.infer(frame, int(time.monotonic() * 1000))
                    calibrator.add(features, down=elapsed >= 10)
                except Exception:
                    pass
            time.sleep(.1)
        try:
            baseline = calibrator.finish()
            save_baseline(self.baseline_path, baseline)
            self.posture.set_baseline(baseline)
            self.store.event("calibration_ok")
            notify("자세 기준 설정", "기준 자세가 저장되었습니다.")
        except (ValueError, OSError) as exc:
            self.store.event("calibration_failed")
            self.logger.warning("calibration_failed %s", type(exc).__name__)
            notify("자세 기준 설정", "얼굴 인식이나 고개 움직임이 충분하지 않아 기존 기준을 유지했습니다.")
        self.presence.after_resume(time.monotonic(), self.settings.power.resume_grace_seconds)

    def _dashboard(self):
        command = [sys.executable, "-m", "streamlit", "run", str(PROJECT / "dashboard" / "app.py"),
                   "--server.address=127.0.0.1", "--server.port=8501", "--browser.gatherUsageStats=false"]
        try:
            subprocess.Popen(command, cwd=PROJECT, creationflags=subprocess.CREATE_NO_WINDOW,
                             env={**os.environ, "DESK_GUARDIAN_CONFIG": str(self.config_path)})
            import webbrowser
            webbrowser.open("http://127.0.0.1:8501")
        except Exception as exc:
            self.logger.warning("dashboard_start_error %s", type(exc).__name__)
            notify("대시보드", "열 수 없습니다. 로그를 확인해 주세요.")

    def _commands(self, now: float):
        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                break
            if command == "exit":
                self.running = False
            elif command == "pause":
                self.manual_pause = True
                self.paused_until = now + 1800
                self._release_camera()
                self.focus.stop()
                self.presence.reset(unavailable=True)
                self.store.event("pause")
            elif command == "resume":
                self.manual_pause = False
                self.paused_until = 0
                self._open_camera()
                self.presence.after_resume(now, self.settings.power.resume_grace_seconds)
                self.store.event("unpause")
            elif command == "calibrate":
                self._calibrate()
            elif command == "dashboard":
                self._dashboard()

    def run(self):
        try:
            self.power = PowerMonitor()
        except OSError as exc:
            self.logger.warning("power_monitor_unavailable %s", type(exc).__name__)
        self._open_camera()
        self.store.event("start", "real" if self.enable_sleep else "dry_run")
        self.logger.info("started mode=%s", "real" if self.enable_sleep else "dry_run")
        try:
            while self.running:
                now = time.monotonic()
                gap = now - self.last_loop
                self.last_loop = now
                if self.power:
                    while True:
                        try:
                            event = self.power.queue.get_nowait()
                        except queue.Empty:
                            break
                        if event == "suspend":
                            self.suspended = True
                            self.focus.stop()
                        elif event == "resume":
                            self._resume(now, record=True)
                if gap >= 30:
                    self._resume(now, record=False)
                self._commands(now)
                if self.manual_pause and now >= self.paused_until:
                    self.manual_pause = False
                    self._open_camera()
                    self.presence.after_resume(now, self.settings.power.resume_grace_seconds)
                    self.store.event("unpause")
                if self.manual_pause or self.suspended:
                    self.tray.set_color("yellow", "일시정지" if self.manual_pause else "절전 대기")
                    time.sleep(.1)
                    continue
                self._activity(now)
                self._infer(now)
                if now - self.last_inferred > self.settings.camera.stale_seconds:
                    self.observation = Observation.UNAVAILABLE
                    self.features = None
                    self.presence.tick(Observation.UNAVAILABLE, self.idle or 0, now)
                self._sample(now)
                if self.observation is Observation.UNAVAILABLE or self.idle is None:
                    self.tray.set_color("red", "감지 상태 확인 필요")
                else:
                    self.tray.set_color("green", "감지 중" if self.posture.baseline else "자세 기준 설정 필요")
                time.sleep(.01)
        finally:
            self.focus.stop()
            self._release_camera()
            if self.power:
                self.power.close()
            self.store.event("exit")
            self.store.close()
            self.tray.stop()
            for handler in self.logger.handlers[:]:
                self.logger.removeHandler(handler)
                handler.close()


def main():
    parser = argparse.ArgumentParser(description="Desk Guardian (default: dry-run, no actual sleep)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="never call the Windows sleep API (default)")
    mode.add_argument("--enable-sleep", action="store_true", help="enable actual automatic sleep")
    parser.add_argument("--observe", action="store_true", help="save numerical posture metrics; disable posture alerts")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    handle = acquire()
    if handle is None:
        print("Desk Guardian is already running.", file=sys.stderr)
        return
    try:
        guardian = Guardian(args.config, enable_sleep=args.enable_sleep, observe=args.observe)
        def run_worker():
            try:
                guardian.run()
            except Exception as exc:
                # The tray must never stay green after the worker has died.
                print(f"Desk Guardian stopped: {type(exc).__name__}", file=sys.stderr)
                guardian.tray.set_color("red")
                guardian.tray.stop()

        worker = threading.Thread(target=run_worker, name="guardian-worker", daemon=True)
        worker.start()
        try:
            guardian.tray.run()
        except KeyboardInterrupt:
            guardian.commands.put("exit")
        finally:
            guardian.running = False
            worker.join(timeout=10)
    finally:
        release(handle)


if __name__ == "__main__":
    main()
