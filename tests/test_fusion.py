"""TICKET-016: pure audio-visual fusion combiner tests."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from typer.testing import CliRunner

from sabi.cli import app
from sabi.fusion import FusedResult, FusionCombiner, FusionConfig
from sabi.models.asr import ASRResult
from sabi.models.vsr.model import VSRResult


def _asr(text: str, confidence: float = 0.8, word_conf: list[float] | None = None) -> ASRResult:
    words = text.split()
    confidences = word_conf if word_conf is not None else [confidence] * len(words)
    return ASRResult(
        text=text,
        segments=[],
        confidence=confidence,
        per_word_confidence=[
            (word, float(i), float(i + 1), confidences[i]) for i, word in enumerate(words)
        ],
        avg_logprob=0.0,
        latency_ms=10.0,
        language="en",
        device="cpu",
    )


def _vsr(text: str, confidence: float = 0.5, word_conf: list[float] | None = None) -> VSRResult:
    words = text.split()
    confidences = word_conf if word_conf is not None else [confidence] * len(words)
    return VSRResult(
        text=text,
        confidence=confidence,
        per_token_scores=tuple(confidences),
        latency_ms=20.0,
    )


def test_public_import_contract() -> None:
    assert FusionCombiner is not None
    assert FusionConfig is not None
    assert FusedResult is not None


def test_identical_sentences_mark_every_word_both() -> None:
    result = FusionCombiner().combine(_asr("ship by friday", 0.9), _vsr("ship by friday", 0.5))

    assert result.text == "ship by friday"
    assert result.per_word_origin == ["both", "both", "both"]
    assert result.source_weights == {"asr": 0.5, "vsr": 0.5}
    assert result.mode_used == "audio_primary"
    assert result.confidence == 0.9


def test_disagreement_asr_wins_when_more_confident() -> None:
    result = FusionCombiner().combine(
        _asr("ship by friday", 0.9, [0.9, 0.9, 0.9]),
        _vsr("ship by monday", 0.5, [0.5, 0.5, 0.4]),
    )

    assert result.text == "ship by friday"
    assert result.per_word_origin == ["both", "both", "asr"]
    assert result.confidence < 0.9


def test_disagreement_vsr_wins_in_vsr_primary_when_more_confident() -> None:
    result = FusionCombiner(FusionConfig(mode="vsr_primary")).combine(
        _asr("ship by friday", 0.6, [0.6, 0.6, 0.4]),
        _vsr("ship by monday", 0.8, [0.8, 0.8, 0.9]),
    )

    assert result.text == "ship by monday"
    assert result.per_word_origin == ["both", "both", "vsr"]
    assert result.mode_used == "vsr_primary"


def test_empty_asr_returns_vsr_verbatim() -> None:
    result = FusionCombiner().combine(_asr(""), _vsr("hello world", 1.0))

    assert result.text == "hello world"
    assert result.mode_used == "vsr_primary"
    assert result.mode_reason == "asr empty"
    assert result.source_weights == {"asr": 0.0, "vsr": 1.0}
    assert result.confidence == 0.85


def test_empty_vsr_returns_asr_verbatim() -> None:
    result = FusionCombiner().combine(_asr("hello world", 1.0), _vsr(""))

    assert result.text == "hello world"
    assert result.mode_used == "audio_primary"
    assert result.mode_reason == "vsr empty"
    assert result.source_weights == {"asr": 1.0, "vsr": 0.0}
    assert result.confidence == 0.85


def test_both_empty_returns_empty_result() -> None:
    result = FusionCombiner().combine(_asr(""), _vsr(""))

    assert result.text == ""
    assert result.confidence == 0.0
    assert result.source_weights == {"asr": 0.0, "vsr": 0.0}
    assert result.per_word_origin == []


def test_low_alignment_returns_higher_confidence_source_verbatim() -> None:
    result = FusionCombiner().combine(
        _asr("alpha beta gamma", 1.0),
        _vsr("one two three", 0.4),
    )

    assert result.text == "alpha beta gamma"
    assert result.mode_reason == "alignment_below_threshold"
    assert result.per_word_origin == ["asr", "asr", "asr"]
    assert result.confidence == 0.45


def test_low_alignment_audio_primary_fallback_forces_asr_in_auto_mode() -> None:
    cfg = FusionConfig(low_alignment_fallback="audio_primary")
    result = FusionCombiner(cfg).combine(
        _asr("alpha beta gamma", 0.4),
        _vsr("one two three", 1.0),
    )

    assert result.text == "alpha beta gamma"
    assert result.mode_used == "audio_primary"
    assert result.mode_reason == "alignment_below_threshold:audio_primary_fallback"
    assert result.per_word_origin == ["asr", "asr", "asr"]


def test_low_alignment_vsr_primary_fallback_forces_vsr_in_auto_mode() -> None:
    cfg = FusionConfig(low_alignment_fallback="vsr_primary")
    result = FusionCombiner(cfg).combine(
        _asr("alpha beta gamma", 1.0),
        _vsr("one two three", 0.4),
    )

    assert result.text == "one two three"
    assert result.mode_used == "vsr_primary"
    assert result.mode_reason == "alignment_below_threshold:vsr_primary_fallback"
    assert result.per_word_origin == ["vsr", "vsr", "vsr"]


def test_low_alignment_fallback_ignored_when_mode_explicit() -> None:
    cfg = FusionConfig(mode="audio_primary", low_alignment_fallback="vsr_primary")
    result = FusionCombiner(cfg).combine(
        _asr("alpha beta gamma", 1.0),
        _vsr("one two three", 0.4),
    )

    assert result.text == "alpha beta gamma"
    assert result.mode_used == "audio_primary"
    assert result.mode_reason == "alignment_below_threshold"
    assert result.per_word_origin == ["asr", "asr", "asr"]


def test_low_alignment_fallback_does_not_affect_high_alignment_path() -> None:
    cfg = FusionConfig(low_alignment_fallback="audio_primary")
    result = FusionCombiner(cfg).combine(
        _asr("ship by friday", 0.9, [0.9, 0.9, 0.9]),
        _vsr("ship by monday", 0.5, [0.5, 0.5, 0.4]),
    )

    assert result.text == "ship by friday"
    assert result.mode_used == "audio_primary"
    assert "alignment_below_threshold" not in result.mode_reason
    assert result.per_word_origin == ["both", "both", "asr"]


def test_tie_within_epsilon_respects_tie_breaker() -> None:
    cfg = FusionConfig(mode="audio_primary", tie_breaker="vsr", tie_epsilon=0.05)
    result = FusionCombiner(cfg).combine(
        _asr("ship by friday", 0.7, [0.7, 0.7, 0.70]),
        _vsr("ship by monday", 0.7, [0.7, 0.7, 0.72]),
    )

    assert result.text == "ship by monday"
    assert result.per_word_origin == ["both", "both", "vsr"]


def test_auto_mode_switches_to_vsr_when_asr_is_below_floor() -> None:
    result = FusionCombiner().combine(
        _asr("hello wurld", 0.2, [0.2, 0.2]),
        _vsr("hello world", 0.7, [0.7, 0.7]),
    )

    assert result.text == "hello world"
    assert result.mode_used == "vsr_primary"
    assert result.mode_reason == "asr below floor and vsr above floor"


def test_random_inputs_keep_result_invariants() -> None:
    rng = random.Random(16)
    vocab = ["ship", "by", "friday", "hello", "world", "alpha", "beta", "gamma"]
    combiner = FusionCombiner()

    for _ in range(100):
        asr_words = [rng.choice(vocab) for _ in range(rng.randint(0, 8))]
        vsr_words = [rng.choice(vocab) for _ in range(rng.randint(0, 8))]
        asr_conf = rng.random()
        vsr_conf = rng.random()

        result = combiner.combine(
            _asr(" ".join(asr_words), asr_conf),
            _vsr(" ".join(vsr_words), vsr_conf),
        )

        assert math.isfinite(result.confidence)
        assert math.isfinite(result.latency_ms)
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.per_word_origin) == len(result.text.split())
        assert len(result.per_word_confidence) == len(result.per_word_origin)


def test_latency_is_recorded_and_fast_for_short_inputs() -> None:
    text = " ".join(f"word{i}" for i in range(32))

    result = FusionCombiner().combine(_asr(text, 0.9), _vsr(text, 0.7))

    assert result.latency_ms >= 0.0
    assert result.latency_ms < 5.0


def test_fusion_smoke_text_shortcut_cli() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "fusion-smoke",
            "--asr-text",
            "ship by friday",
            "--vsr-text",
            "ship by friday",
            "--asr-conf",
            "0.9",
            "--vsr-conf",
            "0.5",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["text"] == "ship by friday"
    assert payload["per_word_origin"] == ["both", "both", "both"]
    assert payload["source_weights"] == {"asr": 0.5, "vsr": 0.5}
    assert payload["mode_used"] == "audio_primary"


def test_fusion_smoke_empty_asr_cli() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["fusion-smoke", "--asr-text", "", "--vsr-text", "hello world", "--vsr-conf", "0.6"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["text"] == "hello world"
    assert payload["mode_used"] == "vsr_primary"
    assert payload["mode_reason"] == "asr empty"


def test_fusion_smoke_json_files_cli(tmp_path: Path) -> None:
    asr_path = tmp_path / "asr.json"
    vsr_path = tmp_path / "vsr.json"
    asr_path.write_text(
        json.dumps(
            {
                "text": "ship by friday",
                "confidence": 0.9,
                "per_word_confidence": [
                    ["ship", 0.0, 1.0, 0.9],
                    ["by", 1.0, 2.0, 0.9],
                    ["friday", 2.0, 3.0, 0.9],
                ],
            }
        ),
        encoding="utf-8",
    )
    vsr_path.write_text(
        json.dumps(
            {
                "text": "ship by friday",
                "confidence": 0.5,
                "per_token_scores": [0.5, 0.5, 0.5],
                "latency_ms": 0.0,
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["fusion-smoke", str(asr_path), str(vsr_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["text"] == "ship by friday"
