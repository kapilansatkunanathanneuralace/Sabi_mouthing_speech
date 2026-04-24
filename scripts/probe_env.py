"""Thin shim so `python scripts/probe_env.py` works (TICKET-002)."""

from __future__ import annotations

from sabi.probe import main

if __name__ == "__main__":
    raise SystemExit(main())
