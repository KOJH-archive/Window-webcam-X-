"""Owns exactly one camera handle and keeps only the latest frame in RAM."""
from __future__ import annotations

import threading
import time

import cv2

from .config import CameraConfig


class Camera:
    def __init__(self, config: CameraConfig):
        self.config = config
        self.cap = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.latest_frame = None
        self.latest_time = 0.0
        self.sequence = 0
        self.consecutive_errors = 0

    def open(self) -> bool:
        if self.cap is not None:
            return True
        backend = cv2.CAP_DSHOW if self.config.backend == "DSHOW" else cv2.CAP_MSMF
        cap = cv2.VideoCapture(self.config.index, backend)
        if not cap.isOpened():
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.cap = cap
        self.stop.clear()
        self.thread = threading.Thread(target=self._read_loop, daemon=True, name="guardian-camera")
        self.thread.start()
        return True

    def _read_loop(self):
        while not self.stop.is_set():
            try:
                ok, frame = self.cap.read()
                with self.lock:
                    if ok:
                        self.latest_frame = frame
                        self.latest_time = time.monotonic()
                        self.sequence += 1
                        self.consecutive_errors = 0
                    else:
                        self.consecutive_errors += 1
                if not ok:
                    time.sleep(0.1)
            except Exception:
                with self.lock:
                    self.consecutive_errors += 1
                time.sleep(0.1)

    def latest(self):
        with self.lock:
            if self.latest_frame is None or time.monotonic() - self.latest_time > self.config.stale_seconds:
                return None, self.sequence, self.consecutive_errors
            return self.latest_frame, self.sequence, self.consecutive_errors

    def close(self) -> bool:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                return False
        if self.cap is not None:
            self.cap.release()
        self.cap = None
        self.thread = None
        with self.lock:
            self.latest_frame = None
            self.latest_time = 0.0
            self.sequence = 0
            self.consecutive_errors = 0
        return True
