"""Guided fused-eval dataset collection (TICKET-019)."""

from __future__ import annotations

import json
import re
import subprocess
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from sabi.eval.harness import EvalPhrase, load_video_frames, load_wav_utterance

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "eval" / "fused"
DEFAULT_PHRASES_PATH = REPO_ROOT / "data" / "eval" / "phrases.sample.jsonl"

TakeStatus = Literal["recorded", "skipped", "planned", "failed"]
RESET_MEDIA_SUFFIXES = {".mp4", ".wav"}


@dataclass(frozen=True)
class FusedEvalCollectionConfig:
    """Configuration for collecting paired video/audio fused eval takes."""

    out_dir: Path = DEFAULT_OUT_DIR
    phrases_path: Path = DEFAULT_PHRASES_PATH
    video_dir: str = "video"
    audio_dir: str = "audio"
    video_ext: str = "mp4"
    audio_sample_rate: int = 16000
    duration_s: float = 4.0
    camera_name: str | None = None
    mic_name: str | None = None
    limit: int | None = None
    start_at: str | None = None
    phrase_ids: tuple[str, ...] = ()
    retry_phrase_id: str | None = None
    skip_existing: bool = False
    overwrite: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class FusedEvalTake:
    phrase: EvalPhrase
    video_path: Path
    audio_path: Path
    video_rel: str
    audio_rel: str
    status: TakeStatus
    error: str | None = None


@dataclass(frozen=True)
class CollectionResult:
    phrases_path: Path
    takes: tuple[FusedEvalTake, ...]

    @property
    def recorded(self) -> int:
        return sum(1 for take in self.takes if take.status == "recorded")

    @property
    def skipped(self) -> int:
        return sum(1 for take in self.takes if take.status == "skipped")

    @property
    def planned(self) -> int:
        return sum(1 for take in self.takes if take.status == "planned")

    @property
    def failed(self) -> int:
        return sum(1 for take in self.takes if take.status == "failed")


@dataclass(frozen=True)
class ResetResult:
    """Files removed or planned for removal by a fused dataset reset."""

    out_dir: Path
    files: tuple[Path, ...]
    dry_run: bool

    @property
    def removed_count(self) -> int:
        return 0 if self.dry_run else len(self.files)


class FusedEvalRecorder(Protocol):
    """Recorder interface used by the real CLI and test fakes."""

    def record_take(
        self,
        phrase: EvalPhrase,
        *,
        video_path: Path,
        audio_path: Path,
        duration_s: float,
    ) -> None:
        """Record one phrase to an MP4 plus a 16 kHz PCM WAV."""


