# -*- mode: python ; coding: utf-8 -*-
"""Pruned PyInstaller spec for desktop installer smoke/release builds.

This profile keeps the JSON-RPC sidecar, onboarding probe, and cache APIs working
without eagerly collecting every ML pipeline and CUDA dependency from the dev venv.
Build full inference release sidecars from a CPU-only environment once distribution
dependencies are pinned.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path.cwd()
SPEC_DIR = ROOT / "packaging" / "sidecar"


def existing_tree(path: Path, target: str):
    if path.exists():
        return [(str(path), target)]
    return []


datas = []
datas += existing_tree(ROOT / "configs", "resources/configs")
datas += existing_tree(
    ROOT / "src" / "sabi" / "cleanup" / "prompts",
    "resources/sabi/cleanup/prompts",
)
datas += collect_data_files("cv2")

hiddenimports = [
    "cv2",
    "numpy",
    "pydantic",
    "rich",
    "sounddevice",
    "sabi.sidecar.server",
    "sabi.sidecar.dispatcher",
    "sabi.sidecar.protocol",
    "sabi.sidecar.handlers",
    "sabi.sidecar.handlers.cache",
    "sabi.sidecar.handlers.dictation",
    "sabi.sidecar.handlers.eval",
    "sabi.sidecar.handlers.meta",
    "sabi.sidecar.handlers.models",
    "sabi.sidecar.handlers.probe",
    "sabi.runtime.asset_cache",
    "sabi.runtime.paths",
]

excludes = [
    "av",
    "faster_whisper",
    "matplotlib",
    "mediapipe",
    "onnxruntime",
    "pandas",
    "pytorch_lightning",
    "scipy",
    "skimage",
    "sympy",
    "torch",
    "torchaudio",
    "torchvision",
    "triton",
]

a = Analysis(
    [str(SPEC_DIR / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(SPEC_DIR / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sabi-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="sabi-sidecar",
)
