"""Thin shim so `python scripts/webcam_viewer.py` works (TICKET-003)."""

from __future__ import annotations

from sabi.capture.preview import run_cam_preview

if __name__ == "__main__":
    run_cam_preview()
