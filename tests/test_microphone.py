"""TICKET-006: MicrophoneSource tests with a monkeypatched sounddevice stream."""

from __future__ import annotations

import sys
import threading
import time
import types

import numpy as np
import pytest

from sabi.capture.microphone import (
    MicConfig,
    MicrophoneSource,
    MicUnavailableError,
    Utterance,
    _VadBackend,
)


class _ScriptedVad(_VadBackend):
    """Deterministic VAD: returns scripted speech flags in order, then final."""

    name = "scripted"

    def __init__(self, flags: list[bool], default: bool = False) -> None:
        self._flags = list(flags)
        self._i = 0
        self._default = default
        self.calls = 0

    def is_speech(self, frame_int16: np.ndarray, sample_rate: int) -> bool:
        self.calls += 1
        if self._i < len(self._flags):
            v = self._flags[self._i]
            self._i += 1
            return v
        return self._default


class _FakeRawInputStream:
    """Drop-in fake for :class:`sounddevice.RawInputStream`.

    Test code drives the stream by calling :meth:`feed` with 20 ms int16
    frames. No real thread runs in the background.
    """

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.blocksize = int(kwargs["blocksize"])  # type: ignore[arg-type]
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def feed(self, frame_int16: np.ndarray) -> None:
        assert self.started and not self.closed, "stream must be started"
        payload = frame_int16.astype(np.int16).tobytes()
        self.callback(payload, self.blocksize, None, None)


@pytest.fixture
def fake_stream(monkeypatch: pytest.MonkeyPatch) -> list[_FakeRawInputStream]:
    from sabi.capture import microphone as m

    created: list[_FakeRawInputStream] = []

    def factory(**kwargs: object) -> _FakeRawInputStream:
        inst = _FakeRawInputStream(**kwargs)
        created.append(inst)
        return inst

    monkeypatch.setattr(m.sd, "RawInputStream", factory)
    monkeypatch.setattr(m.sd, "check_input_settings", lambda **_kw: None)
    return created


def _zeros_frame(n: int) -> np.ndarray:
    return np.zeros(n, dtype=np.int16)


def _loud_frame(n: int, amp: int = 8000) -> np.ndarray:
    t = np.linspace(0, 1, n, endpoint=False, dtype=np.float32)
    sine = np.sin(2 * np.pi * 220.0 * t) * amp
    return sine.astype(np.int16)


def _drain_utterances(
    src: MicrophoneSource,
    expected: int,
    timeout_s: float = 2.0,
) -> list[Utterance]:
    out: list[Utterance] = []
    deadline = time.monotonic() + timeout_s
    while len(out) < expected and time.monotonic() < deadline:
        u = src.next_utterance(timeout=0.05)
        if u is not None:
            out.append(u)
    return out


def test_emits_single_utterance_from_silence_speech_silence(
    fake_stream: list[_FakeRawInputStream],
) -> None:
    cfg = MicConfig(
        sample_rate=16000,
        frame_ms=20,
        min_utterance_ms=40,
        max_utterance_ms=2000,
        trailing_silence_ms=100,
    )
    flags = [False] * 5 + [True] * 10 + [False] * 10
    vad = _ScriptedVad(flags, default=False)

    with MicrophoneSource(cfg, vad_backend=vad) as src:
        stream = fake_stream[0]
        quiet = _zeros_frame(320)
        loud = _loud_frame(320)
        for is_speech in flags:
            stream.feed(loud if is_speech else quiet)
            time.sleep(0.002)
        utts = _drain_utterances(src, expected=1)

    assert len(utts) == 1, f"expected one utterance, got {len(utts)}"
    u = utts[0]
    # 10 speech frames + 5 trailing silence frames that pushed the gate closed
    assert u.samples.dtype == np.float32
    assert u.samples.ndim == 1
    assert u.sample_rate == 16000
    assert u.samples.shape[0] == 15 * 320
    assert 0.0 < u.vad_coverage <= 1.0
    assert u.peak_dbfs <= 0.0


