"""Clipboard + paste injection (TICKET-009).

The last step of both dictation pipelines. ``paste_text`` saves the user's
existing clipboard, writes the cleaned text, triggers Ctrl+V in the
focused window, and restores the prior clipboard on a background thread
so we do not pollute the user's clipboard history.

Windows-only for the PoC. The module imports ``pyautogui`` lazily so that
headless CI runners (and the unit tests in :mod:`tests.test_inject_unicode`)
never attempt to load a display.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

import pyperclip
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class InjectConfig(BaseModel):
    """Configuration for :func:`paste_text`."""

    paste_delay_ms: int = Field(default=15, ge=0)
    restore_delay_ms: int = Field(default=400, ge=0)
    dry_run: bool = False


@dataclass
class InjectResult:
    """Outcome of a single :func:`paste_text` call.

    ``clipboard_restored_at_ns`` is written by the background restore
    thread (``time.monotonic_ns`` at the moment ``pyperclip.copy`` returns)
    so callers / tests can assert ordering without blocking the hot path.
    A value of ``0`` means restore has not completed yet (or was skipped).
    """

    text: str
    length: int
    latency_ms: float
    clipboard_restored_at_ns: int = 0
    error: str | None = None
    restore_done: threading.Event | None = None


def capture_clipboard() -> str | None:
    """Return current clipboard text, or ``None`` when empty / unreadable.

    Callers treat ``None`` as "nothing worth restoring".
    """
    try:
        value = pyperclip.paste()
    except pyperclip.PyperclipWindowsException:
        logger.warning("capture_clipboard: Windows clipboard locked", exc_info=True)
        return None
    except Exception:
        logger.warning("capture_clipboard: unexpected failure", exc_info=True)
        return None
    if not isinstance(value, str) or value == "":
        return None
    return value


def _safe_copy(text: str) -> bool:
    """Copy ``text`` to the clipboard with one 50 ms retry on Windows lock.

    Returns ``True`` on success, ``False`` if both attempts raise
    :class:`pyperclip.PyperclipWindowsException`. Other exceptions
    propagate so real bugs are not silently swallowed.
    """
    try:
        pyperclip.copy(text)
        return True
    except pyperclip.PyperclipWindowsException:
        logger.warning("clipboard copy contended, retrying in 50 ms")
        time.sleep(0.05)
    try:
        pyperclip.copy(text)
        return True
    except pyperclip.PyperclipWindowsException:
        logger.error("clipboard copy failed after retry", exc_info=True)
        return False


def _hotkey_ctrl_v() -> None:
    """Press Ctrl+V in the focused window via pyautogui.

    Imported lazily so tests never touch the GUI layer; callers already
    check ``InjectConfig.dry_run`` before invoking this.
    """
    import pyautogui

    pyautogui.hotkey("ctrl", "v")


def paste_text(
    text: str,
    config: InjectConfig | None = None,
    *,
    hotkey: Callable[[], None] | None = None,
) -> InjectResult:
    """Paste ``text`` into the focused window via the clipboard.

    ``hotkey`` is a seam for tests: pass a no-op ``lambda: None`` and
    ``dry_run=True`` to avoid touching real input. Production callers
    leave it ``None`` so the default :func:`_hotkey_ctrl_v` runs.
    """
    cfg = config or InjectConfig()
    t0 = time.perf_counter()

    prior = capture_clipboard()

    if not _safe_copy(text):
        latency_ms = (time.perf_counter() - t0) * 1000.0
        logger.error("paste_text: clipboard locked, skipping Ctrl+V and restore")
        return InjectResult(
            text=text,
            length=len(text),
            latency_ms=latency_ms,
            error="clipboard_locked",
        )

    if cfg.paste_delay_ms > 0:
        time.sleep(cfg.paste_delay_ms / 1000.0)

    if cfg.dry_run:
        logger.info("paste_text: dry_run=True, skipping Ctrl+V")
    else:
        try:
            (hotkey or _hotkey_ctrl_v)()
        except Exception:
            logger.warning("paste_text: Ctrl+V hotkey failed", exc_info=True)

    latency_ms = (time.perf_counter() - t0) * 1000.0
    result = InjectResult(
        text=text,
        length=len(text),
        latency_ms=latency_ms,
        restore_done=threading.Event(),
    )

    restore_payload = prior if prior is not None else ""

    def _restore() -> None:
        time.sleep(cfg.restore_delay_ms / 1000.0)
        if _safe_copy(restore_payload):
            result.clipboard_restored_at_ns = time.monotonic_ns()
        else:
            logger.error("paste_text: failed to restore prior clipboard")
        assert result.restore_done is not None
        result.restore_done.set()

    threading.Thread(target=_restore, name="sabi-clipboard-restore", daemon=True).start()
    return result


__all__ = [
    "InjectConfig",
    "InjectResult",
    "capture_clipboard",
    "paste_text",
]
