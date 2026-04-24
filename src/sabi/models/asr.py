"""faster-whisper ASR wrapper (TICKET-007).

Responsibilities:

* Expose a stable :class:`ASRModel` interface that mirrors
  :class:`sabi.models.vsr.model.VSRModel` so the audio pipeline
  (TICKET-012) can swap VSR for ASR without touching its call sites.
* Lazy-load ``faster_whisper.WhisperModel`` on the first call so CLI
  startup and unit tests stay cheap.
* Consume :class:`sabi.capture.microphone.Utterance` directly: the
  microphone already emits float32 mono 16 kHz, matching
  faster-whisper's expected input.
* Preserve per-word confidences because Phase 2 AV fusion (roadmap
  Tier 2) will need them.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from sabi.capture.microphone import Utterance

logger = logging.getLogger(__name__)

Device = Literal["auto", "cuda", "cpu"]
ModelSize = Literal["tiny", "base", "small", "medium", "large-v3"]


class ASRInputError(ValueError):
    """Raised when ``transcribe`` receives audio that violates the input contract."""


class ASRModelConfig(BaseModel):
    """Configuration for :class:`ASRModel`."""

    model_size: ModelSize = Field(
        default="small",
        description="faster-whisper checkpoint size (roadmap MVP: 'small').",
    )
    device: Device = "auto"
    compute_type: str | None = Field(
        default=None,
        description=(
            "CTranslate2 compute_type. When None, uses 'int8_float16' on CUDA "
            "else 'int8' per the TICKET-007 notes."
        ),
    )
    language: str | None = Field(
        default="en",
        description="ISO-639-1 language code. None enables auto-detect.",
    )
    beam_size: int = Field(default=1, ge=1)
    vad_filter: bool = Field(
        default=False,
        description="Leave False: TICKET-006 already VAD-gates upstream.",
    )
    word_timestamps: bool = True
    min_utterance_samples: int = Field(
        default=160,
        ge=0,
        description="Utterances shorter than this return an empty ASRResult (default 10 ms @ 16 kHz).",
    )
    silence_peak_dbfs: float = Field(
        default=-60.0,
        description="Skip transcription when Utterance.peak_dbfs is below this floor.",
    )
    sample_rate: int = Field(default=16000, ge=8000)
    download_root: Path | None = Field(
        default=None,
        description="Override for the faster-whisper model cache (defaults to HF cache).",
    )

    model_config = {"arbitrary_types_allowed": True}


@dataclass(frozen=True)
class ASRResult:
    """Single-utterance prediction from :meth:`ASRModel.transcribe`."""

    text: str
    segments: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    per_word_confidence: list[tuple[str, float, float, float]] = field(default_factory=list)
    avg_logprob: float = 0.0
    latency_ms: float = 0.0
    language: str | None = None
    device: str = "cpu"


def _resolve_device(requested: Device) -> str:
    """Return ``'cuda'`` or ``'cpu'`` for CTranslate2, with a WARNING log on CPU fallback."""
    import torch

    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "device='cuda' requested but torch.cuda.is_available() is False",
            )
        return "cuda"
    if torch.cuda.is_available():
        return "cuda"
    logger.warning(
        "CUDA not available; faster-whisper will run on CPU (INT8). "
        "Expect 150-500 ms per short utterance instead of the sub-200 ms CUDA budget.",
    )
    return "cpu"


def _resolve_compute_type(device: str, override: str | None) -> str:
    if override:
        return override
    return "int8_float16" if device == "cuda" else "int8"


def _utterance_is_silence(utt: "Utterance", cfg: ASRModelConfig) -> bool:
    if utt.samples.size < cfg.min_utterance_samples:
        return True
    peak = utt.peak_dbfs
    if peak == float("-inf") or peak < cfg.silence_peak_dbfs:
        return True
    return False


def _normalize_segments(raw_segments) -> list[dict]:  # noqa: ANN001 - faster-whisper type
    """Drain faster-whisper's segment iterator into a list of plain dicts."""
    out: list[dict] = []
    for seg in raw_segments:
        out.append(
            {
                "start": float(getattr(seg, "start", 0.0) or 0.0),
                "end": float(getattr(seg, "end", 0.0) or 0.0),
                "text": str(getattr(seg, "text", "") or "").strip(),
                "avg_logprob": float(getattr(seg, "avg_logprob", 0.0) or 0.0),
                "_words": list(getattr(seg, "words", None) or []),
            },
        )
    return out


def _weighted_avg_logprob(segments: list[dict]) -> float:
    total_len = 0
    total = 0.0
    for seg in segments:
        text_len = max(len(seg.get("text", "")), 1)
        total += float(seg.get("avg_logprob", 0.0)) * text_len
        total_len += text_len
    if total_len == 0:
        return 0.0
    return total / total_len


def _confidence_from_logprob(avg_logprob: float) -> float:
    value = math.exp(avg_logprob) if avg_logprob <= 0 else 1.0
    return float(min(max(value, 0.0), 1.0))


def _flatten_words(segments: list[dict]) -> list[tuple[str, float, float, float]]:
    out: list[tuple[str, float, float, float]] = []
    for seg in segments:
        words = seg.get("_words") or []
        for w in words:
            text = str(getattr(w, "word", "") or "").strip()
            if not text:
                continue
            out.append(
                (
                    text,
                    float(getattr(w, "start", 0.0) or 0.0),
                    float(getattr(w, "end", 0.0) or 0.0),
                    float(getattr(w, "probability", 0.0) or 0.0),
                ),
            )
    return out


