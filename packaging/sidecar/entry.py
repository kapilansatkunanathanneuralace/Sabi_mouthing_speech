"""Frozen entry point for the Sabi Python sidecar."""

from __future__ import annotations

import logging
import sys

from sabi.sidecar.server import run_stdio_server


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    return run_stdio_server()


if __name__ == "__main__":
    raise SystemExit(main())