def test_max_utterance_ms_forces_emit(
    fake_stream: list[_FakeRawInputStream],
) -> None:
    cfg = MicConfig(
        sample_rate=16000,
        frame_ms=20,
        min_utterance_ms=20,
        max_utterance_ms=100,
        trailing_silence_ms=100,
    )
    # Always-speech VAD
    vad = _ScriptedVad([], default=True)

    with MicrophoneSource(cfg, vad_backend=vad) as src:
        stream = fake_stream[0]
        loud = _loud_frame(320)
        for _ in range(10):
            stream.feed(loud)
            time.sleep(0.002)
        utts = _drain_utterances(src, expected=1)

    assert len(utts) >= 1
    # Forced emit must cap at max_utterance_ms == 5 frames at 20ms
    assert utts[0].samples.shape[0] == 5 * 320
    assert utts[0].vad_coverage == pytest.approx(1.0)


def test_min_utterance_ms_drops_short_blip(
    fake_stream: list[_FakeRawInputStream],
) -> None:
    cfg = MicConfig(
        sample_rate=16000,
        frame_ms=20,
        min_utterance_ms=200,
        max_utterance_ms=2000,
        trailing_silence_ms=60,
    )
    # 2 speech frames (40 ms) then silence: below min_utterance_ms floor.
    flags = [False] * 3 + [True] * 2 + [False] * 8
    vad = _ScriptedVad(flags, default=False)

    with MicrophoneSource(cfg, vad_backend=vad) as src:
        stream = fake_stream[0]
        quiet = _zeros_frame(320)
        loud = _loud_frame(320)
        for is_speech in flags:
            stream.feed(loud if is_speech else quiet)
            time.sleep(0.002)
        # Wait a moment to ensure the state machine closes the segment.
        u = src.next_utterance(timeout=0.3)
    assert u is None, "short blip should be discarded below min_utterance_ms"


def test_push_to_talk_records_between_events(
    fake_stream: list[_FakeRawInputStream],
) -> None:
    cfg = MicConfig(
        sample_rate=16000,
        frame_ms=20,
        min_utterance_ms=20,
        max_utterance_ms=2000,
        trailing_silence_ms=100,
    )
    vad = _ScriptedVad([], default=True)

    with MicrophoneSource(cfg, vad_backend=vad) as src:
        stream = fake_stream[0]
        loud = _loud_frame(320)
        start_ev = threading.Event()
        end_ev = threading.Event()
        result: dict[str, Utterance] = {}

        def runner() -> None:
            result["utt"] = src.push_to_talk_segment(start_ev, end_ev)

        t = threading.Thread(target=runner)
        t.start()

        start_ev.set()
        time.sleep(0.02)
        for _ in range(6):
            stream.feed(loud)
            time.sleep(0.005)
        end_ev.set()
        t.join(timeout=2.0)
    assert "utt" in result, "push_to_talk_segment never returned"
    u = result["utt"]
    assert u.samples.dtype == np.float32
    assert u.samples.shape[0] >= 3 * 320  # accept some scheduling slack
    assert u.end_ts_ns >= u.start_ts_ns
    assert u.vad_coverage == pytest.approx(1.0)


def test_check_input_settings_failure_raises_mic_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sabi.capture import microphone as m

    def bad_check(**_kw: object) -> None:
        raise OSError("simulated mic blocked")

    monkeypatch.setattr(m.sd, "check_input_settings", bad_check)
    vad = _ScriptedVad([], default=False)
    with pytest.raises(MicUnavailableError) as excinfo:
        with MicrophoneSource(MicConfig(), vad_backend=vad):
            pass
    msg = str(excinfo.value)
    assert "Microphone" in msg
    assert "Privacy" in msg or "privacy" in msg


def test_selects_silero_when_webrtcvad_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sabi.capture import microphone as m

    # Block webrtcvad
    monkeypatch.setitem(sys.modules, "webrtcvad", None)

    # Inject a minimal fake silero_vad module (avoid downloading real weights).
    fake_silero = types.ModuleType("silero_vad")

    class _FakeModel:
        def __call__(self, tensor, sample_rate):  # noqa: ANN001
            import torch

            return torch.tensor(0.1)

    fake_silero.load_silero_vad = lambda: _FakeModel()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "silero_vad", fake_silero)

    # torch import in the adapter is cheap (already installed).
    src = m.MicrophoneSource(MicConfig())
    assert src.backend == "silero"
