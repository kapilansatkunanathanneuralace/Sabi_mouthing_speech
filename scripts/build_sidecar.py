"""Build and smoke-test the PyInstaller Sabi sidecar."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "sidecar" / "sabi_sidecar.spec"
DIST_ROOT = ROOT / "packaging" / "sidecar" / "dist" / "sabi-sidecar"
REQUEST = {"jsonrpc": "2.0", "id": 1, "method": "meta.version"}
AUDIT_LIMIT = 20


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _top_level_sizes(root: Path) -> Iterable[tuple[int, Path]]:
    for item in root.iterdir():
        if item.is_file():
            yield item.stat().st_size, item
        elif item.is_dir():
            yield _dir_size(item), item


def _directory_sizes(root: Path) -> Iterable[tuple[int, Path]]:
    for item in root.rglob("*"):
        if item.is_dir():
            yield _dir_size(item), item


def audit_bundle(
    root: Path,
    *,
    limit: int = AUDIT_LIMIT,
    recursive: bool = False,
) -> list[tuple[int, Path]]:
    """Return largest bundle entries for packaging size triage."""

    if not root.exists():
        return []
    iterator = _directory_sizes(root) if recursive else _top_level_sizes(root)
    return sorted(iterator, reverse=True, key=lambda row: row[0])[:limit]


def _sidecar_bin() -> Path:
    exe = DIST_ROOT / ("sabi-sidecar.exe" if os.name == "nt" else "sabi-sidecar")
    if exe.is_file():
        return exe
    raise FileNotFoundError(f"sidecar binary not found: {exe}")


def _check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PyInstaller is not installed. Run: pip install -e \".[packaging]\""
        ) from exc


def _run_build() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--distpath",
        str(ROOT / "packaging" / "sidecar" / "dist"),
        "--workpath",
        str(ROOT / "packaging" / "sidecar" / "build"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)


def _smoke(binary: Path) -> dict:
    proc = subprocess.run(
        [str(binary)],
        input=json.dumps(REQUEST) + "\n",
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"sidecar smoke failed with exit {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"sidecar smoke produced no stdout; stderr={proc.stderr}")
    payload = json.loads(lines[-1])
    version = payload.get("result", {}).get("protocol_version")
    if version != "1.0.0":
        raise RuntimeError(f"unexpected sidecar response: {payload}")
    return payload


def main() -> int:
    _check_pyinstaller()
    _run_build()
    binary = _sidecar_bin()
    response = _smoke(binary)
    size_mb = _dir_size(DIST_ROOT) / (1024 * 1024)
    print(f"sidecar_root : {DIST_ROOT}")
    print(f"sidecar_bin  : {binary}")
    print(f"bundle_size  : {size_mb:.1f} MB")
    print("largest_entries:")
    for size, path in audit_bundle(DIST_ROOT):
        print(f"  {_format_size(size):>10}  {path.relative_to(DIST_ROOT)}")
    print("largest_directories:")
    for size, path in audit_bundle(DIST_ROOT, recursive=True):
        print(f"  {_format_size(size):>10}  {path.relative_to(DIST_ROOT)}")
    print(f"smoke        : {json.dumps(response, separators=(',', ':'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
