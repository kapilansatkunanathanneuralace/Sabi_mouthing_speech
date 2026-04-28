"""Pure audio-visual transcript fusion (TICKET-016)."""

from __future__ import annotations

import math
import string
import time
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from sabi.models.asr import ASRResult
from sabi.models.vsr.model import VSRResult

FusionMode = Literal["auto", "audio_primary", "vsr_primary"]
WordOrigin = Literal["asr", "vsr", "both"]
LowAlignmentFallback = Literal["higher_confidence", "audio_primary", "vsr_primary"]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "fusion.toml"


class FusionConfig(BaseModel):
    """Tunable rules for one-shot ASR/VSR transcript fusion."""

    mode: FusionMode = "auto"
    asr_confidence_floor: float = Field(default=0.4, ge=0.0, le=1.0)
    vsr_confidence_floor: float = Field(default=0.35, ge=0.0, le=1.0)
    auto_switch_low_conf_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    tie_epsilon: float = Field(default=0.02, ge=0.0, le=1.0)
    tie_breaker: Literal["asr", "vsr"] = "asr"
    min_alignment_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    low_alignment_fallback: LowAlignmentFallback = "higher_confidence"


@dataclass(frozen=True)
class FusedResult:
    """Final transcript plus provenance produced by :func:`combine`."""

    text: str
    confidence: float
    source_weights: dict[str, float]
    per_word_origin: list[WordOrigin]
    per_word_confidence: list[float]
    mode_used: FusionMode
    mode_reason: str
    latency_ms: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _TokenStream:
    surface: list[str]
    normalized: list[str]
    confidence: list[float]


def load_fusion_config(path: Path | None = None) -> FusionConfig:
    """Load fusion defaults from ``configs/fusion.toml`` when present."""

    target = path if path is not None else DEFAULT_CONFIG_PATH
    if not target.is_file():
        return FusionConfig()
    with target.open("rb") as f:
        data = tomllib.load(f)
    fusion = data.get("fusion", {}) or {}
    return FusionConfig(**fusion)


def combine(
    asr: ASRResult | None,
    vsr: VSRResult | None,
    config: FusionConfig | None = None,
) -> FusedResult:
    """Fuse ASR and VSR transcripts without touching hardware or models."""

    cfg = config or FusionConfig()
    asr_stream = _asr_stream(asr)
    vsr_stream = _vsr_stream(vsr)

    if not asr_stream.surface and not vsr_stream.surface:
        return _empty_result(cfg.mode, "both empty", 0.0)
    if not asr_stream.surface:
        return _verbatim_result(
            vsr_stream,
            "vsr_primary",
            "asr empty",
            0.0,
            "vsr",
            confidence_cap=0.85,
        )
    if not vsr_stream.surface:
        return _verbatim_result(
            asr_stream,
            "audio_primary",
            "vsr empty",
            0.0,
            "asr",
            confidence_cap=0.85,
        )

    start = time.perf_counter()
    mode_used, mode_reason = _resolve_mode(cfg, asr, vsr, asr_stream)
    alignment = _align(asr_stream.normalized, vsr_stream.normalized)
    aligned_ratio = _alignment_ratio(alignment, asr_stream.normalized, vsr_stream.normalized)
    if aligned_ratio < cfg.min_alignment_ratio:
        return _low_alignment_pick(
            cfg=cfg,
            asr=asr,
            vsr=vsr,
            asr_stream=asr_stream,
            vsr_stream=vsr_stream,
            aligned_ratio=aligned_ratio,
            start=start,
        )

    words: list[str] = []
    origins: list[WordOrigin] = []
    confidences: list[float] = []
    primary = "asr" if mode_used == "audio_primary" else "vsr"

    for a_idx, v_idx in alignment:
        if a_idx is not None and v_idx is not None:
            a_word = asr_stream.surface[a_idx]
            v_word = vsr_stream.surface[v_idx]
            a_conf = asr_stream.confidence[a_idx]
            v_conf = vsr_stream.confidence[v_idx]
            if asr_stream.normalized[a_idx] == vsr_stream.normalized[v_idx]:
                words.append(a_word if primary == "asr" else v_word)
                origins.append("both")
                confidences.append(max(a_conf, v_conf))
            else:
                source = _choose_source(a_conf, v_conf, cfg, primary)
                if source == "asr":
                    words.append(a_word)
                    origins.append("asr")
                    confidences.append(a_conf)
                else:
                    words.append(v_word)
                    origins.append("vsr")
                    confidences.append(v_conf)
        elif a_idx is not None and primary == "asr":
            words.append(asr_stream.surface[a_idx])
            origins.append("asr")
            confidences.append(asr_stream.confidence[a_idx])
        elif v_idx is not None and primary == "vsr":
            words.append(vsr_stream.surface[v_idx])
            origins.append("vsr")
            confidences.append(vsr_stream.confidence[v_idx])

    return FusedResult(
        text=" ".join(words),
        confidence=_calibrated_confidence(confidences, origins),
        source_weights=_source_weights(origins),
        per_word_origin=origins,
        per_word_confidence=[_clamp01(c) for c in confidences],
        mode_used=mode_used,
        mode_reason=mode_reason,
        latency_ms=_elapsed_ms(start),
    )


