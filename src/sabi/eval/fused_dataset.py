"""Validation helpers for personal fused eval datasets (TICKET-020)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sabi.eval.harness import EvalPhrase, load_phrases, load_video_frames, load_wav_utterance


@dataclass(frozen=True)
class FusedDatasetIssue:
    """One actionable validation issue for a phrase row."""

    phrase_id: str
    field: str
    message: str


@dataclass(frozen=True)
class FusedDatasetSummary:
    """Validation summary for a fused eval dataset."""

    dataset_path: Path
    phrase_count: int
    valid_count: int
    missing_video_count: int
    missing_audio_count: int
    invalid_video_count: int
    invalid_audio_count: int
    issues: tuple[FusedDatasetIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.phrase_count > 0 and not self.issues

    @property
    def recommended_eval_command(self) -> str:
        return (
            "python -m sabi eval "
            f"--dataset {self.dataset_path} "
            "--pipeline fused --runs 1 "
            "--out reports/poc-eval-fused-personal.md"
        )


def validate_fused_dataset(dataset_path: Path) -> FusedDatasetSummary:
    """Validate a fused eval dataset without stopping at the first bad phrase."""

    try:
        phrases = load_phrases(dataset_path)
    except Exception as exc:  # noqa: BLE001 - make CLI errors actionable.
        return FusedDatasetSummary(
            dataset_path=dataset_path,
            phrase_count=0,
            valid_count=0,
            missing_video_count=0,
            missing_audio_count=0,
            invalid_video_count=0,
            invalid_audio_count=0,
            issues=(
                FusedDatasetIssue(
                    phrase_id="-",
                    field="phrases",
                    message=str(exc),
                ),
            ),
        )

    issues: list[FusedDatasetIssue] = []
    valid_count = 0
    missing_video_count = 0
    missing_audio_count = 0
    invalid_video_count = 0
    invalid_audio_count = 0

    for phrase in phrases:
        before = len(issues)
        if phrase.video_path is None:
            missing_video_count += 1
            issues.append(_issue(phrase, "video_path", "missing video_path"))
        elif not phrase.video_path.is_file():
            missing_video_count += 1
            issues.append(
                _issue(phrase, "video_path", f"video file not found: {phrase.video_path}")
            )
        else:
            try:
                load_video_frames(phrase.video_path)
            except Exception as exc:  # noqa: BLE001
                invalid_video_count += 1
                issues.append(_issue(phrase, "video_path", f"invalid video: {exc}"))

        if phrase.audio_path is None:
            missing_audio_count += 1
            issues.append(_issue(phrase, "audio_path", "missing audio_path"))
        elif not phrase.audio_path.is_file():
            missing_audio_count += 1
            issues.append(
                _issue(phrase, "audio_path", f"audio file not found: {phrase.audio_path}")
            )
        else:
            try:
                load_wav_utterance(phrase.audio_path)
            except Exception as exc:  # noqa: BLE001
                invalid_audio_count += 1
                issues.append(_issue(phrase, "audio_path", f"invalid audio: {exc}"))

        if len(issues) == before:
            valid_count += 1

    return FusedDatasetSummary(
        dataset_path=dataset_path,
        phrase_count=len(phrases),
        valid_count=valid_count,
        missing_video_count=missing_video_count,
        missing_audio_count=missing_audio_count,
        invalid_video_count=invalid_video_count,
        invalid_audio_count=invalid_audio_count,
        issues=tuple(issues),
    )


def _issue(phrase: EvalPhrase, field: str, message: str) -> FusedDatasetIssue:
    return FusedDatasetIssue(phrase_id=phrase.id, field=field, message=message)


__all__ = [
    "FusedDatasetIssue",
    "FusedDatasetSummary",
    "validate_fused_dataset",
]
