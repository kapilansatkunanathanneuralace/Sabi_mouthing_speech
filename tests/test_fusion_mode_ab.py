"""TICKET-037: fusion mode A/B eval."""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import cv2
import numpy as np
import pytest

from sabi.eval.fusion_mode_ab import (
    FusionModeAbConfig,
    parse_fusion_modes,
    render_fusion_mode_ab_report,
    run_fusion_mode_ab_eval,
)
from sabi.eval.harness import (
    EvalConfig,
    EvalPhrase,
    EvalRecord,
    EvalResult,
    MissingEvalDependencyError,
    percentile_stats,
    require_eval_dependencies,
    run_eval,
)
from sabi.pipelines.fused_dictate import (
    FusedDictateConfig,
)
from sabi.pipelines.fused_dictate import (
    UtteranceProcessed as FusedUtteranceProcessed,
)


def test_parse_fusion_modes_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown fusion mode"):
        parse_fusion_modes("auto,banana")


def test_parse_fusion_modes_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        parse_fusion_modes("auto,vsr_primary,auto")


def test_render_fusion_mode_ab_report_contains_sections() -> None:
    phrase = EvalPhrase(id="p1", text="hello world")
    ev_a = FusedUtteranceProcessed(
        utterance_id=1,
        started_at_ns=0,
        ended_at_ns=1,
        text_raw="hello world",
        text_final="hello world",
        confidence=1.0,
        used_fallback=False,
        decision="dry_run",
        latencies={
            "capture_ms": 1.0,
            "roi_ms": 1.0,
            "vsr_ms": 1.0,
            "asr_ms": 1.0,
            "fusion_ms": 0.0,
            "cleanup_ms": 1.0,
            "inject_ms": 0.0,
            "warmup_ms": 0.0,
            "capture_open_ms": 0.0,
            "mic_open_ms": 0.0,
            "total_ms": 100.0,
        },
        fusion={"mode_used": "audio_primary", "mode_reason": "fake"},
        asr={"text": "a", "confidence": 0.9, "latency_ms": 1.0},
        vsr={"text": "v", "confidence": 0.9, "latency_ms": 1.0},
        frame_count=1,
        face_present_ratio=1.0,
        duration_ms=1000.0,
        vad_coverage=1.0,
        peak_dbfs=-10.0,
        error=None,
    )
    ev_b = FusedUtteranceProcessed(
        utterance_id=2,
        started_at_ns=0,
        ended_at_ns=1,
        text_raw="wrong",
        text_final="wrong",
        confidence=0.5,
        used_fallback=False,
        decision="dry_run",
        latencies={
            "capture_ms": 1.0,
            "roi_ms": 1.0,
            "vsr_ms": 1.0,
            "asr_ms": 1.0,
            "fusion_ms": 0.0,
            "cleanup_ms": 1.0,
            "inject_ms": 0.0,
            "warmup_ms": 0.0,
            "capture_open_ms": 0.0,
            "mic_open_ms": 0.0,
            "total_ms": 200.0,
        },
        fusion={"mode_used": "vsr_primary", "mode_reason": "fake"},
        asr={"text": "a", "confidence": 0.9, "latency_ms": 1.0},
        vsr={"text": "v", "confidence": 0.9, "latency_ms": 1.0},
        frame_count=1,
        face_present_ratio=1.0,
        duration_ms=1000.0,
        vad_coverage=1.0,
        peak_dbfs=-10.0,
        error=None,
    )
    rec_a = EvalRecord(
        phrase=phrase,
        pipeline="fused",
        run_index=0,
        event=ev_a,
        raw_wer=0.0,
        cleaned_wer=0.0,
        prompt_version="v1",
    )
    rec_b = EvalRecord(
        phrase=phrase,
        pipeline="fused",
        run_index=0,
        event=ev_b,
        raw_wer=1.0,
        cleaned_wer=1.0,
        prompt_version="v1",
    )
    ps = percentile_stats([100.0])
    stage_row = {k: float(ps[k]) for k in ("p50", "p90", "p95", "p99", "max")}
    stage_names = (
        "capture_ms",
        "roi_ms",
        "vsr_ms",
        "asr_ms",
        "fusion_ms",
        "cleanup_ms",
        "total_ms",
    )
    stage_stats = {("fused", s): dict(stage_row) for s in stage_names}
    dummy_cfg = EvalConfig(dataset_path=Path("x"), pipeline="fused", write_output=False)
    res_a = EvalResult(
        config=dummy_cfg,
        report_path=Path("unused-a.md"),
        records=(rec_a,),
        stage_stats=stage_stats,
        summary_stats={
            "fused": {
                "raw_wer": 0.0,
                "cleaned_wer": 0.0,
                "cleanup_record_count": 1.0,
                "cleanup_fallback_count": 0.0,
                "cleanup_fallback_rate": 0.0,
                **{f"total_{k}": float(ps[k]) for k in ps},
            }
        },
    )
    res_b = EvalResult(
        config=dummy_cfg,
        report_path=Path("unused-b.md"),
        records=(rec_b,),
        stage_stats=stage_stats,
        summary_stats={
            "fused": {
                "raw_wer": 1.0,
                "cleaned_wer": 1.0,
                "cleanup_record_count": 1.0,
                "cleanup_fallback_count": 0.0,
                "cleanup_fallback_rate": 0.0,
                **{f"total_{k}": float(ps[k]) for k in ps},
            }
        },
    )
    text = render_fusion_mode_ab_report(
        dataset_path=Path("data/eval/fused"),
        modes=("audio_primary", "vsr_primary"),
        runs=1,
        warmups=0,
        cleanup_prompts=("v1",),
        by_mode={"audio_primary": res_a, "vsr_primary": res_b},
        elapsed_ms=12.0,
    )
    assert "## Summary by mode" in text
    assert "## Per-phrase cleaned WER by mode" in text
    assert "audio_primary" in text
    assert "vsr_primary" in text
    assert "p1" in text


