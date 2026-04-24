# TICKET-002 - Core dependencies & env probe

Phase: 1 - ML PoC
Epic: Infra
Estimate: M
Depends on: TICKET-001
Status: Not started

## Goal

Pin every third-party runtime dependency the ML PoC needs and ship a `scripts/probe_env.py` that proves, on a fresh clone, that: Python, CUDA/torch, the webcam, and the default microphone all work. Running the probe is the first thing any downstream ticket requires.

## System dependencies

- Python 3.11 (from TICKET-001).
- Windows: a working NVIDIA driver if GPU inference is desired (CUDA 12.1 wheel line assumed). CPU-only fallback must still let the probe pass with a warning.
- A connected webcam and microphone. Windows privacy settings must allow apps to access both.
- Ollama is **not** installed here - it belongs to TICKET-008.

## Python packages

Add to `pyproject.toml` `[project].dependencies` with exact version pins. Reference versions (update at implementation time if newer is stable):

- `opencv-python==4.10.0.84` - webcam capture (TICKET-003).
- `mediapipe==0.10.14` - face landmarks for lip ROI (TICKET-004).
- `numpy>=1.26,<2.1` - pinned ceiling because mediapipe + torch are sensitive to NumPy 2.x at time of writing.
- `torch==2.3.1` and `torchaudio==2.3.1` - installed via the CUDA 12.1 index URL on Windows (`--index-url https://download.pytorch.org/whl/cu121`). Required by Chaplin/Auto-AVSR (TICKET-005). Torchaudio is also useful for ASR post-processing.
- `faster-whisper==1.0.3` - ASR baseline (TICKET-007).
- `sounddevice==0.4.7` - mic capture (TICKET-006).
- `webrtcvad-wheels==2.0.14` - VAD gate (TICKET-006). If a wheel is unavailable, fall back to `silero-vad` via `torch.hub` - note which was used in the env probe output.
- `pyautogui==0.9.54` and `pyperclip==1.9.0` - text injection (TICKET-009).
- `keyboard==0.13.5` - global hotkey (TICKET-010).
- `pydantic==2.8.2` - config schema across tickets.
- `httpx==0.27.0` - Ollama client (TICKET-008).
- `rich==13.7.1` - overlay TUI (TICKET-013) and probe output formatting.
- `typer==0.12.3` - CLI backbone (supersedes the argparse stub from TICKET-001).

Dev-only additions:

- `pytest-timeout==2.3.1` - to guard against probes that hang.

Document the Windows-specific install line in `docs/INSTALL.md`:

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install torch==2.3.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121
pip install -e .[dev]
```

## Work

- Update `pyproject.toml` with the pinned `dependencies` and `optional-dependencies.dev` lists above.
- Replace the argparse stub in `src/sabi/cli.py` with a Typer app that already registers empty `silent-dictate`, `dictate`, and `probe` subcommands (the real bodies land in later tickets).
- Write `scripts/probe_env.py`:
  - Prints Python version, OS, CPU count.
  - Imports torch; prints `torch.__version__`, `torch.cuda.is_available()`, device name, VRAM if CUDA is available.
  - Opens webcam index 0 with OpenCV, grabs one frame, prints resolution, releases. Fails loudly with a remediation hint ("Windows Privacy > Camera") on failure.
  - Queries `sounddevice.query_devices()`, prints default input device + sample rate support for 16 kHz mono.
  - Tries to import `mediapipe`, `faster_whisper`, `webrtcvad` (or `silero_vad`), `pyautogui`, `pyperclip`, `keyboard`, `httpx`, `pydantic`, `rich`, `typer` - each one gets a PASS/FAIL line.
  - Returns exit code 0 only if all mandatory checks pass; CUDA-missing is a warning, not a failure.
- Wire the probe under the CLI too: `python -m sabi probe` should call into `scripts/probe_env.py`'s main function.
- Add a smoke test in `tests/test_probe.py` that imports every declared package without running hardware I/O (so CI-less local runs at least confirm the install).

## Acceptance criteria

- [ ] `pip install -e .[dev]` on a clean venv on Windows completes without conflicts (after running the torch CUDA line from `docs/INSTALL.md`).
- [ ] `python -m sabi probe` prints a pass/fail table for every package above, plus webcam and mic status.
- [ ] With the webcam disabled in Windows privacy settings, the probe fails with a clear remediation message and non-zero exit code.
- [ ] With CUDA absent, the probe still exits 0 but prints a visible `CUDA: not available (CPU fallback will be used)` warning.
- [ ] `pytest tests/test_probe.py` passes.
- [ ] `docs/INSTALL.md` exists and matches what a fresh-clone developer must actually run.

## Out of scope

- Ollama install/bring-up (TICKET-008).
- Chaplin weights download (TICKET-005).
- faster-whisper model download on first run - just confirm the package imports (TICKET-007 handles the actual download).
- Any virtual-mic/audio-routing dependencies (BlackHole/VB-Cable) - out of PoC scope entirely.

## References

- Roadmap core models table (project_roadmap.md lines 22-28) - fixes the MVP model choices this ticket must make runnable.
- Roadmap Phase 1 Week 1 (project_roadmap.md line 174) - "Chaplin installed, faster-whisper wired up" assumes this ticket's deps are in place.
- Roadmap risks (project_roadmap.md lines 217-225) - GPU baseline and model-version lock risks motivate the exact pins here.
