# Sabi Mouthing Speech

A **local, multimodal PoC** that turns spoken **or** silently mouthed input into text — no cloud, no accounts. Everything runs on the developer's machine.

- **Silent dictation** — webcam → MediaPipe lip ROI → Chaplin / Auto-AVSR → Ollama cleanup → paste (`python -m sabi silent-dictate`).
- **Audio dictation** — microphone + VAD → faster-whisper → Ollama cleanup → paste (`python -m sabi dictate`).
- **Fused dictation** — VSR + ASR run in parallel, confidence-weighted fusion → cleanup → paste (`python -m sabi fused-dictate`).
- **Silent meeting (planned)** — VSR → Kokoro TTS → VB-Cable virtual mic → Zoom/Teams/Meet. Specified across TICKET-021…029; not implemented yet.

Work is tracked as numbered tickets in [`tickets/README.md`](tickets/README.md). Product vision, phases, and the fusion roadmap live in [`project_roadmap.md`](project_roadmap.md).

> **New to the repo?** Read [`docs/ONBOARDING.md`](docs/ONBOARDING.md) first. For the demo path, use [`docs/DEMO.md`](docs/DEMO.md); for a layman system explanation, use [`docs/INFRA_CHEAT_SHEET.md`](docs/INFRA_CHEAT_SHEET.md).
## Status at a glance

Current ticket progress: **34/54 done**, **0 in progress**, **20 not started** (includes the new Phase 3 distribution & packaging track, TICKET-041 - TICKET-054).

| Area | State | Entry point |
|---|---|---|
| Silent dictation (TICKET-011) | Done | `python -m sabi silent-dictate` |
| Audio dictation (TICKET-012)  | Done | `python -m sabi dictate` |
| Probe / hardware check (002)  | Done | `python -m sabi probe` |
| Capture + VAD + hotkey + paste + cleanup (003–010) | Done | see per-feature commands below |
| VSR wrapper (005) | Done | `python -m sabi vsr-smoke <clip.mp4>` |
| Overlay UI, eval harness, demo runbook (013–015) | Done | `python -m sabi eval` / [`docs/DEMO.md`](docs/DEMO.md) |
| Audio–visual fusion + fused pipeline (016–017) | Done | `python -m sabi fused-dictate` |
| Cleanup polish v2 + eval A/B (018) | Done | `python -m sabi cleanup-smoke --prompt-version v2 "text"` |
| Personal fused eval collection + baseline (019–020) | Done | `python -m sabi collect-fused-eval` / `python -m sabi fused-eval-check` |
| Fused diagnostics + recommendations + calibration (030–034) | Partial — 031–033 Done; 030 + 034 Not started | see `tickets/README.md` |
| Cleanup/fusion policy + expanded eval + latency (035–040) | Partial — 035–038 Done; 039–040 Not started | see `tickets/README.md` |
| Meeting track (021–029) | Not started — deferred behind fusion + polish | — |
| Distribution & packaging (041–054) | Partial — 041–048 Done; 049 Partial; 050–054 Not started | see [`tickets/distribution_packaging/`](tickets/distribution_packaging/README.md) |

## Desktop app (alpha)

The installable desktop shell is being built under [`desktop/`](desktop/README.md).
It uses Electron + Vite + React, starts the Python sidecar, shows live sidecar
health, can run `probe.run` through JSON-RPC, has resident tray/shortcut behavior,
includes first-launch onboarding, and manages model downloads in an app-owned cache.
The Python CLI remains the primary developer/debug path for pipeline work.

## Distribution And Install

