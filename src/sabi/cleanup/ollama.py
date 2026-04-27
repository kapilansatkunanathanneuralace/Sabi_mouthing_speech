"""Ollama-backed LLM cleanup (TICKET-008).

Responsibilities:

* Clean dictated text (filler removal, casing, punctuation, stutter
  collapse) via a locally hosted Ollama 3B model over the documented
  HTTP API (``/api/tags`` for availability, ``/api/chat`` for cleanup).
* Fail safely: when Ollama is unreachable, slow, or returns garbage, we
  return the raw text unchanged with ``used_fallback=True`` and log a
  single WARNING per :class:`TextCleaner` instance.
* Stay honest about latency: wall-clock ``time.monotonic`` is recorded
  around the HTTP call so :func:`append_latency_row` reflects what the
  pipeline (TICKET-012) will actually pay.
"""

from __future__ import annotations

import json
import logging
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from sabi.cleanup.prompts import load_prompt

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "cleanup.toml"
DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "v1_dictation.txt"

Source = Literal["asr", "vsr", "fused"]
RegisterHint = Literal["dictation", "meeting", "chat"]
PromptVersion = Literal["v1", "v2"]


class CleanupConfig(BaseModel):
    """Configuration for :class:`TextCleaner`."""

    base_url: str = Field(default="http://127.0.0.1:11434")
    model: str = Field(default="llama3.2:3b-instruct-q4_K_M")
    timeout_ms: int = Field(default=800, ge=1)
    availability_timeout_ms: int = Field(default=250, ge=1)
    availability_cache_ms: int = Field(default=5000, ge=0)
    max_output_tokens: int = Field(default=256, ge=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    bypass_on_error: bool = True
    max_growth_factor: float = Field(default=3.0, gt=0.0)
    max_growth_floor: int = Field(default=16, ge=0)
    prompt_version: PromptVersion = "v1"
    prompt_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}


@dataclass(frozen=True)
class CleanupContext:
    """Contextual signals attached to each cleanup call.

    The PoC prompt ignores everything except ``source``; the other fields
    are plumbed so TICKET-011 / TICKET-012 can start populating them and
    a later ticket can teach the prompt to use them.
    """

    source: Source = "asr"
    focused_app: str | None = None
    register_hint: RegisterHint = "dictation"


@dataclass(frozen=True)
class CleanedText:
    """Result of :meth:`TextCleaner.cleanup`."""

    text: str
    latency_ms: float
    used_fallback: bool
    edits: list[tuple[str, str]] | None = None
    reason: str | None = None


def load_cleanup_config(path: Path | None = None) -> CleanupConfig:
    """Load :class:`CleanupConfig` from ``configs/cleanup.toml`` (or defaults)."""
    target = path if path is not None else DEFAULT_CONFIG_PATH
    if not target.is_file():
        return CleanupConfig()
    with target.open("rb") as f:
        data = tomllib.load(f)
    ollama = data.get("ollama", {}) or {}
    limits = data.get("limits", {}) or {}
    merged: dict[str, object] = {}
    if "base_url" in ollama:
        merged["base_url"] = ollama["base_url"]
    if "model" in ollama:
        merged["model"] = ollama["model"]
    for key in (
        "timeout_ms",
        "availability_timeout_ms",
        "availability_cache_ms",
        "max_output_tokens",
        "temperature",
        "bypass_on_error",
        "max_growth_factor",
        "max_growth_floor",
    ):
        if key in limits:
            merged[key] = limits[key]
    prompt = data.get("prompt", {}) or {}
    if "prompt_version" in prompt:
        merged["prompt_version"] = prompt["prompt_version"]
    if "prompt_path" in prompt:
        merged["prompt_path"] = Path(str(prompt["prompt_path"]))
    return CleanupConfig(**merged)