class ASRModel:
    """High-level faster-whisper wrapper (TICKET-007)."""

    def __init__(self, config: ASRModelConfig | None = None) -> None:
        self._config = config or ASRModelConfig()
        self._whisper = None  # populated on first transcribe / warm_up
        self._device: str | None = None
        self._compute_type: str | None = None
        self._last_warmup_ms: float | None = None

    @property
    def config(self) -> ASRModelConfig:
        return self._config

    @property
    def device(self) -> str | None:
        return self._device

    @property
    def compute_type(self) -> str | None:
        return self._compute_type

    @property
    def last_warmup_latency_ms(self) -> float | None:
        return self._last_warmup_ms

    def __enter__(self) -> "ASRModel":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def close(self) -> None:
        self._whisper = None

    def _ensure_loaded(self) -> None:
        if self._whisper is not None:
            return
        from faster_whisper import WhisperModel

        self._device = _resolve_device(self._config.device)
        self._compute_type = _resolve_compute_type(
            self._device,
            self._config.compute_type,
        )
        kwargs: dict[str, object] = {
            "device": self._device,
            "compute_type": self._compute_type,
        }
        if self._config.download_root is not None:
            kwargs["download_root"] = str(self._config.download_root)
        self._whisper = WhisperModel(self._config.model_size, **kwargs)

    def _make_empty_result(self) -> ASRResult:
        return ASRResult(
            text="",
            segments=[],
            confidence=0.0,
            per_word_confidence=[],
            avg_logprob=0.0,
            latency_ms=0.0,
            language=self._config.language,
            device=self._device or "cpu",
        )

    def _validate_samples(self, samples: np.ndarray) -> np.ndarray:
        if not isinstance(samples, np.ndarray):
            raise ASRInputError(
                f"samples must be np.ndarray, got {type(samples).__name__}",
            )
        if samples.ndim != 1:
            raise ASRInputError(
                f"samples must be 1-D mono; got shape {samples.shape}",
            )
        if samples.dtype != np.float32:
            samples = samples.astype(np.float32, copy=False)
        if not samples.flags["C_CONTIGUOUS"]:
            samples = np.ascontiguousarray(samples)
        return samples

    def transcribe(self, utterance: "Utterance") -> ASRResult:
        """Transcribe a single utterance.

        Silence or empty input returns an empty :class:`ASRResult` with
        ``confidence=0.0`` instead of raising, per TICKET-007 acceptance.
        """
        if _utterance_is_silence(utterance, self._config):
            return self._make_empty_result()

        samples = self._validate_samples(utterance.samples)

        self._ensure_loaded()
        assert self._whisper is not None

        start = time.monotonic()
        raw_segments, info = self._whisper.transcribe(
            samples,
            language=self._config.language,
            beam_size=self._config.beam_size,
            vad_filter=self._config.vad_filter,
            word_timestamps=self._config.word_timestamps,
        )
        segments = _normalize_segments(raw_segments)
        latency_ms = (time.monotonic() - start) * 1000.0

        text = " ".join(seg["text"] for seg in segments if seg["text"]).strip()
        avg_logprob = _weighted_avg_logprob(segments)
        confidence = _confidence_from_logprob(avg_logprob) if segments else 0.0
        per_word = _flatten_words(segments)
        # Strip internal `_words` key so the caller sees plain segment dicts.
        clean_segments = [
            {k: v for k, v in seg.items() if not k.startswith("_")}
            for seg in segments
        ]

        detected_language = getattr(info, "language", None)
        return ASRResult(
            text=text,
            segments=clean_segments,
            confidence=confidence,
            per_word_confidence=per_word,
            avg_logprob=avg_logprob,
            latency_ms=float(latency_ms),
            language=detected_language or self._config.language,
            device=self._device or "cpu",
        )

    def warm_up(self) -> ASRResult:
        """Run one dummy inference on 0.5 s of silence to pay the JIT cost.

        Returns the warm-up :class:`ASRResult` (expected ``text=""``); its
        ``latency_ms`` is also cached on :attr:`last_warmup_latency_ms`.
        """
        from sabi.capture.microphone import Utterance

        sr = self._config.sample_rate
        samples = np.zeros(sr // 2, dtype=np.float32)
        # Build an Utterance that deliberately bypasses the silence guard
        # (peak_dbfs = 0.0 >> silence_peak_dbfs) so the real decode runs.
        dummy = Utterance(
            samples=samples,
            start_ts_ns=0,
            end_ts_ns=int(0.5 * 1e9),
            sample_rate=sr,
            peak_dbfs=0.0,
            mean_dbfs=0.0,
            vad_coverage=0.0,
        )

        self._ensure_loaded()
        assert self._whisper is not None

        start = time.monotonic()
        raw_segments, _info = self._whisper.transcribe(
            samples,
            language=self._config.language,
            beam_size=self._config.beam_size,
            vad_filter=False,
            word_timestamps=False,
        )
        # Drain generator so the kernels actually run.
        _ = list(raw_segments)
        latency_ms = (time.monotonic() - start) * 1000.0
        self._last_warmup_ms = float(latency_ms)

        return ASRResult(
            text="",
            segments=[],
            confidence=0.0,
            per_word_confidence=[],
            avg_logprob=0.0,
            latency_ms=float(latency_ms),
            language=self._config.language,
            device=self._device or "cpu",
        )


__all__ = [
    "ASRInputError",
    "ASRModel",
    "ASRModelConfig",
    "ASRResult",
]
