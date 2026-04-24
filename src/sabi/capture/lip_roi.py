"""Lip / mouth ROI detector on top of MediaPipe Face Mesh topology (TICKET-004).

Emits 96x96 uint8 grayscale mouth crops aligned to the Auto-AVSR / LRS3 training
distribution so downstream VSR models see crops similar to their training data.
This module deliberately stops **before** Auto-AVSR's mean/std normalization;
normalization is the responsibility of the VSR wrapper (TICKET-005) so there is
a single entry point for that concern.

Implementation note: TICKET-004 calls for ``mediapipe.solutions.face_mesh.FaceMesh``.
On Python 3.14 / mediapipe 0.10.33 that legacy namespace is not shipped, so this
module uses the equivalent ``mediapipe.tasks.vision.FaceLandmarker`` (same Face
Mesh landmark topology, same 478 indices with ``refine_landmarks=True``). The
``face_landmarker.task`` asset is downloaded once into the user cache on first
use and reused afterwards.
"""

from __future__ import annotations

import logging
import math
import os
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Face Mesh topology lip landmark indices (see TICKET-004).
OUTER_LIP_INDICES: tuple[int, ...] = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291)
INNER_LIP_INDICES: tuple[int, ...] = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308)
ALL_LIP_INDICES: tuple[int, ...] = tuple(sorted(set(OUTER_LIP_INDICES + INNER_LIP_INDICES)))

# Outer lip corners used to define the mouth midline for rotation alignment.
LEFT_MOUTH_CORNER = 61
RIGHT_MOUTH_CORNER = 291

DEFAULT_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def _default_model_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "sabi" / "models" / "face_landmarker.task"


def _ensure_model(path: Path, url: str = DEFAULT_MODEL_URL) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading face_landmarker model to %s", path)
    urllib.request.urlretrieve(url, str(path))
    return path


class LipROIConfig(BaseModel):
    target_size: int = Field(default=96, ge=1)
    target_fps: float = Field(default=25.0, gt=0)
    smooth_alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    grayscale: bool = True
    max_missing_streak: int = Field(default=15, ge=1)
    expand_ratio: float = Field(default=0.4, ge=0.0)
    min_detection_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    min_presence_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    min_tracking_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    model_path: Path | None = None


@dataclass(frozen=True)
class LipFrame:
    timestamp_ns: int
    crop: np.ndarray
    confidence: float
    face_present: bool
    bbox: tuple[float, float, float, float]
    """Smoothed bbox on the source frame: ``(cx, cy, side, angle_deg)``."""


