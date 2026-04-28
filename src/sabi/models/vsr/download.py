"""Download + verify Chaplin VSR weights (TICKET-005).

Importable alongside ``scripts/download_vsr_weights.py`` so the ``sabi`` CLI
can delegate without poking at ``scripts/`` at runtime (``scripts/`` is not on
``sys.path`` in an installed package).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Callable

from sabi.runtime.asset_cache import AssetCache, AssetManifest
from sabi.runtime.paths import models_dir, vsr_manifest_path

logger = logging.getLogger(__name__)

DEFAULT_MANIFEST = vsr_manifest_path()
DEFAULT_DEST_ROOT = models_dir() / "vsr"


ProgressCallback = Callable[[dict[str, Any]], None]


def download_all(
    manifest_path: Path = DEFAULT_MANIFEST,
    dest_root: Path = DEFAULT_DEST_ROOT,
    force: bool = False,
    print_hashes: bool = False,
    progress: ProgressCallback | None = None,
) -> int:
    """Download every file listed under ``[[files]]``.

    Returns 0 on success, non-zero on any hash mismatch or IO failure.
    """
    if not manifest_path.is_file():
        logger.error("manifest not found: %s", manifest_path)
        return 2
    try:
        manifest = AssetManifest.load(manifest_path).model_copy(update={"name": dest_root.name})
    except Exception as exc:  # noqa: BLE001 - CLI reports validation failures as exit code
        logger.error("manifest %s is invalid: %s", manifest_path, exc)
        return 2

    cache = AssetCache(app_home=dest_root.parent)
    try:
        status = cache.ensure_manifest(manifest, force=force, progress=progress, migrate=False)
    except Exception as exc:  # noqa: BLE001 - report and keep CLI exit-code contract
        logger.error("download failed: %s", exc)
        return 1

    if print_hashes:
        print("\n# Paste these sha256 values into configs/vsr_weights.toml:")
        for entry in status["entries"]:
            if entry.get("sha256"):
                print(f'{entry["name"]} = "{entry["sha256"]}"')

    return 0 if status["status"] == "present" else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Chaplin VSR weights.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to vsr_weights.toml (default: configs/vsr_weights.toml).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST_ROOT,
        help="Destination root (default: data/models/vsr).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload files that already exist on disk.",
    )
    parser.add_argument(
        "--print-hashes",
        action="store_true",
        help="Print the sha256 of every resulting file in TOML form.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_arg_parser().parse_args(argv)
    return download_all(
        manifest_path=args.manifest,
        dest_root=args.dest,
        force=args.force,
        print_hashes=args.print_hashes,
    )