Windows installer builds use the slim PyInstaller sidecar and Electron NSIS package:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\build_sidecar_release.py
cd desktop
npm run package:win
npm run validate:win-package
```

The installer is written to `desktop/dist/Sabi-<version>-setup.exe`. Run it from
Explorer or PowerShell, keep the default per-user install, then launch Sabi from the
finish page, Start Menu, or desktop shortcut. Model weights are not bundled; the app
downloads them into `%LOCALAPPDATA%\Sabi\models` during onboarding.
The installer is a bootstrap app: real silent/audio/fused dictation also requires the
full CPU runtime pack, downloaded and activated from the desktop onboarding/runtime
panel after install.

For local signed smoke builds, create a developer-only self-signed certificate:

```powershell
cd desktop
npm run signing:create-local-cert -- -Trust
$env:WIN_CSC_LINK = ".certs\sabi-local-test-signing.pfx"
$env:WIN_CSC_KEY_PASSWORD = "<password used above>"
$env:WIN_SELF_SIGNED_LOCAL = "1"
$env:WIN_EXPECT_SIGNED = "1"
npm run package:win
npm run validate:win-package
```

Self-signed installers are only for local validation. Public releases still require a
trusted OV/EV certificate or Azure Trusted Signing; see
[`docs/distribution_packaging/SIGNING_WINDOWS.md`](docs/distribution_packaging/SIGNING_WINDOWS.md).

To produce the full dictation runtime artifact for distribution, build from a
CPU-only Python environment:

```powershell
python scripts\build_sidecar_full_cpu.py
```

Publish the generated runtime zip and update `configs/runtime/full-cpu.json` with its
URL, SHA256, and size before asking users to install the full runtime.

## Quick start (Windows, PowerShell)

Full dependency order (PyTorch CUDA wheels, then the project, then optional Ollama / Chaplin weights / VB-Cable) is in **[docs/INSTALL.md](docs/INSTALL.md)**. Short version:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# PyTorch (CUDA or CPU): follow docs/INSTALL.md before or after this step as appropriate
pip install -e ".[dev]"
python -m sabi
```

You should see: `sabi PoC - see tickets/README.md`

Then verify hardware + imports:

```powershell
python -m sabi probe
```

First end-to-end run (safe — prints instead of pasting):

```powershell
python -m sabi silent-dictate --dry-run
python -m sabi dictate --dry-run
```

Drop `--dry-run` to paste into the focused window; default hotkey is **Ctrl+Alt+Space**, with **F12** for force-paste of low-confidence utterances.

## Quick start (Windows, Command Prompt)

Manual activation:

```bat
cd path\to\Sabi_MouthingSpeech
.\.venv\Scripts\activate.bat
```

Helper scripts in the repo root (run from Explorer or `cmd`):

- **`activate_venv.bat`** — `cd` to the repo and activate `.venv` in the **current** Command Prompt window.
- **`open_cmd_with_venv.bat`** — opens a **new** Command Prompt with the repo folder and `.venv` already activated (handy double-click).

## CLI commands

All commands are `python -m sabi <name> [--help]`.

| Command | Ticket | Purpose |
|---|---|---|
| `probe` | 002 | Hardware + import matrix (camera, mic, torch, mediapipe, …). |
| `cam-preview` / `lip-preview` | 003 / 004 | OpenCV window for the visual stack. |
| `mic-preview` | 006 | Live dB meter + VAD indicator. |
| `download-vsr` | 005 | Fetch + hash-verify Chaplin weights per `configs/vsr_weights.toml`. |
| `vsr-smoke <clip.mp4>` | 005 | Run Chaplin end-to-end on a recorded clip. |
| `asr-smoke <clip.wav>` | 007 | Run faster-whisper end-to-end. |
| `cleanup-smoke "text"` | 008 | One-shot Ollama cleanup (degrades to raw on failure). |
| `paste-test "text"` | 009 | Clipboard + Ctrl+V with a countdown. |
| `hotkey-debug` | 010 | Prints `[TRIGGER START|STOP]` for the configured chord. |
| `silent-dictate` | 011 | Silent-dictation pipeline (VSR). |
| `dictate` | 012 | Audio-dictation pipeline (ASR, PTT or VAD). |
| `fused-dictate` | 017 | Fused dictation pipeline (ASR + VSR + fusion). |
| `eval` | 014 / 017 / 018 / 020 | Offline WER/latency eval for silent, audio, and fused pipelines. |
| `collect-fused-eval` | 019 | Guided webcam + mic capture for personal fused eval data. |
| `fused-eval-check` | 020 | Validate fused eval media before running the eval harness. |
| `fused-eval-reset` | 019 / 020 | Preview or delete generated fused eval media so you can restart collection. |

## Common command cheat sheet

Use these from the repo root with the virtual environment activated.

