"""OpenCV live preview for webcam capture (TICKET-003)."""

from __future__ import annotations

import cv2

from sabi.capture.webcam import WebcamConfig, WebcamSource


def run_cam_preview(config: WebcamConfig | None = None) -> None:
    """Show a live window with FPS and dropped-frame overlay; press ``q`` to quit."""
    cfg = config or WebcamConfig()
    window = "Sabi cam-preview"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    with WebcamSource(cfg) as src:
        while True:
            _ts, frame_rgb = src.get_latest()
            bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            st = src.stats
            line1 = f"FPS: {st.measured_fps:.1f}  dropped: {st.dropped}"
            cv2.putText(
                bgr,
                line1,
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
    cv2.destroyWindow(window)
