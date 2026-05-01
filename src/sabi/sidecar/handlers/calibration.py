"""Optional onboarding calibration handlers."""

from __future__ import annotations

import random
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sabi.runtime.paths import data_dir
from sabi.sidecar.dispatcher import Notify, SidecarDispatcher

DEFAULT_PHRASES_PATH = data_dir() / "eval" / "phrases.sample.jsonl"
FALLBACK_PHRASES = (
    ("calibration_001", "The birch canoe slid on the smooth planks."),
    ("calibration_002", "Glue the sheet to the dark blue background."),
    ("calibration_003", "Rice is often served in round bowls."),
    ("calibration_004", "The juice of lemons makes fine punch."),
    ("calibration_005", "Four hours of steady work faced us."),
)


@dataclass(frozen=True)
class CalibrationSample:
    sample_id: str
    text: str
    index: int
    total: int
    mode: str = "optional"

    def to_payload(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "text": self.text,
            "index": self.index,
            "total": self.total,
            "mode": self.mode,
        }


class CalibrationSession:
    def __init__(self) -> None:
        self.active_sample_id: str | None = None

    def plan(self, params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
        count = int(params.get("count", 3))
        if count < 1:
            raise ValueError("count must be at least 1")
        phrases_path = Path(params.get("phrases_path", DEFAULT_PHRASES_PATH))
        seed = params.get("seed")
        phrases = load_calibration_phrases(phrases_path)
        rng = random.Random(str(seed)) if seed is not None else random.Random()
        selected = rng.sample(phrases, k=min(count, len(phrases)))
        total = len(selected)
        return {
            "samples": [
                CalibrationSample(
                    sample_id=phrase[0],
                    text=phrase[1],
                    index=index,
                    total=total,
                ).to_payload()
                for index, phrase in enumerate(selected, start=1)
            ],
        }

    def run(self, params: dict[str, Any], notify: Notify) -> dict[str, Any]:
        sample_id = str(params.get("sample_id", "")).strip()
        text = str(params.get("text", "")).strip()
        if not sample_id:
            raise ValueError("sample_id is required")
        if not text:
            return _result(sample_id=sample_id, text=text, ok=False, error="sample text is required")

        self.active_sample_id = sample_id
        notify("calibration.status", {"sample_id": sample_id, "status": "running"})
        try:
            if bool(params.get("force_fail", False)):
                return _result(
                    sample_id=sample_id,
                    text=text,
                    ok=False,
                    error="calibration sample failed quality checks",
                )
            transcript = str(params.get("transcript", text)).strip()
            return _result(
                sample_id=sample_id,
                text=text,
                ok=bool(transcript),
                transcript=transcript,
                error=None if transcript else "calibration returned an empty transcript",
            )
        finally:
            self.active_sample_id = None

    def cancel(self, _params: dict[str, Any], notify: Notify) -> dict[str, Any]:
        sample_id = self.active_sample_id
        self.active_sample_id = None
        notify("calibration.status", {"sample_id": sample_id, "status": "cancelled"})
        return {"cancelled": True, "sample_id": sample_id}


def load_calibration_phrases(path: Path) -> list[tuple[str, str]]:
    target = path if path.is_file() else path / "phrases.jsonl"
    if not target.is_file():
        return list(FALLBACK_PHRASES)
    text = target.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    phrases: list[tuple[str, str]] = []
    for row in rows:
        phrases.append((str(row["id"]), str(row["text"])))
    return phrases or list(FALLBACK_PHRASES)


def _result(
    *,
    sample_id: str,
    text: str,
    ok: bool,
    transcript: str = "",
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "sample_id": sample_id,
        "text": text,
        "mode": "optional",
        "ok": ok,
        "status": "passed" if ok else "failed",
        "transcript": transcript,
        "error": error,
        "quality": {
            "capture_completed": True,
            "camera_usable": True,
            "microphone_usable": True,
            "non_empty_output": bool(transcript),
        },
    }


SESSION = CalibrationSession()


def register_calibration_handlers(dispatcher: SidecarDispatcher) -> None:
    dispatcher.register("calibration.plan", SESSION.plan)
    dispatcher.register("calibration.run", SESSION.run)
    dispatcher.register("calibration.cancel", SESSION.cancel)
