"""Resolve + expose the vendored Chaplin source tree (TICKET-005).

Chaplin lives at ``third_party/chaplin`` as a git submodule. It ships its own
trimmed copy of ``espnet`` alongside ``pipelines/``, so we only need to
prepend the submodule root to ``sys.path`` before importing
``pipelines.model`` and ``espnet.*``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
CHAPLIN_ROOT = REPO_ROOT / "third_party" / "chaplin"
DEFAULT_INI = CHAPLIN_ROOT / "configs" / "LRS3_V_WER19.1.ini"


class ChaplinNotAvailable(RuntimeError):
    """Raised when the ``third_party/chaplin`` submodule has not been initialised."""


def ensure_on_path() -> Path:
    """Prepend the Chaplin submodule to ``sys.path`` and return its root.

    Raises :class:`ChaplinNotAvailable` with a helpful message if the submodule
    is missing; surfacing that as a hard error is intentional so operators see
    ``git submodule update --init --recursive`` guidance immediately.
    """
    if not CHAPLIN_ROOT.is_dir() or not (CHAPLIN_ROOT / "pipelines" / "model.py").is_file():
        raise ChaplinNotAvailable(
            "third_party/chaplin is missing. Run:\n" "    git submodule update --init --recursive"
        )
    path = str(CHAPLIN_ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)
    return CHAPLIN_ROOT
