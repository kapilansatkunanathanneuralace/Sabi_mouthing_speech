"""Thin wrapper around ``sabi.models.vsr.download`` for direct CLI use.

Exists so operators on a machine without ``sabi`` installed (e.g. fresh clone
before ``pip install -e .``) can still ``python scripts/download_vsr_weights.py``
from the repo root.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_path() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    _bootstrap_path()
    from sabi.models.vsr.download import main as _main

    return _main()


if __name__ == "__main__":
    sys.exit(main())
