"""Thin shim so ``python scripts/mic_monitor.py`` works (TICKET-006)."""

from __future__ import annotations

from sabi.capture.mic_preview import run_mic_preview

if __name__ == "__main__":
    run_mic_preview()