class FusionCombiner:
    """Reusable thin wrapper around :func:`combine`."""

    def __init__(self, config: FusionConfig | None = None) -> None:
        self.config = config or FusionConfig()

    def combine(
        self,
        asr: ASRResult | None,
        vsr: VSRResult | None,
        config: FusionConfig | None = None,
    ) -> FusedResult:
        return combine(asr, vsr, config or self.config)


def _asr_stream(asr: ASRResult | None) -> _TokenStream:
    if asr is None:
        return _TokenStream([], [], [])
    surface = _surface_tokens(asr.text)
    if not surface:
        return _TokenStream([], [], [])
    confidences = [_clamp01(asr.confidence)] * len(surface)
    if len(asr.per_word_confidence) == len(surface):
        confidences = [_clamp01(float(item[3])) for item in asr.per_word_confidence]
    return _TokenStream(surface, [_normalize_token(t) for t in surface], confidences)


def _vsr_stream(vsr: VSRResult | None) -> _TokenStream:
    if vsr is None:
        return _TokenStream([], [], [])
    surface = _surface_tokens(vsr.text)
    if not surface:
        return _TokenStream([], [], [])
    confidences = [_clamp01(vsr.confidence)] * len(surface)
    if vsr.per_token_scores is not None and len(vsr.per_token_scores) == len(surface):
        confidences = [_clamp01(float(score)) for score in vsr.per_token_scores]
    return _TokenStream(surface, [_normalize_token(t) for t in surface], confidences)


def _surface_tokens(text: str) -> list[str]:
    return [token for token in text.split() if token]


def _normalize_token(token: str) -> str:
    return token.lower().strip(string.punctuation)


def _resolve_mode(
    cfg: FusionConfig,
    asr: ASRResult | None,
    vsr: VSRResult | None,
    asr_stream: _TokenStream,
) -> tuple[Literal["audio_primary", "vsr_primary"], str]:
    if cfg.mode == "audio_primary":
        return "audio_primary", "configured audio_primary"
    if cfg.mode == "vsr_primary":
        return "vsr_primary", "configured vsr_primary"

    asr_conf = _overall_confidence(asr)
    vsr_conf = _overall_confidence(vsr)
    low_conf_words = sum(1 for conf in asr_stream.confidence if conf < cfg.asr_confidence_floor)
    low_conf_ratio = low_conf_words / max(len(asr_stream.confidence), 1)
    if asr_conf < cfg.asr_confidence_floor and vsr_conf >= cfg.vsr_confidence_floor:
        return "vsr_primary", "asr below floor and vsr above floor"
    if low_conf_ratio > cfg.auto_switch_low_conf_ratio:
        return "vsr_primary", "asr word confidence ratio below floor"
    return "audio_primary", "auto -> audio_primary"


def _overall_confidence(result: ASRResult | VSRResult | None) -> float:
    if result is None:
        return 0.0
    return _clamp01(float(result.confidence))


def _align(a: list[str], v: list[str]) -> list[tuple[int | None, int | None]]:
    rows = len(a) + 1
    cols = len(v) + 1
    score = [[0 for _ in range(cols)] for _ in range(rows)]
    pointer: list[list[str]] = [["" for _ in range(cols)] for _ in range(rows)]

    for i in range(1, rows):
        score[i][0] = score[i - 1][0] - 1
        pointer[i][0] = "up"
    for j in range(1, cols):
        score[0][j] = score[0][j - 1] - 1
        pointer[0][j] = "left"

    for i in range(1, rows):
        for j in range(1, cols):
            diag_score = score[i - 1][j - 1] + (1 if a[i - 1] == v[j - 1] else -1)
            up_score = score[i - 1][j] - 1
            left_score = score[i][j - 1] - 1
            best = max(diag_score, up_score, left_score)
            score[i][j] = best
            if best == diag_score:
                pointer[i][j] = "diag"
            elif best == up_score:
                pointer[i][j] = "up"
            else:
                pointer[i][j] = "left"

    out: list[tuple[int | None, int | None]] = []
    i = len(a)
    j = len(v)
    while i > 0 or j > 0:
        move = pointer[i][j]
        if move == "diag":
            out.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif move == "up":
            out.append((i - 1, None))
            i -= 1
        else:
            out.append((None, j - 1))
            j -= 1
    out.reverse()
    return out


def _alignment_ratio(
    alignment: list[tuple[int | None, int | None]],
    a_tokens: list[str],
    v_tokens: list[str],
) -> float:
    shorter = min(len(a_tokens), len(v_tokens))
    if shorter == 0:
        return 0.0
    matched = 0
    for a_idx, v_idx in alignment:
        if a_idx is not None and v_idx is not None and a_tokens[a_idx] == v_tokens[v_idx]:
            matched += 1
    return matched / shorter


