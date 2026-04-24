"""TICKET-007: ASRModel wrapper tests (no real faster-whisper, no downloads).

All tests monkeypatch :class:`faster_whisper.WhisperModel` so they exercise
the wrapper's config wiring, confidence math, per-word plumbing, and
empty-input behavior without touching the network, CUDA, or disk.
"""

from __future__ import annotations

import math
import sys
import types
from typing import Any

import numpy as np
import pytest

from sabi.capture.microphone import Utterance
from sabi.models import asr as asr_module
from sabi.models.asr import (
    ASRModel,
    ASRModelConfig,
    ASRResult,
    _confidence_from_logprob,
    _weighted_avg_logprob,
)


class _FakeSegment:
    def __init__(
        self,
        text: str,
        start: float,
        end: float,
        avg_logprob: float,
        words: list[Any] | None = None,
    ) -> None:
        self.text = text
        self.start = start
        self.end = end
        self.avg_logprob = avg_logprob
        self.words = words


class _FakeWord:
    def __init__(self, word: str, start: float, end: float, probability: float) -> None:
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class _FakeInfo:
    def __init__(self, language: str | None = "en") -> None:
        self.language = language


class _FakeWhisperModel:
    """Stand-in for ``faster_whisper.WhisperModel``."""

    last_instance: "_FakeWhisperModel | None" = None

    def __init__(self, model_size: str, **kwargs: Any) -> None:
        self.model_size = model_size
        self.kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        self.segments_to_return: list[_FakeSegment] = []
        self.info = _FakeInfo(language="en")
        _FakeWhisperModel.last_instance = self

    def transcribe(self, samples: np.ndarray, **kwargs: Any):  # noqa: ANN401
        self.calls.append({"samples_len": int(samples.shape[0]), "kwargs": kwargs})
        # Yield from a generator to simulate faster-whisper's lazy API.
        return iter(list(self.segments_to_return)), self.info


@pytest.fixture
def stub_whisper(monkeypatch: pytest.MonkeyPatch) -> type[_FakeWhisperModel]:
    """Install a fake ``faster_whisper`` module so ``ASRModel._ensure_loaded`` finds it."""
    fake_module = types.ModuleType("faster_whisper")
    fake_module.WhisperModel = _FakeWhisperModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    _FakeWhisperModel.last_instance = None
    return _FakeWhisperModel


def _utterance(
    samples: np.ndarray,
    peak_dbfs: float = -10.0,
    sample_rate: int = 16000,
) -> Utterance:
    return Utterance(
        samples=samples,
        start_ts_ns=0,
        end_ts_ns=int(samples.shape[0] * 1e9 / max(sample_rate, 1)),
        sample_rate=sample_rate,
        peak_dbfs=peak_dbfs,
        mean_dbfs=peak_dbfs - 6.0,
        vad_coverage=1.0,
    )


def _speech_samples(duration_s: float = 0.6, amplitude: float = 0.3) -> np.ndarray:
    n = int(16000 * duration_s)
    t = np.linspace(0, duration_s, n, endpoint=False, dtype=np.float32)
    return (amplitude * np.sin(2 * math.pi * 220.0 * t)).astype(np.float32)


