"""Download + verify Chaplin VSR weights (TICKET-005).

Importable alongside ``scripts/download_vsr_weights.py`` so the ``sabi`` CLI
can delegate without poking at ``scripts/`` at runtime (``scripts/`` is not on
``sys.path`` in an installed package).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import urllib.request
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    import tomli as tomllib  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

# Repo root = parents[4]: download.py -> vsr -> models -> sabi -> src -> <root>.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MANIFEST = REPO_ROOT / "configs" / "vsr_weights.toml"
DEFAULT_DEST_ROOT = REPO_ROOT / "data" / "models" / "vsr"
CHUNK = 1 << 20  # 1 MiB


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    logger.info("downloading %s -> %s", url, dest)
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(dest)


def download_all(
    manifest_path: Path = DEFAULT_MANIFEST,
    dest_root: Path = DEFAULT_DEST_ROOT,
    force: bool = False,
    print_hashes: bool = False,
) -> int:
    """Download every file listed under ``[[files]]``.

    Returns 0 on success, non-zero on any hash mismatch or IO failure.
    """
    if not manifest_path.is_file():
        logger.error("manifest not found: %s", manifest_path)
        return 2
    manifest = _load_manifest(manifest_path)
    files = manifest.get("files", [])
    if not files:
        logger.error("manifest %s has no [[files]] entries", manifest_path)
        return 2

    exit_code = 0
    computed: dict[str, str] = {}
    for entry in files:
        name = entry.get("name") or entry.get("relative_path", "?")
        url = entry["url"]
        rel = Path(entry["relative_path"])
        expected = (entry.get("sha256") or "").strip().lower()
        dest = dest_root / rel

        if dest.exists() and not force:
            logger.info("[%s] already present: %s", name, dest)
        else:
            if dest.exists() and force:
                logger.info("[%s] --force: overwriting %s", name, dest)
            try:
                _download(url, dest)
            except Exception as exc:  # noqa: BLE001 - report and continue
                logger.error("[%s] download failed: %s", name, exc)
                exit_code = 1
                continue

        digest = _sha256_file(dest)
        computed[name] = digest
        if expected:
            if digest != expected:
                logger.error(
                    "[%s] sha256 mismatch: expected %s got %s",
                    name,
                    expected,
                    digest,
                )
                exit_code = 1
            else:
                logger.info("[%s] sha256 ok", name)
        else:
            logger.warning(
                "[%s] no sha256 pinned in manifest; computed %s",
                name,
                digest,
            )

    if print_hashes:
        print("\n# Paste these sha256 values into configs/vsr_weights.toml:")
        for name, digest in computed.items():
            print(f'{name} = "{digest}"')

    return exit_code


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