def _write_tiny_mp4(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (32, 32),
    )
    try:
        for _ in range(5):
            writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
    finally:
        writer.release()


def _write_sine_wav(path: Path) -> None:
    sample_rate = 16000
    duration_s = 1.0
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    samples = (0.25 * np.sin(2 * math.pi * 220.0 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())


def _write_dataset(root: Path) -> None:
    video_dir = root / "video"
    audio_dir = root / "audio"
    video_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    video = video_dir / "phrase001.mp4"
    audio = audio_dir / "phrase001.wav"
    _write_tiny_mp4(video)
    _write_sine_wav(audio)
    (root / "phrases.jsonl").write_text(
        json.dumps(
            {
                "id": "phrase001",
                "text": "hello world",
                "video_path": "video/phrase001.mp4",
                "audio_path": "audio/phrase001.wav",
                "tags": ["test"],
            }
        )
        + "\n",
        encoding="utf-8",
    )


class _FakeFusionModeRunner:
    def __init__(self, cfg: FusedDictateConfig) -> None:
        self.config = cfg

    def run(self, phrase: EvalPhrase, run_index: int) -> FusedUtteranceProcessed:
        mode = self.config.fusion.mode
        if mode == "audio_primary":
            hyp = phrase.text
            conf = 1.0
        elif mode == "auto":
            hyp = phrase.text + " noise"
            conf = 0.8
        else:
            hyp = "wrong"
            conf = 0.5
        return FusedUtteranceProcessed(
            utterance_id=1,
            started_at_ns=0,
            ended_at_ns=1,
            text_raw=hyp,
            text_final=hyp,
            confidence=conf,
            used_fallback=False,
            decision="dry_run",
            latencies={
                "capture_ms": 1.0,
                "roi_ms": 1.0,
                "vsr_ms": 1.0,
                "asr_ms": 1.0,
                "fusion_ms": 0.0,
                "cleanup_ms": 1.0,
                "inject_ms": 0.0,
                "warmup_ms": 0.0,
                "capture_open_ms": 0.0,
                "mic_open_ms": 0.0,
                "total_ms": 50.0,
            },
            fusion={"mode_used": mode, "mode_reason": "fake"},
            asr={"text": "a", "confidence": 0.9, "latency_ms": 1.0},
            vsr={"text": "v", "confidence": 0.9, "latency_ms": 1.0},
            frame_count=1,
            face_present_ratio=1.0,
            duration_ms=1000.0,
            vad_coverage=1.0,
            peak_dbfs=-10.0,
            error=None,
        )


def test_run_fusion_mode_ab_eval_with_fake_runner(tmp_path: Path) -> None:
    try:
        require_eval_dependencies()
    except MissingEvalDependencyError:
        pytest.skip("eval extras not installed")

    ds = tmp_path / "dataset"
    _write_dataset(ds)
    out = tmp_path / "ab.md"
    path = run_fusion_mode_ab_eval(
        FusionModeAbConfig(
            dataset_path=ds,
            modes=("audio_primary", "auto", "vsr_primary"),
            runs=1,
            warmups=0,
            cleanup_preflight=False,
            out_path=out,
        ),
        fused_runner_factory=lambda cfg: _FakeFusionModeRunner(cfg),
    )
    assert path == out
    body = out.read_text(encoding="utf-8")
    assert "## Summary by mode" in body
    assert "phrase001" in body
    assert "audio_primary" in body
    assert "## Per-phrase cleaned WER by mode" in body


def test_run_eval_respects_write_output_false(tmp_path: Path) -> None:
    try:
        require_eval_dependencies()
    except MissingEvalDependencyError:
        pytest.skip("eval extras not installed")

    ds = tmp_path / "dataset"
    _write_dataset(ds)
    report_path = tmp_path / "should-not-exist.md"
    fused_cfg = FusedDictateConfig(dry_run=True)
    runner = _FakeFusionModeRunner(fused_cfg)
    result = run_eval(
        EvalConfig(
            dataset_path=ds,
            runs=1,
            warmups=0,
            pipeline="fused",
            out_path=report_path,
            cleanup_preflight=False,
            fused_config=fused_cfg,
            write_output=False,
        ),
        fused_runner=runner,
    )
    assert not report_path.is_file()
    assert len(result.records) == 1
