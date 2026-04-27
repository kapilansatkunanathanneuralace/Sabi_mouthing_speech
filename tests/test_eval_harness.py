"""TICKET-014: offline eval harness tests."""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from sabi.capture.lip_roi import LipFrame
from sabi.cleanup.ollama import CleanedText
from sabi.eval.harness import (
    AudioOfflineRunner,
    EvalConfig,
    EvalPhrase,
    FusedOfflineRunner,
    MissingEvalDependencyError,
    SilentOfflineRunner,
    load_phrases,
    load_wav_utterance,
    percentile_stats,
    require_eval_dependencies,
    run_eval,
)
from sabi.models.asr import ASRResult
from sabi.models.vsr.model import VSRResult


class _Ctx:
    def __init__(self, value: Any) -> None:
        self.value = value

    def __enter__(self) -> Any:
        return self.value

    def __exit__(self, *a: Any) -> None:
        return None


class FakeROI:
    def process_frame(self, ts_ns: int, _frame_rgb: np.ndarray) -> LipFrame:
        return LipFrame(
            timestamp_ns=ts_ns,
            crop=np.zeros((96, 96), dtype=np.uint8),
            confidence=0.9,
            face_present=True,
            bbox=(0.0, 0.0, 96.0, 0.0),
        )


class FakeVSR:
    def predict(self, frames: list[LipFrame]) -> VSRResult:
        assert frames
        return VSRResult(
            text="hello world",
            confidence=0.92,
            per_token_scores=None,
            latency_ms=12.0,
        )


class FakeASR:
    def transcribe(self, _utt: Any) -> ASRResult:
        return ASRResult(
            text="hello world",
            segments=[],
            confidence=0.88,
            latency_ms=22.0,
            language="en",
            device="cpu",
        )


class FakeCleaner:
    def __init__(self, *, fallback: bool = False) -> None:
        self.fallback = fallback

    def cleanup(self, text: str, _ctx: Any) -> CleanedText:
        return CleanedText(
            text=text if self.fallback else "hello world",
            latency_ms=5.0,
            used_fallback=self.fallback,
            reason="ollama_unavailable" if self.fallback else None,
        )


class VersionedFakeCleaner:
    def __init__(self, prompt_version: str) -> None:
        self.prompt_version = prompt_version

    def cleanup(self, _text: str, _ctx: Any) -> CleanedText:
        if self.prompt_version == "v2":
            return CleanedText(text="hello world", latency_ms=7.0, used_fallback=False)
        return CleanedText(text="hello word", latency_ms=5.0, used_fallback=False)


