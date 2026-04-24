"""TICKET-009: clipboard + paste injection tests.

All tests monkeypatch :mod:`pyperclip` so they never touch the real
Windows clipboard (the suite also runs fine on Linux/macOS CI). The
``pyautogui`` Ctrl+V press is replaced by a plain counter via the
``hotkey=`` seam on :func:`paste_text`, so headless runners never steal
focus.
"""

from __future__ import annotations

import time

import pyperclip
import pytest

from sabi.output import InjectConfig, capture_clipboard, paste_text
from sabi.output.inject import _safe_copy


UNICODE_SAMPLES = [
    "naive cafe",
    "na\u00efve caf\u00e9",
    "question?",
    "\u3053\u3093\u306b\u3061\u306f",
    "\U0001F642 smile",
]


@pytest.fixture
def fake_clipboard(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replace pyperclip with an in-memory single-slot clipboard."""
    state: dict[str, str] = {"value": ""}

    def _copy(text: str) -> None:
        state["value"] = text

    def _paste() -> str:
        return state["value"]

    monkeypatch.setattr(pyperclip, "copy", _copy)
    monkeypatch.setattr(pyperclip, "paste", _paste)
    return state


@pytest.mark.parametrize("sample", UNICODE_SAMPLES)
def test_unicode_round_trip_dry_run(
    sample: str, fake_clipboard: dict[str, str]
) -> None:
    """Dry-run paste writes the exact unicode payload to the clipboard."""
    hotkeys: list[None] = []
    cfg = InjectConfig(paste_delay_ms=0, restore_delay_ms=5000, dry_run=True)

    result = paste_text(sample, cfg, hotkey=lambda: hotkeys.append(None))

    assert result.text == sample
    assert result.length == len(sample)
    assert result.error is None
    assert hotkeys == []
    assert fake_clipboard["value"] == sample


def test_restore_preserves_prior_clipboard(
    fake_clipboard: dict[str, str],
) -> None:
    """After restore_delay_ms the prior clipboard contents are back."""
    fake_clipboard["value"] = "user-prior-xyz"
    cfg = InjectConfig(paste_delay_ms=0, restore_delay_ms=50, dry_run=True)

    result = paste_text("payload", cfg, hotkey=lambda: None)
    return_ns = time.monotonic_ns()

    assert fake_clipboard["value"] == "payload"
    assert result.clipboard_restored_at_ns == 0

    assert result.restore_done is not None
    assert result.restore_done.wait(timeout=1.0)

    assert fake_clipboard["value"] == "user-prior-xyz"
    assert result.clipboard_restored_at_ns > return_ns


def test_clipboard_locked_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two PyperclipWindowsException raises -> error='clipboard_locked' and no Ctrl+V."""
    calls = {"copy": 0}

    def _boom(_: str) -> None:
        calls["copy"] += 1
        raise pyperclip.PyperclipWindowsException("locked")

    monkeypatch.setattr(pyperclip, "copy", _boom)
    monkeypatch.setattr(pyperclip, "paste", lambda: "")

    hotkeys: list[None] = []
    cfg = InjectConfig(paste_delay_ms=0, restore_delay_ms=0, dry_run=False)
    result = paste_text("x", cfg, hotkey=lambda: hotkeys.append(None))

    assert result.error == "clipboard_locked"
    assert result.clipboard_restored_at_ns == 0
    assert result.restore_done is None
    assert hotkeys == []
    assert calls["copy"] == 2


def test_safe_copy_retries_once_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call raises, retry succeeds -> _safe_copy returns True."""
    attempts = {"n": 0}

    def _flaky(text: str) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise pyperclip.PyperclipWindowsException("contended")

    monkeypatch.setattr(pyperclip, "copy", _flaky)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    assert _safe_copy("hello") is True
    assert attempts["n"] == 2


def test_capture_clipboard_returns_none_on_empty(
    fake_clipboard: dict[str, str],
) -> None:
    fake_clipboard["value"] = ""
    assert capture_clipboard() is None


def test_capture_clipboard_returns_none_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom() -> str:
        raise pyperclip.PyperclipWindowsException("locked")

    monkeypatch.setattr(pyperclip, "paste", _boom)
    assert capture_clipboard() is None
