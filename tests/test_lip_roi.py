"""TICKET-004: LipROIDetector geometry and stream tests (no GUI, no real model).

Tests monkeypatch the MediaPipe detection step with synthetic Face Mesh
landmarks so the pipeline (bbox + 40% expand + rotation alignment + EWMA +
crop) is validated hermetically - no webcam, no model download, no binary
fixtures on disk. The downstream model-accuracy check lives in TICKET-014's
eval harness, not here.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Iterable

import numpy as np
import pytest

from sabi.capture.lip_roi import (
    ALL_LIP_INDICES,
    LEFT_MOUTH_CORNER,
    RIGHT_MOUTH_CORNER,
    LipROIConfig,
    LipROIDetector,
)


def _synth_face_landmarks(
    frame_w: int,
    frame_h: int,
    mouth_cx: float,
    mouth_cy: float,
    mouth_w: float,
    mouth_h: float,
    angle_deg: float = 0.0,
) -> list[SimpleNamespace]:
    """Build a list of 478 landmarks with realistic lip positions in pixel -> normalized space."""
    # Landmarks outside the lip set can stay at (0, 0) - detector ignores them.
    landmarks = [SimpleNamespace(x=0.0, y=0.0, z=0.0, visibility=0.0) for _ in range(478)]

    theta = np.radians(angle_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)

    def place(idx: int, dx: float, dy: float, visibility: float = 1.0) -> None:
        # Rotate (dx, dy) by angle_deg and translate to mouth center.
        x = mouth_cx + dx * cos_t - dy * sin_t
        y = mouth_cy + dx * sin_t + dy * cos_t
        landmarks[idx] = SimpleNamespace(
            x=x / frame_w,
            y=y / frame_h,
            z=0.0,
            visibility=visibility,
        )

    half_w = mouth_w / 2.0
    half_h = mouth_h / 2.0
    place(LEFT_MOUTH_CORNER, -half_w, 0.0)
    place(RIGHT_MOUTH_CORNER, +half_w, 0.0)
    # Spread the remaining lip landmarks around the mouth rectangle so the tight
    # bbox has roughly the expected size.
    others = [i for i in ALL_LIP_INDICES if i not in {LEFT_MOUTH_CORNER, RIGHT_MOUTH_CORNER}]
    for i, idx in enumerate(others):
        t = (i + 1) / (len(others) + 1)
        dx = -half_w + t * mouth_w
        dy = half_h if i % 2 == 0 else -half_h
        place(idx, dx, dy)
    return landmarks


def _install_fake_detect(
    detector: LipROIDetector,
    monkeypatch: pytest.MonkeyPatch,
    landmarks_or_none: Iterable[list | None],
) -> None:
    """Patch ``_detect_landmarks`` to yield a fixed sequence of results."""
    it = iter(landmarks_or_none)

    def fake_detect(_self, _frame_rgb):  # noqa: ANN001
        return next(it, None)

    monkeypatch.setattr(
        "sabi.capture.lip_roi.LipROIDetector._detect_landmarks",
        fake_detect,
    )


def test_crop_is_96x96_uint8_contiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = np.full((240, 320, 3), 128, dtype=np.uint8)
    landmarks = _synth_face_landmarks(
        frame_w=320,
        frame_h=240,
        mouth_cx=160.0,
        mouth_cy=180.0,
        mouth_w=80.0,
        mouth_h=30.0,
    )
    detector = LipROIDetector(LipROIConfig(smooth_alpha=0.0))
    _install_fake_detect(detector, monkeypatch, [landmarks])
    result = detector.process_frame(1, frame)
    assert result is not None
    assert result.face_present is True
    assert result.crop.shape == (96, 96)
    assert result.crop.dtype == np.uint8
    assert result.crop.flags["C_CONTIGUOUS"]
    cx, cy, side, _angle = result.bbox
    assert abs(cx - 160.0) < 1e-6
    assert abs(cy - 180.0) < 1e-6
    expected_side = 80.0 * (1.0 + 2.0 * detector.config.expand_ratio)
    assert side == pytest.approx(expected_side, rel=0.01)


def test_grayscale_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = np.full((240, 320, 3), 200, dtype=np.uint8)
    landmarks = _synth_face_landmarks(320, 240, 160.0, 180.0, 80.0, 30.0)
    detector = LipROIDetector(LipROIConfig(grayscale=False, smooth_alpha=0.0))
    _install_fake_detect(detector, monkeypatch, [landmarks])
    result = detector.process_frame(1, frame)
    assert result is not None
    assert result.crop.shape == (96, 96, 3)


def test_missing_face_emits_single_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    detector = LipROIDetector(LipROIConfig(max_missing_streak=3))
    # Fake detect returns ``None`` (no face) forever.
    monkeypatch.setattr(
        "sabi.capture.lip_roi.LipROIDetector._detect_landmarks",
        lambda _self, _frame: None,
    )
    frames = iter((i, np.zeros((240, 320, 3), dtype=np.uint8)) for i in range(8))
    with caplog.at_level(logging.WARNING, logger="sabi.capture.lip_roi"):
        yielded = list(detector.process_stream(frames))
    assert yielded == [None]
    assert any("no longer sees a face" in rec.message for rec in caplog.records)


def test_missing_face_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    detector = LipROIDetector(LipROIConfig(max_missing_streak=2, smooth_alpha=0.0))
    face = _synth_face_landmarks(320, 240, 160.0, 180.0, 80.0, 30.0)
    script = [face, None, None, None, face, face]
    _install_fake_detect(detector, monkeypatch, script)
    frames = iter((i, np.zeros((240, 320, 3), dtype=np.uint8)) for i in range(len(script)))
    yielded = list(detector.process_stream(frames))
    # 1 face frame, then 1 None sentinel after streak hits threshold (2 misses),
    # then two more face frames after recovery. The third miss in a row does
    # not emit another None; the warning flag resets once a face returns.
    assert len(yielded) == 4
    assert yielded[0] is not None and yielded[0].face_present
    assert yielded[1] is None
    assert yielded[2] is not None and yielded[2].face_present
    assert yielded[3] is not None and yielded[3].face_present


def test_smoothing_reduces_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoothing should cut the std-dev of bbox center by at least 50%."""
    rng = np.random.default_rng(seed=1234)
    jitter_px = 6.0
    n = 120
    base_cx, base_cy = 320.0, 240.0
    frame_shape = (480, 640, 3)

    def make_detector(alpha: float) -> LipROIDetector:
        return LipROIDetector(LipROIConfig(smooth_alpha=alpha))

    def run(alpha: float) -> np.ndarray:
        detector = make_detector(alpha)
        centers: list[tuple[float, float]] = []
        landmarks_seq: list[list] = []
        for _ in range(n):
            noise_x = rng.normal(0.0, jitter_px)
            noise_y = rng.normal(0.0, jitter_px)
            landmarks_seq.append(
                _synth_face_landmarks(
                    frame_shape[1],
                    frame_shape[0],
                    base_cx + noise_x,
                    base_cy + noise_y,
                    80.0,
                    30.0,
                )
            )
        _install_fake_detect(detector, monkeypatch, landmarks_seq)
        frame = np.zeros(frame_shape, dtype=np.uint8)
        for i in range(n):
            result = detector.process_frame(i, frame)
            assert result is not None
            cx, cy, _side, _angle = result.bbox
            centers.append((cx, cy))
        return np.array(centers)

    raw = run(alpha=0.0)
    # Fresh random state for smoothed run so jitter distribution matches.
    rng = np.random.default_rng(seed=1234)
    smoothed = run(alpha=0.85)
    raw_std = float(np.linalg.norm(raw.std(axis=0)))
    smoothed_std = float(np.linalg.norm(smoothed.std(axis=0)))
    assert smoothed_std <= 0.5 * raw_std, (
        f"expected smoothed std <= 50% of raw, got raw={raw_std:.2f} "
        f"smoothed={smoothed_std:.2f}"
    )