def _load_prompt(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"cleanup system prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


@dataclass
class _AvailabilityCache:
    value: bool | None = None
    timestamp: float = 0.0


class TextCleaner:
    """HTTP client for Ollama's ``/api/chat`` cleanup pass.

    Thread-safety: a single instance holds one :class:`httpx.Client`; call
    :meth:`close` (or use the context manager) to release the connection
    pool. Downstream pipeline tickets instantiate one cleaner per
    process.
    """

    _WARNING_PREFIX = "Ollama cleanup unavailable"

    def __init__(
        self,
        config: CleanupConfig | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config or CleanupConfig()
        self._system_prompt_cache: dict[str, str] = {}
        if self._config.prompt_path is not None:
            self._system_prompt_cache["dictation"] = _load_prompt(self._config.prompt_path)

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                base_url=self._config.base_url,
                timeout=self._config.timeout_ms / 1000.0,
            )
            self._owns_client = True

        self._availability = _AvailabilityCache()
        self._warned_bypass = False
        self._closed = False

    @property
    def config(self) -> CleanupConfig:
        return self._config

    def __enter__(self) -> TextCleaner:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass

    def is_available(self, *, force_refresh: bool = False) -> bool:
        """Ping ``/api/tags`` with a short timeout; cache the answer for 5 s."""
        cache = self._availability
        now = time.monotonic()
        cache_window_s = self._config.availability_cache_ms / 1000.0
        if (
            not force_refresh
            and cache.value is not None
            and (now - cache.timestamp) < cache_window_s
        ):
            return cache.value

        timeout_s = self._config.availability_timeout_ms / 1000.0
        try:
            resp = self._client.get("/api/tags", timeout=timeout_s)
            ok = resp.status_code == 200
        except httpx.HTTPError:
            ok = False
        cache.value = ok
        cache.timestamp = now
        return ok

    def cleanup(self, raw_text: str, context: CleanupContext | None = None) -> CleanedText:
        """Run one cleanup pass. Safe fallback to raw text on any error."""
        ctx = context or CleanupContext()
        raw_text = raw_text or ""
        if not raw_text.strip():
            return CleanedText(
                text=raw_text,
                latency_ms=0.0,
                used_fallback=False,
                reason="empty_input",
            )

        if not self.is_available():
            return self._fallback(raw_text, reason="ollama_unavailable", latency_ms=0.0)

        payload = {
            "model": self._config.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._system_prompt(ctx.register_hint)},
                {
                    "role": "user",
                    "content": self._build_user_message(raw_text, ctx),
                },
            ],
            "options": {
                "num_predict": self._config.max_output_tokens,
                "temperature": self._config.temperature,
            },
        }

        start = time.monotonic()
        timeout_s = self._config.timeout_ms / 1000.0
        try:
            resp = self._client.post("/api/chat", json=payload, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            latency_ms = (time.monotonic() - start) * 1000.0
            return self._fallback(
                raw_text,
                reason=f"http_error: {exc.__class__.__name__}",
                latency_ms=latency_ms,
            )
        except json.JSONDecodeError:
            latency_ms = (time.monotonic() - start) * 1000.0
            return self._fallback(
                raw_text,
                reason="json_decode_error",
                latency_ms=latency_ms,
            )

        latency_ms = (time.monotonic() - start) * 1000.0
        cleaned = _extract_message_content(data)
        if cleaned is None:
            return self._fallback(
                raw_text,
                reason="missing_message_content",
                latency_ms=latency_ms,
            )

        if self._is_hallucinated(raw_text, cleaned):
            return self._fallback(
                raw_text,
                reason="output_too_long",
                latency_ms=latency_ms,
            )

        return CleanedText(
            text=cleaned,
            latency_ms=latency_ms,
            used_fallback=False,
            edits=None,
            reason=None,
        )

    def _system_prompt(self, register: str) -> str:
        """Resolve the configured prompt for the requested cleanup register."""

        key = register.strip().lower()
        if key not in self._system_prompt_cache:
            self._system_prompt_cache[key] = load_prompt(self._config.prompt_version, key)
        return self._system_prompt_cache[key]

    def _fallback(
        self,
        raw_text: str,
        *,
        reason: str,
        latency_ms: float,
    ) -> CleanedText:
        if self._config.bypass_on_error:
            self._warn_once(reason)
            return CleanedText(
                text=raw_text,
                latency_ms=latency_ms,
                used_fallback=True,
                reason=reason,
            )
        raise RuntimeError(f"Ollama cleanup failed ({reason}) and bypass_on_error=False")

    def _warn_once(self, reason: str) -> None:
        if self._warned_bypass:
            return
        self._warned_bypass = True
        logger.warning(
            "%s (%s); returning raw text unchanged for this run.",
            self._WARNING_PREFIX,
            reason,
        )

    def _build_user_message(self, raw_text: str, context: CleanupContext) -> str:
        header = json.dumps(
            {
                "source": context.source,
                "focused_app": context.focused_app,
                "register_hint": context.register_hint,
            },
            ensure_ascii=False,
        )
        return (
            f"Context: {header}\n"
            f"Raw text:\n{raw_text.strip()}\n\n"
            "Return only the cleaned text."
        )

    def _is_hallucinated(self, raw_text: str, cleaned: str) -> bool:
        if len(raw_text) <= self._config.max_growth_floor:
            return False
        limit = int(len(raw_text) * self._config.max_growth_factor)
        return len(cleaned) > max(limit, self._config.max_growth_floor)


def _extract_message_content(payload: dict) -> str | None:
    """Pull the assistant message out of an Ollama ``/api/chat`` response."""
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        return None
    return content.strip()


__all__ = [
    "CleanedText",
    "CleanupConfig",
    "CleanupContext",
    "TextCleaner",
    "load_cleanup_config",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_PROMPT_PATH",
    "PromptVersion",
]
