"""Threaded microphone capture + VAD-gated utterance emitter (TICKET-006)."""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import sounddevice as sd
from pydantic import BaseModel, Field

_logger = logging.getLogger(__name__)


def _mic_remediation_text() -> str:
    return (
        "Remediation: Windows Settings > Privacy & security > Microphone - "
        "allow desktop apps. Close other apps using the microphone. "
        "Verify a default input device is configured."
    )


class MicUnavailableError(RuntimeError):
    """Raised when the microphone cannot be opened or sampled."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class MicConfig(BaseModel):
    device_index: int | None = Field(
        default=None,
        description="sounddevice input index. None means the system default.",
    )
    sample_rate: int = Field(default=16000, ge=8000)
    channels: Literal[1] = 1
    frame_ms: Literal[10, 20, 30] = 20
    vad_aggressiveness: int = Field(default=2, ge=0, le=3)
    silero_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_utterance_ms: int = Field(default=300, ge=0)
    max_utterance_ms: int = Field(default=15000, ge=1)
    trailing_silence_ms: int = Field(default=400, ge=0)
    queue_max_frames: int = Field(default=256, ge=1)
    output_queue_max: int = Field(default=32, ge=1)


@dataclass(frozen=True)
class Utterance:
    """One contiguous speech segment, ready for ASR."""

    samples: np.ndarray
    start_ts_ns: int
    end_ts_ns: int
    sample_rate: int
    peak_dbfs: float
    mean_dbfs: float
    vad_coverage: float

    @property
    def duration_s(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.samples.shape[0] / float(self.sample_rate)


@dataclass
class MicStats:
    frames_captured: int = 0
    frames_dropped: int = 0
    utterances_emitted: int = 0
    last_status_flags: str = ""


class _VadBackend:
    """Abstract VAD: returns speech/non-speech for a single 10/20/30 ms frame."""

    name: str = "abstract"

    def is_speech(self, frame_int16: np.ndarray, sample_rate: int) -> bool:
        raise NotImplementedError


class _WebRTCVad(_VadBackend):
    name = "webrtcvad"

    def __init__(self, aggressiveness: int) -> None:
        import webrtcvad

        self._vad = webrtcvad.Vad(int(aggressiveness))

    def is_speech(self, frame_int16: np.ndarray, sample_rate: int) -> bool:
        return bool(self._vad.is_speech(frame_int16.tobytes(), sample_rate))


class _SileroVad(_VadBackend):
    """Silero VAD adapter that accumulates frames into the model's native window."""

    name = "silero"
    _WINDOW_SAMPLES = {8000: 256, 16000: 512}

    def __init__(self, threshold: float, sample_rate: int) -> None:
        try:
            import torch
            from silero_vad import load_silero_vad
        except ImportError as exc:
            raise MicUnavailableError(
                "Neither webrtcvad nor silero-vad is importable. Install one of:\n"
                "  pip install webrtcvad-wheels\n"
                "  pip install silero-vad\n"
                f"Underlying error: {exc}"
            ) from exc
        if sample_rate not in self._WINDOW_SAMPLES:
            raise MicUnavailableError(
                f"silero-vad requires 8 kHz or 16 kHz input; got {sample_rate}."
            )
        self._torch = torch
        self._model = load_silero_vad()
        self._threshold = float(threshold)
        self._sample_rate = int(sample_rate)
        self._window = self._WINDOW_SAMPLES[sample_rate]
        self._buf = np.zeros(0, dtype=np.float32)
        self._last_prob = 0.0

    def is_speech(self, frame_int16: np.ndarray, sample_rate: int) -> bool:
        chunk = frame_int16.astype(np.float32) / 32768.0
        self._buf = np.concatenate([self._buf, chunk])
        while self._buf.size >= self._window:
            window = self._buf[: self._window]
            self._buf = self._buf[self._window :]
            tensor = self._torch.from_numpy(window.copy())
            with self._torch.no_grad():
                self._last_prob = float(self._model(tensor, sample_rate).item())
        return self._last_prob >= self._threshold


