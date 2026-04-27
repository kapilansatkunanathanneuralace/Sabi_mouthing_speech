"""Shared pipeline status events for user-facing observers (TICKET-013)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PipelineName = Literal["silent", "audio", "fused"]
PipelinePhase = Literal["idle", "recording", "decoding", "cleaning", "pasting"]


@dataclass(frozen=True)
class PipelineStatusEvent:
    """Live status update emitted by pipelines without depending on UI code."""

    pipeline: PipelineName
    mode: PipelinePhase
    utterance_id: int | None = None
    hotkey_binding: str = ""
    force_paste_binding: str = "f12"
    ollama_ok: bool | None = None
    ollama_model: str | None = None
    cuda_status: str = "unknown"
    message: str | None = None
    clipboard_restore_deadline_ns: int | None = None
    pending_force_paste: bool = False
    created_at_ns: int = 0


UiMode = Literal["tui", "none"]


def normalize_ui_mode(value: str) -> UiMode:
    """Normalize and validate CLI/UI mode strings."""

    normalized = value.strip().lower()
    if normalized not in {"tui", "none"}:
        raise ValueError(f"ui must be 'tui' or 'none', got {value!r}")
    return normalized  # type: ignore[return-value]


__all__ = [
    "PipelineName",
    "PipelinePhase",
    "PipelineStatusEvent",
    "UiMode",
    "normalize_ui_mode",
]
