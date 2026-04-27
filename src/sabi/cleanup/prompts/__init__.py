"""Versioned cleanup prompt resolver (TICKET-018)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent
PromptVersion = str
PromptRegister = str

_PROMPT_PATHS: dict[tuple[PromptVersion, PromptRegister], Path] = {
    ("v1", "dictation"): PROMPT_DIR / "v1_dictation.txt",
    ("v2", "dictation"): PROMPT_DIR / "v2_dictation.txt",
}


def resolve_prompt_path(version: str, register: str) -> Path:
    """Return the prompt path for a cleanup prompt version/register pair."""

    key = (version.strip().lower(), register.strip().lower())
    try:
        path = _PROMPT_PATHS[key]
    except KeyError as exc:
        known = ", ".join(f"{v}/{r}" for v, r in sorted(_PROMPT_PATHS))
        raise ValueError(
            f"unknown cleanup prompt version/register {key[0]!r}/{key[1]!r}; "
            f"known prompts: {known}"
        ) from exc
    if not path.is_file():
        raise FileNotFoundError(f"cleanup system prompt not found: {path}")
    return path


@lru_cache(maxsize=16)
def load_prompt(version: str, register: str) -> str:
    """Load and cache a cleanup prompt by version/register."""

    return resolve_prompt_path(version, register).read_text(encoding="utf-8").strip()


__all__ = [
    "PROMPT_DIR",
    "load_prompt",
    "resolve_prompt_path",
]