def _select_vad_backend(config: MicConfig) -> _VadBackend:
    """Prefer webrtcvad; fall back to silero-vad if webrtcvad is unavailable."""
    try:
        return _WebRTCVad(config.vad_aggressiveness)
    except ImportError as exc:
        _logger.warning(
            "webrtcvad import failed (%s); falling back to silero-vad.", exc
        )
        return _SileroVad(config.silero_threshold, config.sample_rate)


def _compute_dbfs(samples: np.ndarray) -> tuple[float, float]:
    if samples.size == 0:
        return (-math.inf, -math.inf)
    abs_samples = np.abs(samples)
    peak_lin = float(abs_samples.max())
    peak_db = 20.0 * math.log10(peak_lin) if peak_lin > 0 else -math.inf
    mean_sq = float(np.mean(samples.astype(np.float64) ** 2))
    mean_db = 10.0 * math.log10(mean_sq) if mean_sq > 0 else -math.inf
    return peak_db, mean_db


@dataclass
class _VadState:
    """Internal VAD-gate state machine state (worker thread only)."""

    mode: str = "listening"  # "listening" | "in_speech" | "trailing_silence"
    frames: list[np.ndarray] = field(default_factory=list)
    flags: list[bool] = field(default_factory=list)
    start_ts_ns: int = 0
    last_ts_ns: int = 0
    in_segment_ms: int = 0
    trailing_silent_ms: int = 0

    def reset(self) -> None:
        self.mode = "listening"
        self.frames = []
        self.flags = []
        self.start_ts_ns = 0
        self.last_ts_ns = 0
        self.in_segment_ms = 0
        self.trailing_silent_ms = 0


