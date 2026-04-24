# Install (Windows)

Use **Python 3.11 (64-bit)** for the pinned dependency stack (see `.python-version`). Newer Python versions may not have matching `torch==2.3.1` CUDA wheels; use the CPU fallback below if `pip` cannot resolve PyTorch.

## One-time setup (PowerShell)

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

**PyTorch (pick one track)**

- **Python 3.11 + CUDA 12.1 (ticket baseline):**  
  `pip install torch==2.3.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121`
- **Newer Python (e.g. 3.12+) or when cu121 wheels are missing:** install the pair recommended for your OS/Python from [pytorch.org](https://pytorch.org/get-started/locally/), then continue.

Then install this repo:

```powershell
pip install -e ".[dev]"
```

Then verify hardware and imports:

```powershell
python -m sabi probe
```

## CPU-only PyTorch (no CUDA)

If you do not need a GPU or the CUDA wheel line fails:

```powershell
pip install torch torchaudio
pip install -e ".[dev]"
```

The probe will print a yellow warning when CUDA is not available; it still exits **0** if camera, microphone, and imports succeed.

## Camera and microphone (Windows)

Allow desktop apps under **Settings > Privacy & security > Camera** and **Microphone**. If `python -m sabi probe` fails to open the webcam, close other apps using the camera and retry. `python -m sabi mic-preview` (TICKET-006) opens the default input device at 16 kHz mono and raises `MicUnavailableError` if microphone access is blocked.

### Optional VAD fallback (TICKET-006)

`sabi.capture.microphone` prefers `webrtcvad` (bundled via `webrtcvad-wheels`). If that import ever fails, it transparently falls back to `silero-vad`, which is **not** installed by default. Install it only if you need the fallback path:

```powershell
pip install silero-vad
```

The selected backend is exposed as `MicrophoneSource.backend` (`"webrtcvad"` or `"silero"`).

## Ollama

Ollama is **not** installed in this ticket. See **TICKET-008** for the LLM cleanup service.

## Dependency notes (vs ticket text)

The ticket pins exact versions for a **Python 3.11 + CUDA 12.1** stack. This repo relaxes a few bounds so installs still resolve on newer CPython (for example 3.14) and when PyPI stops publishing older wheels:

- **mediapipe** / **sounddevice** / **faster-whisper** / **numpy** / **torch** / **pydantic** / **httpx** / **rich** / **typer** may float within the ranges declared in `pyproject.toml`.
- For reproducible ML experiments, create a **Python 3.11** venv and follow the **CUDA 12.1** torch line above, then commit a lockfile when you introduce one (uv/poetry).

## Optional: run probe as a script

With the venv activated and the package installed:

```powershell
python scripts/probe_env.py
python scripts/probe_env.py --camera-index 1
```
