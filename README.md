# Sabi Mouthing Speech

A **local, multimodal PoC** that turns spoken **or** silently mouthed input into text — no cloud, no accounts. Everything runs on the developer's machine.

- **Silent dictation** — webcam → MediaPipe lip ROI → Chaplin / Auto-AVSR → Ollama cleanup → paste (`python -m sabi silent-dictate`).
- **Audio dictation** — microphone + VAD → faster-whisper → Ollama cleanup → paste (`python -m sabi dictate`).
- **Fused dictation (planned, Phase 2)** — VSR + ASR run in parallel, confidence-weighted fusion → cleanup → paste. Specified across TICKET-016 (fusion module) and TICKET-017 (fused pipeline); not implemented yet.
- **Silent meeting (planned)** — VSR → Kokoro TTS → VB-Cable virtual mic → Zoom/Teams/Meet. Specified across TICKET-019…027; not implemented yet.

Work is tracked as numbered tickets in [`tickets/README.md`](tickets/README.md). Product vision, phases, and the fusion roadmap live in [`project_roadmap.md`](project_roadmap.md).

> **New to the repo?** Read [`docs/ONBOARDING.md`](docs/ONBOARDING.md) first. For the demo path, use [`docs/DEMO.md`](docs/DEMO.md); for a layman system explanation, use [`docs/INFRA_CHEAT_SHEET.md`](docs/INFRA_CHEAT_SHEET.md).
## Status at a glance

| Area | State | Entry point |
|---|---|---|
| Silent dictation (TICKET-011) | Done | `python -m sabi silent-dictate` |
| Audio dictation (TICKET-012)  | Done | `python -m sabi dictate` |
| Probe / hardware check (002)  | Done | `python -m sabi probe` |
| Capture + VAD + hotkey + paste + cleanup (003–010) | Done | see per-feature commands below |
| VSR wrapper (005) | In progress — GPU WER verification pending | `python -m sabi vsr-smoke <clip.mp4>` |
| Overlay UI, eval harness, demo runbook (013–015) | Done | `python -m sabi eval` / [`docs/DEMO.md`](docs/DEMO.md) |
| Audio–visual fusion + fused pipeline (016–017) | Not started — roadmap Phase 2 (after 015) | — |
| Cleanup polish v2 + eval A/B (018) | Not started — roadmap Phase 2 (after 014) | — |
| Meeting track (019–027) | Not started — deferred behind fusion + polish | — |

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

## Project layout

```
src/sabi/       capture/ models/ cleanup/ input/ output/ pipelines/  (+ cli.py, probe.py)
tests/          pytest; every module has a sibling test, no real hardware touched
scripts/        argparse shims + debug utilities
configs/        TOML defaults for each subsystem
docs/           operator / dev docs (start with ONBOARDING.md)
tickets/        27-ticket build plan + acceptance notes
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