def _write_dataset(root: Path, *, text: str = "hello world") -> tuple[Path, Path, Path]:
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
                "text": text,
                "video_path": "video/phrase001.mp4",
                "audio_path": "audio/phrase001.wav",
                "tags": ["test"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root / "phrases.jsonl", video, audio


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


def test_load_phrases_and_wav_loader(tmp_path: Path) -> None:
    phrases_path, _video, audio = _write_dataset(tmp_path)

    phrases = load_phrases(phrases_path)
    utt = load_wav_utterance(audio)

    assert phrases[0].id == "phrase001"
    assert phrases[0].audio_path == audio
    assert utt.sample_rate == 16000
    assert utt.samples.dtype == np.float32
    assert utt.samples.size == 16000
    assert utt.peak_dbfs > -20.0


def test_percentile_stats_known_values() -> None:
    stats = percentile_stats([10.0, 20.0, 30.0, 40.0, 50.0])

    assert stats["p50"] == pytest.approx(30.0)
    assert stats["p90"] == pytest.approx(46.0)
    assert stats["p95"] == pytest.approx(48.0)
    assert stats["p99"] == pytest.approx(49.6)
    assert stats["max"] == pytest.approx(50.0)


def test_run_eval_creates_report_and_latency_log(tmp_path: Path) -> None:
    _phrases_path, _video, _audio = _write_dataset(tmp_path / "dataset")
    report_path = tmp_path / "reports" / "poc-eval-test.md"
    latency_log = tmp_path / "reports" / "latency-log.md"
    video_frames = [(0, np.zeros((32, 32, 3), dtype=np.uint8))]
    silent = SilentOfflineRunner(
        lip_roi_factory=lambda _cfg: _Ctx(FakeROI()),
        vsr_factory=lambda _cfg: _Ctx(FakeVSR()),
        cleaner_factory=lambda _cfg: _Ctx(FakeCleaner()),
        video_loader=lambda _path: video_frames,
    )
    audio = AudioOfflineRunner(
        asr_factory=lambda _cfg: _Ctx(FakeASR()),
        cleaner_factory=lambda _cfg: _Ctx(FakeCleaner()),
    )

    result = run_eval(
        EvalConfig(
            dataset_path=tmp_path / "dataset",
            runs=1,
            warmups=0,
            pipeline="both",
            out_path=report_path,
            latency_log_path=latency_log,
        ),
        silent_runner=silent,
        audio_runner=audio,
    )

    report = report_path.read_text(encoding="utf-8")
    assert result.report_path == report_path
    assert len(result.records) == 2
    assert "## Summary" in report
    assert "raw_wer" in report
    assert "cleaned_wer" in report
    assert "## Per-Stage Latency" in report
    assert "## Phrase Results" in report
    assert "phrase001" in report
    assert "hello world" in report
    assert latency_log.read_text(encoding="utf-8").count("TICKET-014") > 0


def test_cleanup_fallback_keeps_raw_and_cleaned_wer_equal(tmp_path: Path) -> None:
    _phrases_path, _video, _audio = _write_dataset(tmp_path / "dataset", text="hello world")
    audio = AudioOfflineRunner(
        asr_factory=lambda _cfg: _Ctx(FakeASR()),
        cleaner_factory=lambda _cfg: _Ctx(FakeCleaner(fallback=True)),
    )

    result = run_eval(
        EvalConfig(
            dataset_path=tmp_path / "dataset",
            runs=1,
            warmups=0,
            pipeline="audio",
            out_path=tmp_path / "report.md",
            latency_log_path=tmp_path / "latency-log.md",
        ),
        audio_runner=audio,
    )

    rec = result.records[0]
    report = result.report_path.read_text(encoding="utf-8")
    assert rec.event.used_fallback is True
    assert rec.raw_wer == pytest.approx(rec.cleaned_wer)
    assert "cleanup: bypassed" in report


def test_run_eval_supports_fused_pipeline(tmp_path: Path) -> None:
    _phrases_path, _video, _audio = _write_dataset(tmp_path / "dataset")
    latency_log = tmp_path / "latency-log.md"
    video_frames = [(0, np.zeros((32, 32, 3), dtype=np.uint8))]
    fused = FusedOfflineRunner(
        lip_roi_factory=lambda _cfg: _Ctx(FakeROI()),
        vsr_factory=lambda _cfg: _Ctx(FakeVSR()),
        asr_factory=lambda _cfg: _Ctx(FakeASR()),
        cleaner_factory=lambda _cfg: _Ctx(FakeCleaner()),
        video_loader=lambda _path: video_frames,
    )

    result = run_eval(
        EvalConfig(
            dataset_path=tmp_path / "dataset",
            runs=1,
            warmups=0,
            pipeline="fused",
            out_path=tmp_path / "report.md",
            latency_log_path=latency_log,
        ),
        fused_runner=fused,
    )

    assert len(result.records) == 1
    assert result.records[0].pipeline == "fused"
    assert result.records[0].event.pipeline == "fused"
    report = result.report_path.read_text(encoding="utf-8")
    assert "| fused |" in report
    assert "pipeline=fused" in latency_log.read_text(encoding="utf-8")


def test_run_eval_reports_cleanup_prompt_ab_columns(tmp_path: Path) -> None:
    _phrases_path, _video, _audio = _write_dataset(tmp_path / "dataset")
    audio = AudioOfflineRunner(
        asr_factory=lambda _cfg: _Ctx(FakeASR()),
        cleaner_factory=lambda cfg: _Ctx(VersionedFakeCleaner(cfg.prompt_version)),
    )

    result = run_eval(
        EvalConfig(
            dataset_path=tmp_path / "dataset",
            runs=1,
            warmups=0,
            pipeline="audio",
            cleanup_prompts=("v1", "v2"),
            out_path=tmp_path / "report.md",
            latency_log_path=tmp_path / "latency-log.md",
        ),
        audio_runner=audio,
    )

    assert [rec.prompt_version for rec in result.records] == ["v1", "v2"]
    report = result.report_path.read_text(encoding="utf-8")
    assert "## Prompt Comparison" in report
    assert "cleaned_wer_v1" in report
    assert "cleaned_wer_v2" in report
    assert "wer_delta_v2_minus_v1" in report
    assert "| cleanup-v1 |" in report
    assert "| cleanup-v2 |" in report


def test_require_eval_dependencies_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sabi.eval.harness.importlib.util.find_spec",
        lambda name: None if name == "pandas" else object(),
    )

    with pytest.raises(MissingEvalDependencyError, match="pip install -e"):
        require_eval_dependencies()


def test_offline_runner_requires_media_path() -> None:
    runner = AudioOfflineRunner(asr_factory=lambda _cfg: _Ctx(FakeASR()))

    with pytest.raises(FileNotFoundError, match="audio_path"):
        runner.run(EvalPhrase(id="x", text="hello"), 0)