| Command | What it does |
|---|---|
| `python -m sabi silent-dictate --dry-run` | Runs the silent dictation pipeline without pasting into another app. Use this to test webcam/VSR flow safely. |
| `Ctrl+Alt+Space` | Default push-to-talk hotkey for dictation commands. Press once to start an utterance and again to stop, depending on mode. |
| `python -m sabi lip-preview` | Opens a live camera preview with mouth/lip ROI detection so you can confirm the webcam and face tracking work. |
| `python -m sabi dictate` | Runs the audio dictation pipeline with the microphone and pastes accepted text into the focused app. |
| `python -m sabi dictate --ui tui --dry-run` | Runs audio dictation with the terminal status UI and no paste side effects. Good for demos/debugging. |
| `python -m sabi silent-dictate --ui tui --dry-run` | Runs silent dictation with the terminal status UI and no paste side effects. |
| `python -m sabi fused-dictate --ui tui --dry-run` | Runs fused dictation with ASR + VSR + fusion, showing status in the TUI without pasting. |
| `ffmpeg -list_devices true -f dshow -i dummy` | Lists Windows DirectShow camera and microphone device names for `collect-fused-eval`. |
| `python -m sabi fused-eval-reset --dataset data/eval/fused` | Previews which generated fused eval files would be deleted. Does not delete yet. |
| `python -m sabi fused-eval-reset --dataset data/eval/fused --yes` | Deletes generated `data/eval/fused` media and `phrases.jsonl` so you can restart collection. |
| `python -m sabi collect-fused-eval --camera-name "ACER FHD User Facing" --mic-name "Microphone Array (Intel® Smart Sound Technology for Digital Microphones)"` | Records synced webcam video and microphone audio for each eval phrase and writes `data/eval/fused/phrases.jsonl`. Replace the device names with the exact names from `ffmpeg`. |
| `python -m sabi fused-eval-check --dataset data/eval/fused` | Checks that every fused eval phrase has readable video and valid 16 kHz PCM WAV audio. Run this before eval. |
| `python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --out reports/poc-eval-fused-personal.md` | Runs the fused eval harness on your collected dataset and writes a personal WER/latency report. |

## Project layout

```
src/sabi/       capture/ models/ cleanup/ input/ output/ pipelines/  (+ cli.py, probe.py)
tests/          pytest; every module has a sibling test, no real hardware touched
scripts/        argparse shims + debug utilities
configs/        TOML defaults for each subsystem
docs/           operator / dev docs (start with ONBOARDING.md)
tickets/        ticket build plan + acceptance notes
reports/        generated JSONL + latency-log.md
third_party/    git submodules (Chaplin / Auto-AVSR)
```

See [`docs/ONBOARDING.md`](docs/ONBOARDING.md) for the detailed, per-folder tour.

## Documentation map

- [`docs/ONBOARDING.md`](docs/ONBOARDING.md) — new-dev orientation + code walkthrough.
- [`docs/INSTALL.md`](docs/INSTALL.md) — full install (venv, torch, Ollama, Chaplin, optional VB-Cable).
- [`docs/DEMO.md`](docs/DEMO.md) — Phase 1 demo runbook for silent and audio dictation.
- [`docs/INFRA_CHEAT_SHEET.md`](docs/INFRA_CHEAT_SHEET.md) — plain-English explanation of the system and common review questions.
- [`docs/silent-dictate.md`](docs/silent-dictate.md) — PoC-1 reference (CLI, latency keys, JSONL schema).
- [`docs/audio-dictate.md`](docs/audio-dictate.md) — PoC-2 reference (PTT vs VAD, force-paste policy).
- [`docs/FUSED_EVAL.md`](docs/FUSED_EVAL.md) — collecting, checking, and running personal fused eval data.
- [`docs/hotkey.md`](docs/hotkey.md), [`docs/paste-injection.md`](docs/paste-injection.md), [`docs/cleanup-prompt.md`](docs/cleanup-prompt.md), [`docs/MODELS.md`](docs/MODELS.md) — per-feature detail.
- [`tickets/README.md`](tickets/README.md) — ticket graph, estimates, dependencies.
- [`project_roadmap.md`](project_roadmap.md) — phases, tiers, fusion plan.

## Dev commands

```powershell
ruff check .
black --check .
pytest
```

The full `pytest` suite finishes in under 10 s because every pipeline component has a dependency-injection seam (`_Deps`) backed by fakes — no camera, no CUDA, no Ollama, no clipboard, no real keyboard hook is touched in tests. See the onboarding doc for conventions.

## Legacy title

The project was initially named `Sabi_mouthing_speech`; the installed package name is `sabi`.
