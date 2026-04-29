# -*- mode: python ; coding: utf-8 -*-
"""Full CPU PyInstaller spec for dictation-capable runtime packs.

Build this profile from a CPU-only Python environment. Unlike the slim installer
sidecar, this includes ML runtime dependencies needed by silent/audio/fused dictation.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path.cwd()
SPEC_DIR = ROOT / "packaging" / "sidecar"


def existing_tree(path: Path, target: str):
    if path.exists():
        return [(str(path), target)]
    return []


datas = []
datas += existing_tree(ROOT / "configs", "resources/configs")
datas += existing_tree(ROOT / "third_party" / "chaplin", "resources/third_party/chaplin")
datas += existing_tree(
    ROOT / "src" / "sabi" / "cleanup" / "prompts",
    "sabi/cleanup/prompts",
)
datas += collect_data_files("mediapipe")

hiddenimports = [
    "av",
    "cv2",
    "ctranslate2",
    "editdistance",
    "faster_whisper",
    "hydra",
    "keyboard",
    "mediapipe",
    "numpy",
    "omegaconf",
    "pyautogui",
    "pydantic",
    "pyperclip",
    "pytorch_lightning",
    "scipy",
    "sentencepiece",
    "skimage",
    "sounddevice",
    "torch",
    "torchaudio",
    "torchvision",
    "webrtcvad",
]
hiddenimports += collect_submodules("sabi")

a = Analysis(
    [str(SPEC_DIR / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(SPEC_DIR / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib.tests", "pandas.tests", "scipy.tests"],
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
