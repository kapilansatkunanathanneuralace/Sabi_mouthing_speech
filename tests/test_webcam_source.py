"""TICKET-003: WebcamSource tests with a fake cv2.VideoCapture (no GUI)."""

from __future__ import annotations

import time

import numpy as np
import pytest

from sabi.capture.webcam import (
    WebcamConfig,
    WebcamSource,
    WebcamTimeoutError,
    WebcamUnavailableError,
)


class FakeVideoCapture:
    """Minimal fake used with monkeypatched ``cv2.VideoCapture``."""

    def __init__(self, opened: bool = True, fail_after_first_read: bool = False) -> None:
        self.opened = opened
        self.release_called = False
        self._read_count = 0
        self.fail_after_first_read = fail_after_first_read

    def isOpened(self) -> bool:
        return self.opened

    def set(self, *_args, **_kwargs) -> bool:
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        self._read_count += 1
        if not self.opened:
            return False, None
        if self.fail_after_first_read and self._read_count > 1:
            return False, None
        h, w = 72, 128
        bgr = np.zeros((h, w, 3), dtype=np.uint8)
        bgr[0, 0, 0] = min(255, self._read_count)
        bgr[0, 1, 1] = (self._read_count // 256) % 256
        return True, bgr

    def release(self) -> None:
        self.release_called = True


@pytest.fixture
def patch_cv_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    import sabi.capture.webcam as w

    monkeypatch.setattr(
        w.cv2,
        "VideoCapture",
        lambda *_a, **_k: FakeVideoCapture(),
    )


def test_get_latest_returns_newest(patch_cv_capture: None) -> None:
    cfg = WebcamConfig(buffer_size=8, width=128, height=72)
    with WebcamSource(cfg) as src:
        time.sleep(0.15)
        _ts, rgb = src.get_latest()
        assert rgb.shape == (72, 128, 3)
        assert rgb.dtype == np.uint8
        assert src.stats.captured >= 1


def test_ring_buffer_increments_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    import sabi.capture.webcam as w

    monkeypatch.setattr(w.cv2, "VideoCapture", lambda *_a, **_k: FakeVideoCapture())
    cfg = WebcamConfig(buffer_size=2, width=64, height=48)
    with WebcamSource(cfg) as src:
        time.sleep(0.25)
    assert src.stats.captured >= 3
    assert src.stats.dropped >= 1


def test_exit_releases_and_thread_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    import sabi.capture.webcam as w

    fake = FakeVideoCapture()

    def factory(*_a, **_k) -> FakeVideoCapture:
        return fake

    monkeypatch.setattr(w.cv2, "VideoCapture", factory)
    cfg = WebcamConfig(width=64, height=48)
    with WebcamSource(cfg):
        pass
    assert fake.release_called is True


def test_reopen_after_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import sabi.capture.webcam as w

    fakes: list[FakeVideoCapture] = []

    def factory(*_a, **_k) -> FakeVideoCapture:
        f = FakeVideoCapture()
        fakes.append(f)
        return f

    monkeypatch.setattr(w.cv2, "VideoCapture", factory)
    cfg = WebcamConfig(width=64, height=48)
    with WebcamSource(cfg):
        pass
    with WebcamSource(cfg):
        pass
    assert len(fakes) == 2
    assert all(f.release_called for f in fakes)


def test_enter_raises_when_not_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    import sabi.capture.webcam as w

    monkeypatch.setattr(
        w.cv2,
        "VideoCapture",
        lambda *_a, **_k: FakeVideoCapture(opened=False),
    )
    cfg = WebcamConfig()
    with pytest.raises(WebcamUnavailableError) as excinfo:
        with WebcamSource(cfg):
            pass
    msg = str(excinfo.value)
    assert "Privacy" in msg or "privacy" in msg
    assert "Camera" in msg or "camera" in msg


def test_get_latest_timeout_when_capture_stalls(monkeypatch: pytest.MonkeyPatch) -> None:
    import sabi.capture.webcam as w

    monkeypatch.setattr(
        w.cv2,
        "VideoCapture",
        lambda *_a, **_k: FakeVideoCapture(fail_after_first_read=True),
    )
    cfg = WebcamConfig(width=64, height=48)
    with WebcamSource(cfg) as src:
        with pytest.raises(WebcamTimeoutError):
            src.get_latest(timeout=0.15)


def test_frames_skips_to_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    import sabi.capture.webcam as w

    monkeypatch.setattr(w.cv2, "VideoCapture", lambda *_a, **_k: FakeVideoCapture())
    cfg = WebcamConfig(buffer_size=4, width=64, height=48)
    with WebcamSource(cfg) as src:
        gen = iter(src.frames())
        ts1, _fr1 = next(gen)
        time.sleep(0.05)
        ts2, _fr2 = next(gen)
        assert ts2 > ts1