class MicrophoneSource:
    """16 kHz mono microphone with a VAD-gated utterance emitter.

    Opens a :class:`sounddevice.RawInputStream` on ``__enter__``; the PortAudio
    callback pushes 20 ms ``int16`` frames onto a bounded queue. A worker
    thread pulls frames, runs the VAD, and drives a state machine that emits
    one :class:`Utterance` per detected speech segment. A push-to-talk API
    bypasses the state machine for callers that already know when to start
    and stop recording (TICKET-010's hotkey path).
    """

    _JOIN_TIMEOUT_S = 2.0

    def __init__(
        self,
        config: MicConfig | None = None,
        vad_backend: _VadBackend | None = None,
    ) -> None:
        self._config = config or MicConfig()
        if vad_backend is None:
            vad_backend = _select_vad_backend(self._config)
        self._vad = vad_backend
        self.backend: str = vad_backend.name

        self._frame_samples = (
            self._config.sample_rate * self._config.frame_ms // 1000
        )

        self._callback_queue: queue.Queue[tuple[int, bytes]] = queue.Queue(
            maxsize=self._config.queue_max_frames,
        )
        self._utterance_queue: queue.Queue[Utterance] = queue.Queue(
            maxsize=self._config.output_queue_max,
        )

        self._stats_lock = threading.Lock()
        self._stats = MicStats()

        self._meter_lock = threading.Lock()
        self._last_peak_dbfs: float = -math.inf
        self._last_is_speech: bool = False

        self._running = False
        self._stream: sd.RawInputStream | None = None
        self._worker: threading.Thread | None = None
        self._entered = False

        self._ptt_lock = threading.Lock()
        self._ptt_active = False
        self._ptt_frames: list[bytes] = []
        self._ptt_flags: list[bool] = []

    @property
    def config(self) -> MicConfig:
        return self._config

    @property
    def stats(self) -> MicStats:
        with self._stats_lock:
            return MicStats(
                frames_captured=self._stats.frames_captured,
                frames_dropped=self._stats.frames_dropped,
                utterances_emitted=self._stats.utterances_emitted,
                last_status_flags=self._stats.last_status_flags,
            )

    def current_meter(self) -> tuple[float, bool]:
        """Return the last observed ``(peak_dbfs, is_speech)`` for live UIs."""
        with self._meter_lock:
            return (self._last_peak_dbfs, self._last_is_speech)

    def _validate_device(self) -> None:
        try:
            sd.check_input_settings(
                device=self._config.device_index,
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype="int16",
            )
        except Exception as exc:  # noqa: BLE001
            raise MicUnavailableError(
                f"Microphone: device settings rejected ({exc}).\n"
                + _mic_remediation_text(),
            ) from exc

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if not self._running:
            return
        if status:
            try:
                with self._stats_lock:
                    self._stats.last_status_flags = str(status)
            except Exception:  # noqa: BLE001
                pass
        try:
            payload = bytes(indata)
        except Exception:  # noqa: BLE001
            return
        ts_ns = time.time_ns()
        try:
            self._callback_queue.put_nowait((ts_ns, payload))
            with self._stats_lock:
                self._stats.frames_captured += 1
        except queue.Full:
            with self._stats_lock:
                self._stats.frames_dropped += 1

    def _emit_utterance(
        self,
        state: _VadState,
        *,
        forced: bool = False,
    ) -> None:
        if not state.frames:
            return
        samples_int16 = np.concatenate(state.frames)
        duration_ms = (samples_int16.shape[0] * 1000) // self._config.sample_rate
        if not forced and duration_ms < self._config.min_utterance_ms:
            return
        float_samples = samples_int16.astype(np.float32) / 32768.0
        peak_db, mean_db = _compute_dbfs(float_samples)
        coverage = float(sum(state.flags)) / max(len(state.flags), 1)
        utt = Utterance(
            samples=float_samples,
            start_ts_ns=state.start_ts_ns,
            end_ts_ns=state.last_ts_ns,
            sample_rate=self._config.sample_rate,
            peak_dbfs=peak_db,
            mean_dbfs=mean_db,
            vad_coverage=coverage,
        )
        try:
            self._utterance_queue.put_nowait(utt)
        except queue.Full:
            try:
                _ = self._utterance_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._utterance_queue.put_nowait(utt)
            except queue.Full:
                return
        with self._stats_lock:
            self._stats.utterances_emitted += 1

    def _update_meter(self, frame_int16: np.ndarray, is_speech: bool) -> None:
        float_frame = frame_int16.astype(np.float32) / 32768.0
        peak_db, _mean = _compute_dbfs(float_frame)
        with self._meter_lock:
            self._last_peak_dbfs = peak_db
            self._last_is_speech = is_speech

    def _worker_loop(self) -> None:
        state = _VadState()
        sr = self._config.sample_rate
        frame_ms = self._config.frame_ms
        max_ms = self._config.max_utterance_ms
        tail_ms = self._config.trailing_silence_ms

        while self._running:
            try:
                ts_ns, payload = self._callback_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            frame_int16 = np.frombuffer(payload, dtype=np.int16)
            if frame_int16.size != self._frame_samples:
                continue
            try:
                is_speech = self._vad.is_speech(frame_int16, sr)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("VAD error (%s); treating frame as non-speech", exc)
                is_speech = False
            self._update_meter(frame_int16, is_speech)

            with self._ptt_lock:
                if self._ptt_active:
                    self._ptt_frames.append(payload)
                    self._ptt_flags.append(is_speech)
                    continue

            if state.mode == "listening":
                if is_speech:
                    state.mode = "in_speech"
                    state.start_ts_ns = ts_ns
                    state.last_ts_ns = ts_ns
                    state.frames = [frame_int16.copy()]
                    state.flags = [True]
                    state.in_segment_ms = frame_ms
                    state.trailing_silent_ms = 0
                continue

            state.frames.append(frame_int16.copy())
            state.flags.append(is_speech)
            state.last_ts_ns = ts_ns
            state.in_segment_ms += frame_ms

            if state.mode == "in_speech":
                if is_speech:
                    state.trailing_silent_ms = 0
                else:
                    state.mode = "trailing_silence"
                    state.trailing_silent_ms = frame_ms
            elif state.mode == "trailing_silence":
                if is_speech:
                    state.mode = "in_speech"
                    state.trailing_silent_ms = 0
                else:
                    state.trailing_silent_ms += frame_ms
                    if state.trailing_silent_ms >= tail_ms:
                        self._emit_utterance(state)
                        state.reset()
                        continue

            if state.in_segment_ms >= max_ms:
                self._emit_utterance(state, forced=True)
                state.reset()

    def utterances(self) -> Iterator[Utterance]:
        """Yield :class:`Utterance` objects as they complete.

        Keeps yielding until the context manager exits and the internal
        output queue has drained.
        """
        while self._running or not self._utterance_queue.empty():
            try:
                yield self._utterance_queue.get(timeout=0.1)
            except queue.Empty:
                continue

    def next_utterance(self, timeout: float | None = None) -> Utterance | None:
        """Block up to ``timeout`` seconds for a single utterance.

        Returns ``None`` on timeout; ``None`` is also used by tests that
        want a non-blocking drain with ``timeout=0``.
        """
        try:
            return self._utterance_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def push_to_talk_segment(
        self,
        start_trigger_event: threading.Event,
        end_trigger_event: threading.Event,
    ) -> Utterance:
        """Record raw audio between two hotkey edges, bypassing VAD gating.

        Waits for ``start_trigger_event`` to be set, then accumulates every
        incoming audio frame until ``end_trigger_event`` is set. The VAD is
        still evaluated on each frame, but its output only contributes to the
        returned :attr:`Utterance.vad_coverage` metric. The returned
        ``start_ts_ns`` and ``end_ts_ns`` reflect the wall-clock time at
        which each trigger was observed, not the first / last frame.
        """
        if not self._running:
            raise RuntimeError("MicrophoneSource must be entered before PTT use.")

        start_trigger_event.wait()
        start_ts_ns = time.time_ns()
        with self._ptt_lock:
            if self._ptt_active:
                raise RuntimeError("A PTT segment is already in progress.")
            self._ptt_active = True
            self._ptt_frames = []
            self._ptt_flags = []

        try:
            end_trigger_event.wait()
        finally:
            end_ts_ns = time.time_ns()

        time.sleep(max(self._config.frame_ms / 1000.0, 0.02))
        with self._ptt_lock:
            frames = self._ptt_frames
            flags = self._ptt_flags
            self._ptt_frames = []
            self._ptt_flags = []
            self._ptt_active = False

        if not frames:
            return Utterance(
                samples=np.zeros(0, dtype=np.float32),
                start_ts_ns=start_ts_ns,
                end_ts_ns=end_ts_ns,
                sample_rate=self._config.sample_rate,
                peak_dbfs=-math.inf,
                mean_dbfs=-math.inf,
                vad_coverage=0.0,
            )

        int16_all = np.concatenate([np.frombuffer(b, dtype=np.int16) for b in frames])
        float_samples = int16_all.astype(np.float32) / 32768.0
        peak_db, mean_db = _compute_dbfs(float_samples)
        coverage = float(sum(flags)) / max(len(flags), 1)
        return Utterance(
            samples=float_samples,
            start_ts_ns=start_ts_ns,
            end_ts_ns=end_ts_ns,
            sample_rate=self._config.sample_rate,
            peak_dbfs=peak_db,
            mean_dbfs=mean_db,
            vad_coverage=coverage,
        )

    def __enter__(self) -> MicrophoneSource:
        if self._entered:
            raise RuntimeError("MicrophoneSource context is not re-entrant.")
        self._entered = True
        self._validate_device()
        try:
            self._stream = sd.RawInputStream(
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype="int16",
                blocksize=self._frame_samples,
                device=self._config.device_index,
                callback=self._audio_callback,
            )
            self._running = True
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            self._entered = False
            self._running = False
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:  # noqa: BLE001
                    pass
                self._stream = None
            raise MicUnavailableError(
                f"Microphone: failed to open input stream ({exc}).\n"
                + _mic_remediation_text(),
            ) from exc
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="MicVADWorker",
            daemon=True,
        )
        self._worker.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:  # noqa: BLE001
                pass
        if self._worker is not None:
            self._worker.join(timeout=self._JOIN_TIMEOUT_S)
            self._worker = None
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        self._entered = False
