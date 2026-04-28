"""TICKET-020: personal fused eval dataset validation tests."""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import cv2
import numpy as np

from sabi.eval.fused_dataset import validate_fused_dataset


def _write_tiny_mp4(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _write_sine_wav(path: Path, *, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    duration_s = 1.0
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    samples = (0.25 * np.sin(2 * math.pi * 220.0 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())


def _write_phrases(root: Path, rows: list[dict[str, object]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "phrases.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_validate_fused_dataset_accepts_valid_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "fused"
    _write_tiny_mp4(dataset / "video" / "p1.mp4")
    _write_sine_wav(dataset / "audio" / "p1.wav")
    _write_phrases(
        dataset,
        [
            {
                "id": "p1",
                "text": "hello world",
                "video_path": "video/p1.mp4",
                "audio_path": "audio/p1.wav",
                "tags": ["test"],
            }
        ],
    )

    summary = validate_fused_dataset(dataset)

    assert summary.is_valid is True
    assert summary.phrase_count == 1
    assert summary.valid_count == 1
    assert summary.issues == ()
    assert "--pipeline fused" in summary.recommended_eval_command


def test_validate_fused_dataset_reports_missing_paths_and_files(tmp_path: Path) -> None:
    dataset = tmp_path / "fused"
    _write_phrases(
        dataset,
        [
            {"id": "missing_paths", "text": "hello"},
            {
                "id": "missing_files",
                "text": "world",
                "video_path": "video/nope.mp4",
                "audio_path": "audio/nope.wav",
            },
        ],
    )

    summary = validate_fused_dataset(dataset)

    assert summary.is_valid is False
    assert summary.phrase_count == 2
    assert summary.valid_count == 0
    assert summary.missing_video_count == 2
    assert summary.missing_audio_count == 2
    messages = "\n".join(issue.message for issue in summary.issues)
    assert "missing video_path" in messages
    assert "audio file not found" in messages


def test_validate_fused_dataset_reports_invalid_media(tmp_path: Path) -> None:
    dataset = tmp_path / "fused"
    bad_video = dataset / "video" / "bad.mp4"
    bad_audio = dataset / "audio" / "bad.wav"
    bad_video.parent.mkdir(parents=True)
    bad_audio.parent.mkdir(parents=True)
    bad_video.write_text("not an mp4", encoding="utf-8")
    _write_sine_wav(bad_audio, sample_rate=8000)
    _write_phrases(
        dataset,
        [
            {
                "id": "bad",
                "text": "bad media",
                "video_path": "video/bad.mp4",
                "audio_path": "audio/bad.wav",
            }
        ],
    )

    summary = validate_fused_dataset(dataset)

    assert summary.is_valid is False
    assert summary.invalid_video_count == 1
    assert summary.invalid_audio_count == 1
    messages = "\n".join(issue.message for issue in summary.issues)
    assert "invalid video" in messages
    assert "expected 16 kHz" in messages


def test_validate_fused_dataset_reports_unreadable_dataset(tmp_path: Path) -> None:
    summary = validate_fused_dataset(tmp_path / "missing")

    assert summary.is_valid is False
    assert summary.phrase_count == 0
    assert summary.issues[0].field == "phrases"
    assert "eval phrases file not found" in summary.issues[0].message
