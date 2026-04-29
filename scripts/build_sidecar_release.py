"""Build and smoke-test the pruned PyInstaller sidecar for desktop installers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_sidecar import _dir_size, _format_size, _smoke, audit_bundle  # noqa: E402

SPEC = ROOT / "packaging" / "sidecar" / "sabi_sidecar_release.spec"
DIST = ROOT / "packaging" / "sidecar" / "release-dist"
BUILD = ROOT / "packaging" / "sidecar" / "release-build"
DIST_ROOT = DIST / "sabi-sidecar"
SIZE_LIMIT_MB = 250


def _run_build() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)


def _sidecar_bin() -> Path:
    exe_name = "sabi-sidecar.exe" if sys.platform == "win32" else "sabi-sidecar"
    binary = DIST_ROOT / exe_name
    if not binary.is_file():
        raise FileNotFoundError(f"sidecar binary not found: {binary}")
    return binary


def _probe_smoke(binary: Path) -> dict:
    proc = subprocess.run(
        [str(binary)],
        input='{"jsonrpc":"2.0","id":2,"method":"cache.status","params":{"manifest":"cleanup"}}\n',
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"release sidecar cache smoke failed with exit {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"release sidecar cache smoke produced no stdout; stderr={proc.stderr}")
    return json.loads(lines[-1])


def main() -> int:
    _run_build()
    binary = _sidecar_bin()
    meta = _smoke(binary)
    cache = _probe_smoke(binary)
    size = _dir_size(DIST_ROOT)
    size_mb = size / (1024 * 1024)
    print(f"sidecar_root : {DIST_ROOT}")
    print(f"sidecar_bin  : {binary}")
    print(f"bundle_size  : {size_mb:.1f} MB")
    print("largest_entries:")
    for entry_size, path in audit_bundle(DIST_ROOT):
        print(f"  {_format_size(entry_size):>10}  {path.relative_to(DIST_ROOT)}")
    print("largest_directories:")
    for entry_size, path in audit_bundle(DIST_ROOT, recursive=True):
        print(f"  {_format_size(entry_size):>10}  {path.relative_to(DIST_ROOT)}")
    print(f"smoke_meta   : {json.dumps(meta, separators=(',', ':'))}")
    print(f"smoke_cache  : {json.dumps(cache, separators=(',', ':'))}")
    if size_mb > SIZE_LIMIT_MB:
        raise SystemExit(
            f"release sidecar exceeds {SIZE_LIMIT_MB} MB limit: {_format_size(size)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