class FfmpegFusedEvalRecorder:
    """Record synchronized webcam + mic media through ffmpeg's Windows dshow input."""

    def __init__(
        self,
        *,
        camera_name: str | None,
        mic_name: str | None,
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        self.camera_name = camera_name
        self.mic_name = mic_name
        self.ffmpeg_path = ffmpeg_path

    def record_take(
        self,
        phrase: EvalPhrase,
        *,
        video_path: Path,
        audio_path: Path,
        duration_s: float,
    ) -> None:
        if not self.camera_name or not self.mic_name:
            raise ValueError(
                "ffmpeg collection requires --camera-name and --mic-name. "
                "Run `ffmpeg -list_devices true -f dshow -i dummy` to list devices."
            )
        video_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        input_spec = f'video={self.camera_name}:audio={self.mic_name}'
        command = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "dshow",
            "-t",
            f"{duration_s:.3f}",
            "-i",
            input_spec,
            "-map",
            "0:v:0",
            "-c:v",
            "mpeg4",
            str(video_path),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(audio_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            prefix = f"ffmpeg failed while recording phrase {phrase.id}"
            raise RuntimeError(f"{prefix}: {details}") from exc


BeforeRecordCallback = Callable[[EvalPhrase, int, int], None]


def collect_fused_eval(
    config: FusedEvalCollectionConfig,
    *,
    recorder: FusedEvalRecorder | None = None,
    before_record: BeforeRecordCallback | None = None,
) -> CollectionResult:
    """Collect a fused eval dataset and update the output ``phrases.jsonl``."""

    _validate_config(config)
    phrases = select_phrases(load_collection_phrases(config.phrases_path), config)
    if not phrases:
        raise ValueError("no phrases matched the requested filters")

    output_phrases_path = config.out_dir / "phrases.jsonl"
    active_recorder = recorder or FfmpegFusedEvalRecorder(
        camera_name=config.camera_name,
        mic_name=config.mic_name,
    )
    takes: list[FusedEvalTake] = []
    rows_to_write: list[dict[str, object]] = []

    for index, phrase in enumerate(phrases, start=1):
        planned = planned_take(config, phrase)
        if config.dry_run:
            takes.append(_with_status(planned, "planned"))
            continue

        exists = planned.video_path.exists() or planned.audio_path.exists()
        if exists and config.skip_existing:
            error = validate_take(planned, expected_duration_s=config.duration_s)
            if error is None:
                takes.append(_with_status(planned, "skipped"))
                rows_to_write.append(_row_for_take(planned))
            else:
                takes.append(_with_status(planned, "failed", error=error))
            continue
        if exists and not (config.overwrite or config.retry_phrase_id):
            takes.append(
                _with_status(
                    planned,
                    "failed",
                    error="media exists; pass --skip-existing, --retry, or --overwrite",
                )
            )
            continue

        try:
            if before_record is not None:
                before_record(phrase, index, len(phrases))
            active_recorder.record_take(
                phrase,
                video_path=planned.video_path,
                audio_path=planned.audio_path,
                duration_s=config.duration_s,
            )
            error = validate_take(planned, expected_duration_s=config.duration_s)
            if error is None:
                takes.append(_with_status(planned, "recorded"))
                rows_to_write.append(_row_for_take(planned))
            else:
                takes.append(_with_status(planned, "failed", error=error))
        except Exception as exc:  # noqa: BLE001 - preserve per-phrase failures.
            takes.append(_with_status(planned, "failed", error=str(exc)))

    if rows_to_write:
        output_phrases_path.parent.mkdir(parents=True, exist_ok=True)
        merged = _merge_rows(_read_jsonl_rows(output_phrases_path), rows_to_write)
        _write_jsonl_rows(output_phrases_path, merged)

    return CollectionResult(phrases_path=output_phrases_path, takes=tuple(takes))


def reset_fused_eval_dataset(
    out_dir: Path = DEFAULT_OUT_DIR,
    *,
    dry_run: bool = True,
) -> ResetResult:
    """Remove generated fused eval metadata and media files."""

    files = tuple(_reset_targets(out_dir))
    if not dry_run:
        for path in files:
            path.unlink(missing_ok=True)
    return ResetResult(out_dir=out_dir, files=files, dry_run=dry_run)


def load_collection_phrases(path: Path) -> list[EvalPhrase]:
    """Load source phrases from JSONL, JSON array, or a dataset directory."""

    target = path if path.is_file() else path / "phrases.jsonl"
    if not target.is_file():
        raise FileNotFoundError(f"phrase file not found: {target}")
    text = target.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        raise ValueError(f"phrase file is empty: {target}")
    if stripped.startswith("["):
        raw_rows = json.loads(stripped)
    else:
        raw_rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    phrases: list[EvalPhrase] = []
    for row in raw_rows:
        phrases.append(
            EvalPhrase(
                id=str(row["id"]),
                text=str(row["text"]),
                tags=tuple(str(tag) for tag in row.get("tags", []) or []),
            )
        )
    return phrases


def _reset_targets(out_dir: Path) -> list[Path]:
    targets: list[Path] = []
    phrases = out_dir / "phrases.jsonl"
    if phrases.is_file():
        targets.append(phrases)
    for child_dir in (out_dir / "video", out_dir / "audio"):
        if not child_dir.is_dir():
            continue
        targets.extend(
            sorted(
                path
                for path in child_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in RESET_MEDIA_SUFFIXES
            )
        )
    return targets


def select_phrases(
    phrases: Sequence[EvalPhrase],
    config: FusedEvalCollectionConfig,
) -> list[EvalPhrase]:
    selected = list(phrases)
    if config.retry_phrase_id:
        selected = [phrase for phrase in selected if phrase.id == config.retry_phrase_id]
    elif config.phrase_ids:
        wanted = set(config.phrase_ids)
        selected = [phrase for phrase in selected if phrase.id in wanted]
    if config.start_at:
        selected = _apply_start_at(selected, config.start_at)
    if config.limit is not None:
        selected = selected[: config.limit]
    return selected


def planned_take(config: FusedEvalCollectionConfig, phrase: EvalPhrase) -> FusedEvalTake:
    safe_id = sanitize_phrase_id(phrase.id)
    video_rel = f"{config.video_dir}/{safe_id}.{config.video_ext.lstrip('.')}"
    audio_rel = f"{config.audio_dir}/{safe_id}.wav"
    return FusedEvalTake(
        phrase=phrase,
        video_path=config.out_dir / video_rel,
        audio_path=config.out_dir / audio_rel,
        video_rel=video_rel,
        audio_rel=audio_rel,
        status="planned",
    )


def sanitize_phrase_id(phrase_id: str) -> str:
    raw = phrase_id.strip()
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    if not safe:
        raise ValueError(f"phrase id cannot be used as a filename: {phrase_id!r}")
    return safe


def validate_take(
    take: FusedEvalTake,
    *,
    expected_duration_s: float | None = None,
) -> str | None:
    """Return ``None`` for a valid take, otherwise an actionable error string."""

    try:
        frames = load_video_frames(take.video_path)
    except Exception as exc:  # noqa: BLE001 - validation reports all loader failures.
        return f"invalid video: {exc}"
    try:
        load_wav_utterance(take.audio_path)
    except Exception as exc:  # noqa: BLE001
        return f"invalid audio: {exc}"
    try:
        with wave.open(str(take.audio_path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            frame_count = wav.getnframes()
            sample_rate = wav.getframerate()
    except Exception as exc:  # noqa: BLE001
        return f"invalid audio: {exc}"
    if channels != 1:
        return f"invalid audio: expected mono wav, got {channels} channels"
    if sample_width != 2:
        return f"invalid audio: expected 16-bit PCM wav, got sample width {sample_width}"
    if frame_count <= 0:
        return "invalid audio: wav contains no samples"
    audio_duration_s = frame_count / float(max(sample_rate, 1))
    if expected_duration_s is not None:
        video_duration_s = _video_duration_s(frames)
        error = _duration_error("video", video_duration_s, expected_duration_s)
        if error is not None:
            return error
        error = _duration_error("audio", audio_duration_s, expected_duration_s)
        if error is not None:
            return error
    return None


def _video_duration_s(frames: list[tuple[int, object]]) -> float:
    if len(frames) < 2:
        return 0.0
    return max(0.0, (frames[-1][0] - frames[0][0]) / 1_000_000_000.0)


def _duration_error(kind: str, observed_s: float, expected_s: float) -> str | None:
    if observed_s <= 0:
        return f"invalid {kind}: duration is zero"
    lower = max(0.05, expected_s * 0.5)
    upper = expected_s * 1.5
    if observed_s < lower or observed_s > upper:
        return (
            f"invalid {kind}: duration {observed_s:.2f}s does not roughly match "
            f"requested {expected_s:.2f}s"
        )
    return None


def _validate_config(config: FusedEvalCollectionConfig) -> None:
    if config.limit is not None and config.limit < 1:
        raise ValueError("--limit must be at least 1")
    if config.duration_s <= 0:
        raise ValueError("--duration-s must be greater than 0")
    if config.retry_phrase_id and config.phrase_ids:
        raise ValueError("--retry cannot be combined with --phrase-id")
    if config.retry_phrase_id and config.skip_existing:
        raise ValueError("--retry cannot be combined with --skip-existing")


def _apply_start_at(phrases: list[EvalPhrase], start_at: str) -> list[EvalPhrase]:
    raw = start_at.strip()
    if raw.isdigit():
        idx = max(int(raw) - 1, 0)
        return phrases[idx:]
    for idx, phrase in enumerate(phrases):
        if phrase.id == raw:
            return phrases[idx:]
    raise ValueError(f"--start-at did not match a phrase id or 1-based index: {start_at!r}")


def _with_status(
    take: FusedEvalTake,
    status: TakeStatus,
    *,
    error: str | None = None,
) -> FusedEvalTake:
    return FusedEvalTake(
        phrase=take.phrase,
        video_path=take.video_path,
        audio_path=take.audio_path,
        video_rel=take.video_rel,
        audio_rel=take.audio_rel,
        status=status,
        error=error,
    )


def _row_for_take(take: FusedEvalTake) -> dict[str, object]:
    row: dict[str, object] = {
        "id": take.phrase.id,
        "text": take.phrase.text,
        "video_path": take.video_rel,
        "audio_path": take.audio_rel,
    }
    if take.phrase.tags:
        row["tags"] = list(take.phrase.tags)
    return row


def _read_jsonl_rows(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl_rows(path: Path, rows: Sequence[dict[str, object]]) -> None:
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def _merge_rows(
    existing: Sequence[dict[str, object]],
    updates: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    by_id = {str(row["id"]): dict(row) for row in existing}
    order = [str(row["id"]) for row in existing]
    for row in updates:
        phrase_id = str(row["id"])
        by_id[phrase_id] = dict(row)
        if phrase_id not in order:
            order.append(phrase_id)
    return [by_id[phrase_id] for phrase_id in order]


__all__ = [
    "CollectionResult",
    "FfmpegFusedEvalRecorder",
    "FusedEvalCollectionConfig",
    "FusedEvalRecorder",
    "FusedEvalTake",
    "ResetResult",
    "collect_fused_eval",
    "load_collection_phrases",
    "planned_take",
    "reset_fused_eval_dataset",
    "sanitize_phrase_id",
    "select_phrases",
    "validate_take",
]