class LipROIDetector:
    """Wraps MediaPipe FaceLandmarker; returns aligned 96x96 mouth crops."""

    def __init__(self, config: LipROIConfig | None = None) -> None:
        self._config = config or LipROIConfig()
        self._landmarker: FaceLandmarker | None = None
        self._smoothed: tuple[float, float, float, float] | None = None
        self._missing_streak = 0
        self._warned_missing = False

    @property
    def config(self) -> LipROIConfig:
        return self._config

    @property
    def last_bbox(self) -> tuple[float, float, float, float] | None:
        """Smoothed ``(cx, cy, side, angle_deg)`` from the last detected frame."""
        return self._smoothed

    def _ensure_landmarker(self) -> FaceLandmarker:
        if self._landmarker is None:
            model_path = self._config.model_path or _default_model_path()
            _ensure_model(model_path)
            options = FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=self._config.min_detection_confidence,
                min_face_presence_confidence=self._config.min_presence_confidence,
                min_tracking_confidence=self._config.min_tracking_confidence,
                output_face_blendshapes=False,
            )
            self._landmarker = FaceLandmarker.create_from_options(options)
        return self._landmarker

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None

    def __enter__(self) -> LipROIDetector:
        self._ensure_landmarker()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def _detect_landmarks(self, frame_rgb: np.ndarray) -> list | None:
        landmarker = self._ensure_landmarker()
        rgb = np.ascontiguousarray(frame_rgb, dtype=np.uint8)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect(mp_image)
        if not result.face_landmarks:
            return None
        return result.face_landmarks[0]

    def _compute_raw_bbox(
        self,
        landmarks: list,
        frame_w: int,
        frame_h: int,
    ) -> tuple[float, float, float, float]:
        """Return ``(cx, cy, side, angle_deg)`` for the mouth region in pixel space."""
        lip_pts = np.array(
            [(landmarks[i].x * frame_w, landmarks[i].y * frame_h) for i in ALL_LIP_INDICES],
            dtype=np.float64,
        )
        lx = landmarks[LEFT_MOUTH_CORNER].x * frame_w
        ly = landmarks[LEFT_MOUTH_CORNER].y * frame_h
        rx = landmarks[RIGHT_MOUTH_CORNER].x * frame_w
        ry = landmarks[RIGHT_MOUTH_CORNER].y * frame_h
        cx = (lx + rx) / 2.0
        cy = (ly + ry) / 2.0
        angle_deg = math.degrees(math.atan2(ry - ly, rx - lx))

        # Rotate lip points into the mouth-aligned frame, then take the tight
        # axis-aligned bbox there so rotation doesn't inflate the crop.
        theta = math.radians(-angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        rel = lip_pts - np.array([cx, cy])
        rot = np.stack(
            [
                rel[:, 0] * cos_t - rel[:, 1] * sin_t,
                rel[:, 0] * sin_t + rel[:, 1] * cos_t,
            ],
            axis=1,
        )
        xmin, ymin = rot.min(axis=0)
        xmax, ymax = rot.max(axis=0)
        bw = (xmax - xmin) * (1.0 + 2.0 * self._config.expand_ratio)
        bh = (ymax - ymin) * (1.0 + 2.0 * self._config.expand_ratio)
        side = float(max(bw, bh, 1.0))
        return float(cx), float(cy), side, float(angle_deg)

    def _smooth(
        self,
        raw: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        alpha = self._config.smooth_alpha
        if self._smoothed is None or alpha <= 0.0:
            self._smoothed = raw
            return raw
        prev_cx, prev_cy, prev_side, prev_angle = self._smoothed
        raw_cx, raw_cy, raw_side, raw_angle = raw
        # Unwrap angle so EWMA doesn't ping-pong across the +/-180 degree seam.
        delta = ((raw_angle - prev_angle + 180.0) % 360.0) - 180.0
        raw_angle_unwrapped = prev_angle + delta
        smoothed = (
            alpha * prev_cx + (1.0 - alpha) * raw_cx,
            alpha * prev_cy + (1.0 - alpha) * raw_cy,
            alpha * prev_side + (1.0 - alpha) * raw_side,
            alpha * prev_angle + (1.0 - alpha) * raw_angle_unwrapped,
        )
        self._smoothed = smoothed
        return smoothed

    def _warp_crop(
        self,
        frame_rgb: np.ndarray,
        bbox: tuple[float, float, float, float],
    ) -> np.ndarray:
        target = self._config.target_size
        cx, cy, side, angle_deg = bbox
        scale = target / side
        M = cv2.getRotationMatrix2D((cx, cy), angle_deg, scale)
        # getRotationMatrix2D rotates around (cx, cy) and keeps that point fixed;
        # translate so (cx, cy) maps to the crop center.
        M[0, 2] += target / 2.0 - cx
        M[1, 2] += target / 2.0 - cy
        crop = cv2.warpAffine(
            frame_rgb,
            M,
            (target, target),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        if self._config.grayscale:
            crop = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        if crop.dtype != np.uint8:
            crop = crop.astype(np.uint8, copy=False)
        return np.ascontiguousarray(crop)

    def _confidence(self, landmarks: list) -> float:
        vis: list[float] = []
        for i in ALL_LIP_INDICES:
            v = getattr(landmarks[i], "visibility", None)
            if v is not None and not math.isclose(v, 0.0):
                vis.append(float(v))
        if not vis:
            return 1.0
        return float(np.mean(vis))

    def process_frame(
        self,
        timestamp_ns: int,
        frame_rgb: np.ndarray,
    ) -> LipFrame | None:
        """Detect the mouth ROI in ``frame_rgb``; return ``None`` when no face."""
        if frame_rgb.ndim != 3 or frame_rgb.shape[2] != 3:
            raise ValueError("frame_rgb must be an HxWx3 RGB array")
        landmarks = self._detect_landmarks(frame_rgb)
        if landmarks is None:
            return None
        h, w = frame_rgb.shape[:2]
        raw_bbox = self._compute_raw_bbox(landmarks, w, h)
        bbox = self._smooth(raw_bbox)
        crop = self._warp_crop(frame_rgb, bbox)
        return LipFrame(
            timestamp_ns=timestamp_ns,
            crop=crop,
            confidence=self._confidence(landmarks),
            face_present=True,
            bbox=bbox,
        )

    def process_stream(
        self,
        frames: Iterator[tuple[int, np.ndarray]],
    ) -> Iterator[LipFrame | None]:
        """Adapter over a ``(timestamp_ns, frame_rgb)`` iterator.

        Yields a :class:`LipFrame` on every frame with a detected face. When the
        face goes missing for more than ``max_missing_streak`` frames in a row,
        yields a single ``None`` sentinel and logs a warning; intermediate
        missing frames are skipped. Yielding resumes once a face returns.
        """
        for ts, frame in frames:
            result = self.process_frame(ts, frame)
            if result is not None:
                self._missing_streak = 0
                self._warned_missing = False
                yield result
                continue
            self._missing_streak += 1
            if self._missing_streak >= self._config.max_missing_streak and not self._warned_missing:
                logger.warning("camera no longer sees a face")
                self._warned_missing = True
                yield None
