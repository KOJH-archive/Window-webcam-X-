"""Face Landmarker adapter; never retains a raw frame after inference."""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np


@dataclass(frozen=True)
class Features:
    face_size: float
    face_cy: float
    pitch: float
    yaw: float
    roll: float


# Approximate 3D head coordinates in millimetres, with 2D points in the same order.
# This pose is only interpreted relative to a user-calibrated baseline.
LANDMARKS = (1, 152, 33, 263, 61, 291)
MODEL_POINTS = np.array([(0, 0, 0), (0, -63, -12), (-43, 32, -26),
                         (43, 32, -26), (-28, -28, -20), (28, -28, -20)], dtype=np.float64)


class FaceVision:
    def __init__(self, model_path: Path, confidence: float):
        self.model_bytes = Path(model_path).read_bytes()
        opts = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_buffer=self.model_bytes),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1, min_face_detection_confidence=confidence,
            min_face_presence_confidence=confidence, min_tracking_confidence=confidence,
            output_face_blendshapes=False, output_facial_transformation_matrixes=False)
        self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(opts)
        self.last_timestamp_ms = -1

    def close(self):
        self.landmarker.close()

    def infer(self, frame, timestamp_ms: int) -> tuple[bool, Features | None]:
        # MediaPipe VIDEO mode requires strictly increasing frame timestamps.
        timestamp_ms = max(timestamp_ms, self.last_timestamp_ms + 1)
        self.last_timestamp_ms = timestamp_ms
        height, width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
        if not result.face_landmarks:
            return False, None
        points = result.face_landmarks[0]
        image_points = np.array([(points[i].x * width, points[i].y * height) for i in LANDMARKS], dtype=np.float64)
        intrinsics = np.array([[width, 0, width / 2], [0, width, height / 2], [0, 0, 1]], dtype=np.float64)
        ok, rotation_vec, translation_vec = cv2.solvePnP(MODEL_POINTS, image_points, intrinsics,
                                                            np.zeros((4, 1)), flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            return True, None
        rotation, _ = cv2.Rodrigues(rotation_vec)
        pitch, yaw, roll = cv2.RQDecomp3x3(rotation)[0]
        face_size = math.dist((points[33].x * width, points[33].y * height),
                              (points[263].x * width, points[263].y * height))
        values = (face_size, points[1].y, pitch, yaw, roll)
        if not all(math.isfinite(value) for value in values) or face_size < 1:
            return True, None
        return True, Features(*values)
