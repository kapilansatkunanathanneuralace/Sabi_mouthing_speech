"""Build and package the full CPU sidecar runtime pack."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_sidecar import _dir_size, _format_size, _smoke, audit_bundle  # noqa: E402

SPEC = ROOT / "packaging" / "sidecar" / "sabi_sidecar_full_cpu.spec"
DIST = ROOT / "packaging" / "sidecar" / "full-cpu-dist"
BUILD = ROOT / "packaging" / "sidecar" / "full-cpu-build"
DIST_ROOT = DIST / "sabi-sidecar"
ARTIFACT_ROOT = ROOT / "packaging" / "sidecar" / "runtime-packs"
RUNTIME_NAME = "sabi-full-cpu-runtime"
RUNTIME_VERSION = "0.0.1"
MIN_DESKTOP_VERSION = "0.0.1"


def _platform_key() -> str:
    if sys.platform == "win32":
        return "win"
    if sys.platform == "darwin":
        return "macos"
    return sys.platform


def _arch_key() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    return machine or ("x64" if sys.maxsize > 2**32 else "x86")


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


def _rpc(binary: Path, method: str, params: dict | None = None, timeout: int = 60) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    proc = subprocess.run(
        [str(binary)],
        input=json.dumps(payload, separators=(",", ":")) + "\n",
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"sidecar {method} smoke failed with exit {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"expected one JSON line from {method}, got {len(lines)}: {proc.stdout}")
    return json.loads(lines[0])


def _assert_probe_ready(probe: dict) -> None:
    probe_result = probe.get("result", {}).get("probe", {})
    torch_result = probe_result.get("torch", {})
    imports = {
        row.get("module"): row
        for row in probe_result.get("imports", [])
        if isinstance(row, dict)
    }
    required_imports = ("mediapipe", "faster_whisper", "typer")
    missing = [
        name
        for name in required_imports
        if not bool(imports.get(name, {}).get("ok"))
    ]
    if not bool(torch_result.get("ok")):
        missing.append(f"torch: {torch_result.get('error', 'unknown error')}")
    if missing:
        raise RuntimeError(f"full CPU runtime probe failed required checks: {', '.join(missing)}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_runtime_metadata() -> dict[str, object]:
    metadata = {
        "name": RUNTIME_NAME,
        "version": RUNTIME_VERSION,
        "platform": sys.platform,
        "arch": _arch_key(),
        "min_desktop_version": MIN_DESKTOP_VERSION,
        "sidecar_dir": "sabi-sidecar",
    }
    (DIST_ROOT / "runtime-pack.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def _make_zip(metadata: dict[str, object]) -> dict[str, object]:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    target = f"{_platform_key()}-{_arch_key()}"
    base_name = ARTIFACT_ROOT / f"{RUNTIME_NAME}-{RUNTIME_VERSION}-{target}"
    zip_path = Path(shutil.make_archive(str(base_name), "zip", root_dir=DIST))
    manifest = {
        **metadata,
        "artifact": zip_path.name,
        "size_bytes": zip_path.stat().st_size,
        "sha256": _sha256(zip_path),
    }
    manifest_path = ARTIFACT_ROOT / f"{RUNTIME_NAME}-{RUNTIME_VERSION}-{target}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"zip_path": zip_path, "manifest_path": manifest_path, "manifest": manifest}


def main() -> int:
    _run_build()
    binary = _sidecar_bin()
    metadata = _write_runtime_metadata()
    meta = _smoke(binary)
    probe = _rpc(binary, "probe.run", {"camera_index": 0}, timeout=120)
    _assert_probe_ready(probe)
    size = _dir_size(DIST_ROOT)
    artifact = _make_zip(metadata)

    print(f"sidecar_root : {DIST_ROOT}")
    print(f"sidecar_bin  : {binary}")
    print(f"bundle_size  : {_format_size(size)}")
    print("largest_directories:")
    for entry_size, path in audit_bundle(DIST_ROOT, recursive=True):
        print(f"  {_format_size(entry_size):>10}  {path.relative_to(DIST_ROOT)}")
    print(f"smoke_meta   : {json.dumps(meta, separators=(',', ':'))}")
    print(f"smoke_probe  : failures={probe.get('result', {}).get('probe', {}).get('failures')}")
    print(f"runtime_zip  : {artifact['zip_path']}")
    print(f"manifest     : {artifact['manifest_path']}")
    print(f"sha256       : {artifact['manifest']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
