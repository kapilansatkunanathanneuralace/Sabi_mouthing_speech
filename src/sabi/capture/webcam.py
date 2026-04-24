"""Threaded webcam capture with ring buffer (TICKET-003)."""

from __future__ import annotations

import sys
import threading
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

import cv2
import numpy as np
from pydantic import BaseModel, Field


def _webcam_remediation_text() -> str:
    return (
        "Remediation: Windows Settings > Privacy & security > Camera - "
        "allow desktop apps. Close other apps using the camera. "
        "Try a different USB port or camera index."
    )


class WebcamUnavailableError(RuntimeError):
    """Raised when the camera cannot be opened or the first frame read fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class WebcamTimeoutError(TimeoutError):
    """Raised when ``get_latest`` waits longer than ``timeout`` without a frame."""


@dataclass(frozen=True)
class FrameStats:
    captured: int
    dropped: int
    last_timestamp_ns: int
    measured_fps: float


class WebcamConfig(BaseModel):
    device_index: int = Field(default=0, ge=0)
    target_fps: float = Field(default=25.0, gt=0)
    width: int = Field(default=1280, ge=1)
    height: int = Field(default=720, ge=1)
    mirror: bool = False
    buffer_size: int = Field(default=4, ge=1)
    backend: int | None = Field(
        default=None,
        description="OpenCV backend (e.g. cv2.CAP_DSHOW). None uses DSHOW on Windows only.",
    )


def _default_capture_backend(config: WebcamConfig) -> int | None:
    if config.backend is not None:
        return config.backend
    if sys.platform == "win32":
        return cv2.CAP_DSHOW
    return None


class WebcamSource:
    """Background thread reads BGR from OpenCV, stores RGB in a bounded deque."""

    _JOIN_TIMEOUT_S = 2.0

    def __init__(self, config: WebcamConfig) -> None:
        self._config = config
        self._cap: cv2.VideoCapture | None = None
        self._deque: deque[tuple[int, np.ndarray]] = deque(maxlen=config.buffer_size)
        self._deque_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._captured = 0
        self._dropped = 0
        self._last_timestamp_ns = 0
        self._measured_fps = 0.0
        self._fps_times_mono: deque[float] = deque(maxlen=120)
        self._running = False
        self._thread: threading.Thread | None = None
        self._deque_cv = threading.Condition(self._deque_lock)
        self._entered = False

    def _open_capture(self) -> cv2.VideoCapture:
        backend = _default_capture_backend(self._config)
        if backend is not None:
            cap = cv2.VideoCapture(self._config.device_index, backend)
        else:
            cap = cv2.VideoCapture(self._config.device_index)
        if not cap.isOpened():
            cap.release()
            raise WebcamUnavailableError(
                "Webcam: FAILED to open device.\n" + _webcam_remediation_text(),
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._config.width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._config.height))
        cap.set(cv2.CAP_PROP_FPS, float(self._config.target_fps))
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # noqa: BLE001 - property may be unsupported
            pass
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            raise WebcamUnavailableError(
                "Webcam: opened but failed to read a frame.\n"
                "Remediation: same as above; check drivers and privacy.",
            )
        return cap

    def _update_fps_ewma(self, now_mono: float) -> None:
        self._fps_times_mono.append(now_mono)
        while len(self._fps_times_mono) >= 2 and (now_mono - self._fps_times_mono[0]) > 2.0:
            self._fps_times_mono.popleft()
        if len(self._fps_times_mono) < 2:
            self._measured_fps = 0.0
            return
        span = self._fps_times_mono[-1] - self._fps_times_mono[0]
        if span <= 0:
            self._measured_fps = 0.0
            return
        self._measured_fps = (len(self._fps_times_mono) - 1) / span

    def _capture_loop(self) -> None:
        assert self._cap is not None
        while self._running:
            ok, bgr = self._cap.read()
            if not ok or bgr is None:
                time.sleep(0.01)
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            if self._config.mirror:
                rgb = cv2.flip(rgb, 1)
            if not rgb.flags["C_CONTIGUOUS"]:
                rgb = np.ascontiguousarray(rgb)
            ts_ns = time.time_ns()
            now_mono = time.monotonic()
            with self._deque_cv:
                will_drop = len(self._deque) == self._deque.maxlen
                self._deque.append((ts_ns, rgb))
                self._deque_cv.notify_all()
            with self._stats_lock:
                self._captured += 1
                if will_drop:
                    self._dropped += 1
                self._last_timestamp_ns = ts_ns
                self._update_fps_ewma(now_mono)

    @property
    def stats(self) -> FrameStats:
        with self._stats_lock:
            return FrameStats(
                captured=self._captured,
                dropped=self._dropped,
                last_timestamp_ns=self._last_timestamp_ns,
                measured_fps=self._measured_fps,
            )

    def get_latest(self, timeout: float | None = None) -> tuple[int, np.ndarray]:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._deque_cv:
                if self._deque:
                    return self._deque[-1]
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WebcamTimeoutError(
                            "No frame arrived within the requested timeout.",
                        )
                    self._deque_cv.wait(timeout=min(0.05, remaining))
                else:
                    self._deque_cv.wait(timeout=0.05)

    def frames(self) -> Iterator[tuple[int, np.ndarray]]:
        last_ts = -1
        while self._running:
            with self._deque_cv:
                while self._running and (not self._deque or self._deque[-1][0] <= last_ts):
                    self._deque_cv.wait(timeout=0.5)
                if not self._running or not self._deque:
                    continue
                ts, frame = self._deque[-1]
            last_ts = ts
            yield (ts, frame)

    def __enter__(self) -> WebcamSource:
        if self._entered:
            raise RuntimeError("WebcamSource context is not re-entrant.")
        self._entered = True
        self._cap = self._open_capture()
        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="WebcamCapture",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self._running = False
        with self._deque_cv:
            self._deque_cv.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=self._JOIN_TIMEOUT_S)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._entered = False
        with self._deque_cv:
            self._deque.clear()
