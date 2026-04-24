# Sabi Mouthing Speech

This repo is a **local multimodal PoC**: silent speech via lip reading (Chaplin / Auto-AVSR path) plus an audio baseline (faster-whisper), with optional meeting-mode output (TTS into a virtual mic). Work is tracked as numbered tickets under [`tickets/README.md`](tickets/README.md). Product vision and architecture live in [`project_roadmap.md`](project_roadmap.md).

## Quick start (Windows, PowerShell)

Full dependency order (PyTorch CUDA wheels, then the project) is in **[docs/INSTALL.md](docs/INSTALL.md)**. Short version:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# PyTorch (CUDA or CPU): follow docs/INSTALL.md before or after this step as appropriate
pip install -e ".[dev]"
python -m sabi
```

You should see: `sabi PoC - see tickets/README.md`

Then run **`python -m sabi probe`** to verify camera, microphone, and imports (see INSTALL for CPU-only PyTorch).

## Quick start (Windows, Command Prompt)

Manual activation (same as always):

```bat
cd path\to\Sabi_MouthingSpeech
.\.venv\Scripts\activate.bat
```

Helper scripts in the repo root (run from Explorer or `cmd`):

- **`activate_venv.bat`** — `cd` to the repo and activate `.venv` in the **current** Command Prompt window.
- **`open_cmd_with_venv.bat`** — opens a **new** Command Prompt with the repo folder and `.venv` already activated (handy double-click).

## Dev commands

```powershell
ruff check .
black --check .
pytest
```

## Legacy title

The project was initially named `Sabi_mouthing_speech`; the package name for code is `sabi`.
