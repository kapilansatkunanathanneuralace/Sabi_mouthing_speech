"""Live lip ROI preview (TICKET-004).

Overlays the smoothed mouth bbox on the raw webcam frame and pastes a zoomed
copy of the 96x96 crop in the top-right corner. Press ``q`` to quit, ``s`` to
save the last good crop to ``data/samples/lip_sample.png``.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from sabi.capture.lip_roi import LipROIConfig, LipROIDetector
from sabi.capture.webcam import WebcamConfig, WebcamSource

SAMPLE_OUT_PATH = Path("data/samples/lip_sample.png")


def _draw_bbox(
    bgr: np.ndarray,
    bbox: tuple[float, float, float, float],
    color: tuple[int, int, int] = (0, 255, 0),
) -> None:
    cx, cy, side, angle_deg = bbox
    half = side / 2.0
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    pts = []
    for dx, dy in corners:
        x = cx + dx * cos_t - dy * sin_t
        y = cy + dx * sin_t + dy * cos_t
        pts.append([int(round(x)), int(round(y))])
    cv2.polylines(bgr, [np.array(pts, dtype=np.int32)], True, color, 2, cv2.LINE_AA)


def _paste_crop(bgr: np.ndarray, crop: np.ndarray, scale: int = 3) -> None:
    display = cv2.resize(
        crop,
        (crop.shape[1] * scale, crop.shape[0] * scale),
        interpolation=cv2.INTER_NEAREST,
    )
    if display.ndim == 2:
        display = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
    h, w = display.shape[:2]
    margin = 12
    y0 = margin
    x0 = bgr.shape[1] - w - margin
    bgr[y0 : y0 + h, x0 : x0 + w] = display
    cv2.rectangle(bgr, (x0 - 1, y0 - 1), (x0 + w, y0 + h), (200, 200, 200), 1)


def run_lip_preview(
    webcam: WebcamConfig | None = None,
    lip: LipROIConfig | None = None,
) -> None:
    wcfg = webcam or WebcamConfig()
    lcfg = lip or LipROIConfig()
    window = "Sabi lip-preview"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    last_crop: np.ndarray | None = None
    with WebcamSource(wcfg) as src, LipROIDetector(lcfg) as detector:
        while True:
            ts, frame_rgb = src.get_latest()
            bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            result = detector.process_frame(ts, frame_rgb)
            st = src.stats
            if result is not None:
                _draw_bbox(bgr, result.bbox)
                _paste_crop(bgr, result.crop)
                last_crop = result.crop
                status = f"FPS: {st.measured_fps:.1f}  dropped: {st.dropped}  face: yes"
            else:
                status = f"FPS: {st.measured_fps:.1f}  dropped: {st.dropped}  face: NO"
            cv2.putText(
                bgr,
                status,
                (8, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(window, bgr)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s") and last_crop is not None:
                SAMPLE_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(SAMPLE_OUT_PATH), last_crop)
    cv2.destroyWindow(window)
