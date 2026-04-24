"""Thin shim so `python scripts/lip_roi_debug.py` works (TICKET-004)."""

from __future__ import annotations

from sabi.capture.lip_preview import run_lip_preview

if __name__ == "__main__":
    run_lip_preview()