def _choose_source(
    a_conf: float,
    v_conf: float,
    cfg: FusionConfig,
    primary: Literal["asr", "vsr"],
) -> Literal["asr", "vsr"]:
    if abs(a_conf - v_conf) < cfg.tie_epsilon:
        if primary == cfg.tie_breaker:
            return primary
        return cfg.tie_breaker
    return "asr" if a_conf > v_conf else "vsr"


def _verbatim_result(
    stream: _TokenStream,
    mode_used: FusionMode,
    mode_reason: str,
    latency_ms: float,
    source: Literal["asr", "vsr"],
    *,
    confidence_multiplier: float = 1.0,
    confidence_cap: float = 1.0,
) -> FusedResult:
    origins: list[WordOrigin] = [source for _ in stream.surface]
    confidence = _mean_confidence(stream.confidence) * confidence_multiplier
    return FusedResult(
        text=" ".join(stream.surface),
        confidence=min(_clamp01(confidence), confidence_cap),
        source_weights=_source_weights(origins),
        per_word_origin=origins,
        per_word_confidence=[_clamp01(c) for c in stream.confidence],
        mode_used=mode_used,
        mode_reason=mode_reason,
        latency_ms=max(latency_ms, 0.0),
    )


def _empty_result(mode_used: FusionMode, mode_reason: str, latency_ms: float) -> FusedResult:
    return FusedResult(
        text="",
        confidence=0.0,
        source_weights={"asr": 0.0, "vsr": 0.0},
        per_word_origin=[],
        per_word_confidence=[],
        mode_used=mode_used,
        mode_reason=mode_reason,
        latency_ms=max(latency_ms, 0.0),
    )


def _mean_confidence(values: list[float]) -> float:
    if not values:
        return 0.0
    return _clamp01(sum(values) / len(values))


def _calibrated_confidence(values: list[float], origins: list[WordOrigin]) -> float:
    base = _mean_confidence(values)
    if not origins:
        return 0.0
    agreement_ratio = sum(1 for origin in origins if origin == "both") / len(origins)
    multiplier = 0.65 + (0.35 * agreement_ratio)
    return _clamp01(base * multiplier)


def _low_alignment_pick(
    *,
    cfg: FusionConfig,
    asr: ASRResult | None,
    vsr: VSRResult | None,
    asr_stream: _TokenStream,
    vsr_stream: _TokenStream,
    aligned_ratio: float,
    start: float,
) -> FusedResult:
    """Pick verbatim ASR or VSR when transcripts barely align.

    The configurable :attr:`FusionConfig.low_alignment_fallback` knob only
    applies when ``cfg.mode == "auto"``. Explicit ``audio_primary`` /
    ``vsr_primary`` modes keep the historical higher-confidence pick so
    forced modes stay predictable. See TICKET-038.
    """

    if cfg.mode == "auto":
        policy: LowAlignmentFallback = cfg.low_alignment_fallback
    else:
        policy = "higher_confidence"

    multiplier = _low_alignment_confidence_multiplier(aligned_ratio)

    if policy == "audio_primary":
        return _verbatim_result(
            asr_stream,
            "audio_primary",
            "alignment_below_threshold:audio_primary_fallback",
            _elapsed_ms(start),
            "asr",
            confidence_multiplier=multiplier,
        )
    if policy == "vsr_primary":
        return _verbatim_result(
            vsr_stream,
            "vsr_primary",
            "alignment_below_threshold:vsr_primary_fallback",
            _elapsed_ms(start),
            "vsr",
            confidence_multiplier=multiplier,
        )

    if _overall_confidence(asr) >= _overall_confidence(vsr):
        return _verbatim_result(
            asr_stream,
            "audio_primary",
            "alignment_below_threshold",
            _elapsed_ms(start),
            "asr",
            confidence_multiplier=multiplier,
        )
    return _verbatim_result(
        vsr_stream,
        "vsr_primary",
        "alignment_below_threshold",
        _elapsed_ms(start),
        "vsr",
        confidence_multiplier=multiplier,
    )


def _low_alignment_confidence_multiplier(aligned_ratio: float) -> float:
    return 0.45 + (0.5 * _clamp01(aligned_ratio))


def _source_weights(origins: list[WordOrigin]) -> dict[str, float]:
    if not origins:
        return {"asr": 0.0, "vsr": 0.0}
    asr_count = 0.0
    vsr_count = 0.0
    for origin in origins:
        if origin == "both":
            asr_count += 0.5
            vsr_count += 0.5
        elif origin == "asr":
            asr_count += 1.0
        else:
            vsr_count += 1.0
    total = asr_count + vsr_count
    return {"asr": asr_count / total, "vsr": vsr_count / total}


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(max(value, 0.0), 1.0)


def _elapsed_ms(start: float) -> float:
    return max((time.perf_counter() - start) * 1000.0, 0.0)


__all__ = [
    "FusedResult",
    "FusionCombiner",
    "FusionConfig",
    "FusionMode",
    "LowAlignmentFallback",
    "combine",
    "load_fusion_config",
]
