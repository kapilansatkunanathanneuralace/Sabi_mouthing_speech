"""Resolve runtime paths in both repo and packaged desktop layouts.

The CLI still defaults to the repository layout. Packaged builds can override
individual roots with ``SABI_*`` environment variables without changing callers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def frozen_resource_root() -> Path | None:
    """Return bundled read-only resource root when running under PyInstaller."""

    if not getattr(sys, "frozen", False):
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = []
    if meipass:
        candidates.append(Path(meipass) / "resources")
    candidates.append(Path(sys.executable).resolve().parent / "resources")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def repo_root() -> Path:
    """Return the source checkout root used by developer/CLI workflows."""

    override = _env_path("SABI_REPO_ROOT")
    if override is not None:
        return override
    frozen_root = frozen_resource_root()
    if frozen_root is not None:
        return frozen_root
    # paths.py -> runtime -> sabi -> src -> repo
    return Path(__file__).resolve().parents[3]


def app_home() -> Path:
    """Return writable app data root for packaged runtime state."""

    override = _env_path("SABI_APP_HOME")
    if override is not None:
        return override
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Sabi"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Sabi"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".local" / "share") / "sabi"


def configs_dir() -> Path:
    override = _env_path("SABI_CONFIG_DIR")
    if override is not None:
        return override
    frozen_root = frozen_resource_root()
    return (frozen_root / "configs") if frozen_root is not None else repo_root() / "configs"


def manifests_dir() -> Path:
    override = _env_path("SABI_MANIFESTS_DIR")
    return override if override is not None else configs_dir() / "manifests"


def data_dir() -> Path:
    override = _env_path("SABI_DATA_DIR")
    return override if override is not None else app_home() / "data"


def models_dir() -> Path:
    override = _env_path("SABI_MODELS_DIR")
    return override if override is not None else app_home() / "models"


def reports_dir() -> Path:
    override = _env_path("SABI_REPORTS_DIR")
    if override is not None:
        return override
    if frozen_resource_root() is not None:
        return app_home() / "reports"
    return repo_root() / "reports"


def chaplin_dir() -> Path:
    override = _env_path("SABI_CHAPLIN_DIR")
    if override is not None:
        return override
    frozen_root = frozen_resource_root()
    root = frozen_root if frozen_root is not None else repo_root()
    return root / "third_party" / "chaplin"


def vsr_manifest_path() -> Path:
    override = _env_path("SABI_VSR_MANIFEST")
    return override if override is not None else configs_dir() / "vsr_weights.toml"
