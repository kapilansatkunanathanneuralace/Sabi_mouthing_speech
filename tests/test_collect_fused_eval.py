"""TICKET-019: fused eval dataset collection tests."""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import cv2
import numpy as np

from sabi.eval.collect_fused import (
    FusedEvalCollectionConfig,
    collect_fused_eval,
    load_collection_phrases,
    planned_take,
    reset_fused_eval_dataset,
    sanitize_phrase_id,
    select_phrases,
    validate_take,
)
from sabi.eval.harness import EvalPhrase


class FakeRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def record_take(
        self,
        phrase: EvalPhrase,
        *,
        video_path: Path,
        audio_path: Path,
        duration_s: float,
    ) -> None:
        self.calls.append(phrase.id)
        assert duration_s > 0
        _write_tiny_mp4(video_path, duration_s=duration_s)
        _write_sine_wav(audio_path, duration_s=duration_s)


def _write_source_phrases(path: Path) -> None:
    rows = [
        {
            "id": "harvard_001",
            "text": "The birch canoe slid on the smooth planks.",
            "tags": ["harvard"],
        },
        {
            "id": "harvard_002",
            "text": "Glue the sheet to the dark blue background.",
            "tags": ["harvard"],
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_tiny_mp4(path: Path, *, duration_s: float = 4.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fps = 5.0
    frame_count = max(2, int(duration_s * fps) + 1)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (32, 32),
    )
    try:
        for _ in range(frame_count):
            writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
    finally:
        writer.release()


def _write_sine_wav(
    path: Path,
    *,
    duration_s: float = 4.0,
    sample_rate: int = 16000,
    channels: int = 1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    mono = (0.25 * np.sin(2 * math.pi * 220.0 * t) * 32767).astype("<i2")
    if channels == 1:
        payload = mono
    else:
        payload = np.repeat(mono.reshape(-1, 1), channels, axis=1).reshape(-1)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(payload.tobytes())


def test_collect_fused_eval_records_media_and_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "phrases.jsonl"
    out_dir = tmp_path / "fused"
    _write_source_phrases(source)
    recorder = FakeRecorder()

    result = collect_fused_eval(
        FusedEvalCollectionConfig(
            out_dir=out_dir,
            phrases_path=source,
            limit=1,
        ),
        recorder=recorder,
    )

    assert recorder.calls == ["harvard_001"]
    assert result.recorded == 1
    assert result.failed == 0
    row = json.loads((out_dir / "phrases.jsonl").read_text(encoding="utf-8"))
    assert row["id"] == "harvard_001"
    assert row["video_path"] == "video/harvard_001.mp4"
    assert row["audio_path"] == "audio/harvard_001.wav"
    assert (out_dir / row["video_path"]).is_file()
    assert (out_dir / row["audio_path"]).is_file()


def test_collect_fused_eval_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "phrases.jsonl"
    out_dir = tmp_path / "fused"
    _write_source_phrases(source)
    recorder = FakeRecorder()

    result = collect_fused_eval(
        FusedEvalCollectionConfig(
            out_dir=out_dir,
            phrases_path=source,
            limit=1,
            dry_run=True,
        ),
        recorder=recorder,
    )

    assert result.planned == 1
    assert recorder.calls == []
    assert not (out_dir / "phrases.jsonl").exists()
    assert not out_dir.exists()


def test_collect_fused_eval_skip_existing_validates_and_merges(tmp_path: Path) -> None:
    source = tmp_path / "phrases.jsonl"
    out_dir = tmp_path / "fused"
    _write_source_phrases(source)
    take = planned_take(
        FusedEvalCollectionConfig(out_dir=out_dir, phrases_path=source),
        EvalPhrase(id="harvard_001", text="The birch canoe slid on the smooth planks."),
    )
    _write_tiny_mp4(take.video_path)
    _write_sine_wav(take.audio_path)
    recorder = FakeRecorder()

    result = collect_fused_eval(
        FusedEvalCollectionConfig(
            out_dir=out_dir,
            phrases_path=source,
            limit=1,
            skip_existing=True,
        ),
        recorder=recorder,
    )

    assert result.skipped == 1
    assert recorder.calls == []
    rows = [
        json.loads(line)
        for line in (out_dir / "phrases.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["id"] == "harvard_001"


def test_collect_fused_eval_retry_replaces_single_phrase(tmp_path: Path) -> None:
    source = tmp_path / "phrases.jsonl"
    out_dir = tmp_path / "fused"
    _write_source_phrases(source)
    recorder = FakeRecorder()

    first = collect_fused_eval(
        FusedEvalCollectionConfig(out_dir=out_dir, phrases_path=source),
        recorder=recorder,
    )
    second = collect_fused_eval(
        FusedEvalCollectionConfig(
            out_dir=out_dir,
            phrases_path=source,
            retry_phrase_id="harvard_002",
        ),
        recorder=recorder,
    )

    assert first.recorded == 2
    assert second.recorded == 1
    assert recorder.calls == ["harvard_001", "harvard_002", "harvard_002"]
    rows = [
        json.loads(line)
        for line in (out_dir / "phrases.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["id"] for row in rows] == ["harvard_001", "harvard_002"]


def test_collect_fused_eval_existing_without_policy_fails(tmp_path: Path) -> None:
    source = tmp_path / "phrases.jsonl"
    out_dir = tmp_path / "fused"
    _write_source_phrases(source)
    recorder = FakeRecorder()
    collect_fused_eval(
        FusedEvalCollectionConfig(out_dir=out_dir, phrases_path=source, limit=1),
        recorder=recorder,
    )

    result = collect_fused_eval(
        FusedEvalCollectionConfig(out_dir=out_dir, phrases_path=source, limit=1),
        recorder=recorder,
    )

    assert result.failed == 1
    assert "media exists" in (result.takes[0].error or "")


def test_phrase_loading_selection_and_sanitizing(tmp_path: Path) -> None:
    source = tmp_path / "phrases.json"
    source.write_text(
        json.dumps(
            [
                {"id": "one", "text": "One."},
                {"id": "two", "text": "Two."},
                {"id": "three", "text": "Three."},
            ]
        ),
        encoding="utf-8",
    )
    phrases = load_collection_phrases(source)

    selected = select_phrases(
        phrases,
        FusedEvalCollectionConfig(phrases_path=source, start_at="2", limit=1),
    )

    assert [phrase.id for phrase in selected] == ["two"]
    assert sanitize_phrase_id("hi there/again") == "hi_there_again"


def test_validate_take_rejects_bad_audio_shape(tmp_path: Path) -> None:
    take = planned_take(
        FusedEvalCollectionConfig(out_dir=tmp_path),
        EvalPhrase(id="phrase", text="hello"),
    )
    _write_tiny_mp4(take.video_path)
    _write_sine_wav(take.audio_path, channels=2)

    assert validate_take(take) == "invalid audio: expected mono wav, got 2 channels"


def test_validate_take_rejects_duration_mismatch(tmp_path: Path) -> None:
    take = planned_take(
        FusedEvalCollectionConfig(out_dir=tmp_path),
        EvalPhrase(id="phrase", text="hello"),
    )
    _write_tiny_mp4(take.video_path, duration_s=4.0)
    _write_sine_wav(take.audio_path, duration_s=4.0)

    error = validate_take(take, expected_duration_s=10.0)

    assert error is not None
    assert "duration" in error


def test_reset_fused_eval_dataset_previews_then_deletes_generated_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "fused"
    _write_tiny_mp4(out_dir / "video" / "harvard_001.mp4")
    _write_sine_wav(out_dir / "audio" / "harvard_001.wav")
    phrases = out_dir / "phrases.jsonl"
    phrases.write_text('{"id":"harvard_001"}\n', encoding="utf-8")
    keep = out_dir / "notes.txt"
    keep.write_text("keep me", encoding="utf-8")

    preview = reset_fused_eval_dataset(out_dir)
    deleted = reset_fused_eval_dataset(out_dir, dry_run=False)

    assert len(preview.files) == 3
    assert preview.dry_run is True
    assert preview.removed_count == 0
    assert deleted.removed_count == 3
    assert not phrases.exists()
    assert not (out_dir / "video" / "harvard_001.mp4").exists()
    assert not (out_dir / "audio" / "harvard_001.wav").exists()
    assert keep.exists()