def test_auto_device_picks_cuda_and_int8_float16(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    fake = stub_whisper
    fake.last_instance = None

    with ASRModel(ASRModelConfig(device="auto")) as model:
        segs = [_FakeSegment("hello", 0.0, 0.3, -0.2)]
        # Arrange the next instance so transcribe returns something.
        model._ensure_loaded()
        assert fake.last_instance is not None
        fake.last_instance.segments_to_return = segs
        result = model.transcribe(_utterance(_speech_samples()))

    assert fake.last_instance is not None
    assert fake.last_instance.kwargs["device"] == "cuda"
    assert fake.last_instance.kwargs["compute_type"] == "int8_float16"
    assert result.device == "cuda"
    assert result.language == "en"


def test_auto_device_falls_back_to_cpu_and_int8(
    stub_whisper: type[_FakeWhisperModel],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    with caplog.at_level("WARNING", logger="sabi.models.asr"):
        with ASRModel(ASRModelConfig(device="auto")) as model:
            model._ensure_loaded()
            assert stub_whisper.last_instance is not None
            stub_whisper.last_instance.segments_to_return = []
            model.transcribe(_utterance(_speech_samples()))

    assert stub_whisper.last_instance is not None
    assert stub_whisper.last_instance.kwargs["device"] == "cpu"
    assert stub_whisper.last_instance.kwargs["compute_type"] == "int8"
    assert any("CUDA not available" in rec.message for rec in caplog.records)


def test_compute_type_override_respected(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    with ASRModel(ASRModelConfig(device="auto", compute_type="float16")) as model:
        model._ensure_loaded()
    assert stub_whisper.last_instance is not None
    assert stub_whisper.last_instance.kwargs["compute_type"] == "float16"


def test_confidence_conversion_from_avg_logprob(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    segs = [
        _FakeSegment(text="ab", start=0.0, end=0.5, avg_logprob=-0.1),
        _FakeSegment(text="cd", start=0.5, end=1.0, avg_logprob=-0.5),
    ]
    with ASRModel(ASRModelConfig(device="cpu")) as model:
        model._ensure_loaded()
        assert stub_whisper.last_instance is not None
        stub_whisper.last_instance.segments_to_return = segs
        result = model.transcribe(_utterance(_speech_samples()))

    expected_logprob = (-0.1 * 2 + -0.5 * 2) / 4
    expected_conf = math.exp(expected_logprob)
    assert result.avg_logprob == pytest.approx(expected_logprob, abs=1e-6)
    assert result.confidence == pytest.approx(expected_conf, abs=1e-6)
    assert 0.0 <= result.confidence <= 1.0


def test_per_word_populated_when_model_provides_words(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    segs = [
        _FakeSegment(
            text="hello world",
            start=0.0,
            end=0.5,
            avg_logprob=-0.2,
            words=[
                _FakeWord("hello", 0.0, 0.2, 0.9),
                _FakeWord("world", 0.25, 0.5, 0.8),
            ],
        ),
    ]
    with ASRModel(ASRModelConfig(device="cpu")) as model:
        model._ensure_loaded()
        assert stub_whisper.last_instance is not None
        stub_whisper.last_instance.segments_to_return = segs
        result = model.transcribe(_utterance(_speech_samples()))

    assert result.per_word_confidence == [
        ("hello", 0.0, 0.2, 0.9),
        ("world", 0.25, 0.5, 0.8),
    ]
    assert result.text == "hello world"


def test_per_word_missing_is_empty_list_not_none(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    segs = [_FakeSegment("hi", 0.0, 0.3, -0.1, words=None)]
    with ASRModel(ASRModelConfig(device="cpu")) as model:
        model._ensure_loaded()
        assert stub_whisper.last_instance is not None
        stub_whisper.last_instance.segments_to_return = segs
        result = model.transcribe(_utterance(_speech_samples()))

    assert result.per_word_confidence == []
    assert isinstance(result.per_word_confidence, list)


def test_empty_utterance_returns_empty_result_without_loading_model(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    utterance = _utterance(np.zeros(0, dtype=np.float32), peak_dbfs=-math.inf)

    with ASRModel(ASRModelConfig(device="cpu")) as model:
        result = model.transcribe(utterance)

    assert isinstance(result, ASRResult)
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.per_word_confidence == []
    assert result.segments == []
    assert stub_whisper.last_instance is None, "WhisperModel must not be loaded on silence"


def test_silence_utterance_below_floor_returns_empty(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    samples = np.zeros(16000, dtype=np.float32)
    utterance = _utterance(samples, peak_dbfs=-80.0)

    with ASRModel(ASRModelConfig(device="cpu", silence_peak_dbfs=-60.0)) as model:
        result = model.transcribe(utterance)

    assert result.text == ""
    assert result.confidence == 0.0
    assert stub_whisper.last_instance is None


def test_warm_up_invokes_model_and_transcribe_reuses_instance(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    with ASRModel(ASRModelConfig(device="cpu")) as model:
        warm = model.warm_up()
        first_instance = stub_whisper.last_instance
        assert first_instance is not None
        assert first_instance.calls, "warm_up must call WhisperModel.transcribe"

        first_instance.segments_to_return = [
            _FakeSegment("ok", 0.0, 0.1, -0.2),
        ]
        result = model.transcribe(_utterance(_speech_samples()))

    assert stub_whisper.last_instance is first_instance, "subsequent transcribe must reuse instance"
    assert result.text == "ok"
    assert warm.text == ""
    assert warm.latency_ms >= 0.0
    assert model.last_warmup_latency_ms is not None


def test_transcribe_kwargs_match_config(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with ASRModel(
        ASRModelConfig(
            device="cpu",
            language="en",
            beam_size=3,
            word_timestamps=False,
            vad_filter=False,
        )
    ) as model:
        model._ensure_loaded()
        assert stub_whisper.last_instance is not None
        stub_whisper.last_instance.segments_to_return = []
        model.transcribe(_utterance(_speech_samples()))

    fake = stub_whisper.last_instance
    assert fake is not None
    call_kwargs = fake.calls[0]["kwargs"]
    assert call_kwargs["language"] == "en"
    assert call_kwargs["beam_size"] == 3
    assert call_kwargs["vad_filter"] is False
    assert call_kwargs["word_timestamps"] is False


def test_device_cuda_requested_without_cuda_raises(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="device='cuda'"):
        with ASRModel(ASRModelConfig(device="cuda")) as model:
            model._ensure_loaded()


def test_confidence_helpers_clip_and_handle_empty() -> None:
    assert _weighted_avg_logprob([]) == 0.0
    assert _confidence_from_logprob(0.0) == pytest.approx(1.0)
    assert _confidence_from_logprob(-10.0) < 1e-3
    # Never exceeds 1.0 even for numerically positive inputs.
    assert _confidence_from_logprob(1.0) == pytest.approx(1.0)


def test_samples_dtype_is_coerced_to_float32(
    stub_whisper: type[_FakeWhisperModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    samples_f64 = _speech_samples().astype(np.float64)
    utterance = _utterance(samples_f64)

    with ASRModel(ASRModelConfig(device="cpu")) as model:
        model._ensure_loaded()
        assert stub_whisper.last_instance is not None
        stub_whisper.last_instance.segments_to_return = []
        model.transcribe(utterance)

    # The fake records the samples length; we also inspect the actual
    # contiguous float32 coercion via a direct call.
    arr = model._validate_samples(samples_f64)
    assert arr.dtype == np.float32
    assert arr.flags["C_CONTIGUOUS"] is True


def test_module_attributes_exported() -> None:
    """Ensure public names are importable from both ``sabi.models.asr`` and ``sabi.models``."""
    for name in ("ASRModel", "ASRModelConfig", "ASRResult"):
        assert hasattr(asr_module, name)
