# Sabi Mouthing Speech — Onboarding

Welcome. This document is the one-stop orientation for new developers. It
covers what the codebase is, how to get it running on a fresh Windows
machine, what every folder is for, and a walkthrough of how a single
utterance moves through the pipelines.

If you only want the **short form**, read sections 1–3 and skim 4. If you
are about to write a ticket, also read sections 5–6.

---

## 1. What this codebase is

**Sabi Mouthing Speech** is a **local, multimodal PoC** that turns
spoken **or** silently mouthed input into text (and, in future tickets,
into synthesised voice that lands in a meeting app). Everything runs on
the developer's machine: no cloud calls, no accounts.

There are two end-to-end "flows" the repo is shaped around. Both are
already working:

- **Silent dictation (PoC-1, TICKET-011)** — webcam → lip ROI →
  Chaplin/Auto-AVSR (VSR) → Ollama cleanup → paste into focused app.
- **Audio dictation (PoC-2, TICKET-012)** — microphone + VAD →
  faster-whisper (ASR) → Ollama cleanup → paste into focused app.

A third flow — **silent meeting** — is specified in tickets (017, 018,
022…) but **not yet implemented**. It will add Kokoro TTS into a VB-Cable
virtual microphone so Zoom/Teams/Meet hears a synthesised voice.

Product vision, phases, and fusion roadmap live in
[`../project_roadmap.md`](../project_roadmap.md). The 24-ticket build
plan lives in [`../tickets/README.md`](../tickets/README.md). Individual
per-feature docs live under [`./`](.) (this folder).

### Mental model (one paragraph)

Think of it as **five swappable layers** glued together by two pipelines:
**capture** → **models** (VSR / ASR) → **cleanup** → **output** (paste),
all triggered by the **input** layer (hotkey). Each layer is its own
small package under `src/sabi/`; the `pipelines` package is what wires
them together, and the Typer CLI in `src/sabi/cli.py` is the only user
entry point (`python -m sabi ...`).

---

## 2. Onboarding steps for new devs

Target OS: **Windows 10/11**, PowerShell. Python **3.11** is the ticket
baseline (see `.python-version`); newer Python works but PyTorch CUDA
wheels may require the CPU fallback instead.

### 2.1. One-time setup

```powershell
git clone <this-repo>
cd Sabi_MouthingSpeech

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Then install PyTorch (pick one):

- **CUDA 12.1 track** (matches tickets):
  `pip install torch==2.3.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121`
- **CPU only** (or newer Python): `pip install torch torchaudio`

Then install the project:

```powershell
pip install -e ".[dev]"
```

Full detail (VB-Cable, Ollama, VAD fallbacks, etc.) is in
[`INSTALL.md`](INSTALL.md). Submodules (Chaplin) are under
`third_party/` and are pulled via `.gitmodules` — run
`git submodule update --init --recursive` if they're empty.

### 2.2. Verify the install

```powershell
python -m sabi probe
```

Green rows for camera, microphone, and core imports mean you're ready.
CUDA is a yellow warning, not a failure.

Then run the whole test suite — **this is the fastest sanity check**:

```powershell
pytest
```

You should see roughly **120+ tests passing in under 10 s** — none of
them touch real hardware because every pipeline component has a
dependency-injection seam (see section 4.5).

### 2.3. First end-to-end run

Pick one:

```powershell
python -m sabi silent-dictate --dry-run
python -m sabi dictate --dry-run
```

`--dry-run` prints the cleaned text to stdout instead of pasting, so you
can hear the pipeline work before you point it at a real window.

When you're ready to paste into a real app, drop `--dry-run` and hold
**Ctrl+Alt+Space** (the default chord). Low-confidence utterances sit
behind **F12** (force-paste) for 1.5 s — see
[`silent-dictate.md`](silent-dictate.md) and
[`audio-dictate.md`](audio-dictate.md).

### 2.4. Optional extras

- **Ollama** (cleanup): install from [ollama.com](https://ollama.com),
  `ollama pull llama3.2:3b-instruct-q4_K_M`. Without it, pipelines still
  run and paste **raw** text with `used_fallback=True`.
- **Chaplin VSR weights** (silent dictation only):
  `python -m sabi download-vsr` fetches hashes from
  `configs/vsr_weights.toml`.
- **VB-Cable** (meeting mode, not yet used): see
  [`INSTALL.md`](INSTALL.md) → "Virtual mic" section.

### 2.5. Dev commands

```powershell
ruff check .        # lint
black --check .     # format check (black --write . to apply)
pytest              # full test suite (hardware-free)
pytest tests/test_audio_dictate.py -q   # single suite
python -m sabi probe                    # hardware + import matrix
```

---

## 3. Folder-by-folder reference

Top of repo:

```
Sabi_MouthingSpeech/
├── src/sabi/           # the package you ship (installed via pyproject.toml)
├── tests/              # pytest; every module under src has a sibling here
├── scripts/            # argparse shims + developer-only utilities
├── configs/            # TOML defaults for each subsystem
├── docs/               # operator / dev docs (you're reading one)
├── tickets/            # 24-ticket build plan + acceptance docs
├── reports/            # generated JSONL + latency-log.md (git-ignored contents)
├── third_party/        # git submodules (Chaplin / Auto-AVSR)
├── data/               # dataset artefacts (not checked in; reserved for TICKET-014)
├── pyproject.toml      # package metadata, pins, tool config
├── project_roadmap.md  # product vision + phased rollout
└── README.md
```

### 3.1. `src/sabi/` — the package

Every subpackage maps to a ticket number. A good mental trick: the
**layer** the folder belongs to is the same as the **roadmap layer** in
`project_roadmap.md` → "Recommended Architecture".

| Package | Tickets | What it owns |
|---|---|---|
| `capture/` | 003, 004, 006 | Webcam, MediaPipe lip ROI, microphone + VAD, mic-preview / lip-preview CLIs. This is the "**Input layer**" for hardware. |
| `models/` | 005, 007 | ML wrappers. `asr.py` = faster-whisper; `vsr/` = Chaplin/Auto-AVSR wrapper + weight download + smoke test. `latency.py` is the shared `append_latency_row()` helper that writes to `reports/latency-log.md`. |
| `cleanup/` | 008 | Ollama HTTP client, prompt loading, degrade-to-raw fallback. The `TextCleaner` is the single place that touches the LLM. |
| `input/` | 010 | Global hotkey controller (`keyboard` library), chord parser, `TriggerBus` that dispatches `on_start` / `on_stop` on a worker thread so callbacks never run inside the Windows keyboard hook. |
| `output/` | 009 | `paste_text()` — save clipboard, write, press Ctrl+V via pyautogui, restore prior clipboard on a background thread. |
| `pipelines/` | 011, 012 | The two end-to-end flows (`silent_dictate.py`, `audio_dictate.py`). This is where all the above modules are wired together behind `_Deps` dataclasses for test isolation. |
| `probe.py` | 002 | `python -m sabi probe` — hardware + import matrix rendered via `rich`. |
| `cli.py`, `__main__.py` | all | Typer app. Every command is one function in `cli.py` (roughly one per ticket). `python -m sabi` runs `__main__.py` → `cli.main()`. |

### 3.2. `tests/`

One pytest file per subpackage. They **do not touch real hardware** —
all external dependencies are replaced via:

- the `_Deps` seam inside the pipeline modules, or
- lightweight fakes (`FakeMicrophone`, `FakeASR`, `FakeCleaner`, …) kept
  at the top of each `test_*.py`.

Running `pytest` locally is the canonical "did my change regress
anything?" check. CI (when it exists) will mirror this.

### 3.3. `scripts/`

Thin **argparse shims** that mirror the Typer commands (they exist so
you can copy-paste a PowerShell line into docs without relying on
`sabi` being on `PATH`). A few are **developer-only** utilities:

- `silent_dictate.py`, `audio_dictate.py` — mirror `python -m sabi
  silent-dictate` / `dictate`.
- `probe_env.py` — same as `python -m sabi probe`.
- `download_vsr_weights.py` — fetches + hash-verifies Chaplin weights.
- `webcam_viewer.py`, `lip_roi_debug.py`, `mic_monitor.py`,
  `hotkey_debug.py`, `paste_harness.py` — debug tools for the
  individual layers.

### 3.4. `configs/`

Pydantic-validated **TOML defaults** for each subsystem. Empty sections
are fine — the pipelines overlay only keys that are present, so partial
TOML files are the normal mode.

- `silent_dictate.toml` / `audio_dictate.toml` — the two end-to-end
  pipeline configs (cover `[webcam|mic] [lip_roi] [vsr|asr] [cleanup]
  [inject] [hotkey] [pipeline]`).
- `cleanup.toml`, `hotkey.toml` — stand-alone configs consumed by
  `cleanup-smoke` and `hotkey-debug`.
- `vsr_weights.toml` — sha256 manifest for Chaplin downloads.

### 3.5. `docs/`

Operator-facing docs — one per feature, plus this onboarding file and
[`INSTALL.md`](INSTALL.md). The pipeline docs
([`silent-dictate.md`](silent-dictate.md),
[`audio-dictate.md`](audio-dictate.md)) are the canonical references
for CLI flags, latency contracts, JSONL schemas, and failure modes.

### 3.6. `tickets/`

The build plan. Every feature you work on has a ticket describing
goal, dependencies, acceptance criteria, risks, and implementation
notes. Read [`tickets/README.md`](../tickets/README.md) for the
dependency graph and phase 1 → phase 2 scheduling.

### 3.7. `reports/`

Where pipelines write their logs:

- `reports/latency-log.md` — one-line-per-run markdown table appended
  via `sabi.models.latency.append_latency_row()`.
- `reports/silent_dictate_<YYYYMMDD>.jsonl` — per-utterance events
  emitted by the silent pipeline.
- `reports/audio_dictate_<YYYYMMDD>.jsonl` — same shape, audio
  pipeline. The `pipeline` field on each row disambiguates once
  TICKET-014 merges both streams.

Everything under `reports/` is generated; treat it as an output folder.

### 3.8. `third_party/`

Git submodules of upstream projects whose code we vendor but don't
fork. Currently: **Chaplin** (Auto-AVSR implementation used by the
VSR wrapper). The wrapper in `src/sabi/models/vsr/` is the stable
Python-facing API — do **not** import directly from `third_party/` in
new code.

### 3.9. `data/`

Reserved for eval datasets (TICKET-014). **Not checked in** (clips
contain real faces/voices). The harness expects
`data/eval/phrases.jsonl` + `data/eval/video|audio/<id>.*`.

---

## 4. Code walkthrough — how one utterance moves through the pipeline

Both pipelines follow the **same shape**. Read this section once with
the silent pipeline in mind, then section 4.6 covers the ASR-specific
differences.

### 4.1. Entry point: `python -m sabi ...`

`src/sabi/__main__.py` is a three-line trampoline that calls
`sabi.cli.main()`. `cli.py` is a Typer app with one `@app.command(...)`
per CLI action. For dictation the relevant commands are:

- `silent-dictate` — loads `configs/silent_dictate.toml` via
  `load_silent_dictate_config`, applies CLI overrides via
  `model_copy`, then calls `run_silent_dictate(cfg)`.
- `dictate` — identical shape for the audio pipeline.

Key behaviour to keep in mind: the Typer command is a **thin adapter**.
All real logic lives in the `run_*` functions inside the pipeline
modules. CLI tests can therefore skip Typer and call `run_*` directly
with a `_Deps(...)` arg.

### 4.2. Config overlay

```python
cfg = load_silent_dictate_config(config_path)     # TOML → Pydantic
overrides = {...}                                 # from CLI flags
cfg = cfg.model_copy(update=overrides)            # shallow merge
raise typer.Exit(run_silent_dictate(cfg))
```

A subtle but important detail: the **audio** pipeline's loader uses
`AudioDictateConfig.model_validate({**cfg.model_dump(), **updates})`
instead of `model_copy(update=...)`. That's because its
`model_validator` coerces `hotkey.mode` to match `trigger_mode`, and
Pydantic v2's `model_copy` **does not re-run validators**. Reconstruct
through `model_validate` when a validator needs to see the merged
state.

### 4.3. `run_silent_dictate(cfg)` — the outer loop

Structure (see `src/sabi/pipelines/silent_dictate.py`):

```python
def run_silent_dictate(config, *, deps=None, stop_event=None):
    with SilentDictatePipeline(config, deps=deps) as pipe:
        pipe.subscribe(_print_callback)   # live console feedback
        (stop_event or threading.Event()).wait()   # block until Ctrl+C
    return 0
```

That's it. The pipeline itself is a **context manager** that owns every
thread and resource. Exiting the `with` block is how you know
everything shut down cleanly.

### 4.4. Inside the pipeline (`__enter__` → `__exit__`)

```
__enter__:
    1. ASR/VSR .warm_up()          → records warmup_ms
    2. TextCleaner.is_available()   → probes Ollama once
    3. open MicrophoneSource / WebcamSource (unless per-trigger lifecycle)
    4. start HotkeyController(primary)  → subscribes on_trigger_start/stop
    5. if force_paste_mode == "listener":
           start HotkeyController(F12) → subscribes _handle_force_paste
    6. (VAD only) start _vad_consumer_thread

user activity → triggers flow through a dispatch thread

__exit__:
    - stop hotkey controllers
    - set _vad_active=False, cancel force-paste timers
    - join dispatch threads with _safe_join(timeout=2.0)
    - close mic/webcam, ASR/VSR, TextCleaner
```

Everything user-visible happens on **dispatch threads** spawned from
trigger callbacks, not on the keyboard-hook thread. This keeps the
Windows message pump responsive even when ASR/VSR is running.

### 4.5. The `_Deps` seam

Both pipeline modules define a `_Deps` dataclass that looks like:

```python
@dataclass
class _Deps:
    mic_factory:     Callable[[MicConfig], ContextManager[MicrophoneSource]]
    asr_factory:     Callable[[ASRModelConfig], ASRModel]
    cleaner_factory: Callable[[CleanupConfig], TextCleaner]
    hotkey_factory:  Callable[[HotkeyConfig], HotkeyController]
    paste_fn:        Callable[[str, InjectConfig], InjectResult]
    latency_writer:  Callable[..., None]
    now_ns:          Callable[[], int]
    perf_counter:    Callable[[], float]
```

Production code passes `deps=None` and the pipeline fills in the real
factories. Tests pass a `_Deps(...)` where each callable is a fake, so
the **exact same pipeline code path** runs with no mic/camera/Ollama/
clipboard/keyboard. This is how `pytest` finishes in a few seconds.

### 4.6. Per-utterance flow

Silent pipeline (PTT mode):

```
hotkey press
  → TriggerBus worker thread fires on_trigger_start(event)
    → pipeline opens webcam (unless keep_camera_open=true)
    → starts frame-capture loop into a bounded deque
hotkey release
  → on_trigger_stop(event)
    → pipeline closes webcam, hands buffered frames to a dispatch thread

dispatch thread:
  1. LipROIDetector → list[LipFrame]  (96×96 uint8 grayscale)
  2. gates:  occlusion_ratio < occlusion_threshold → withheld_occluded
  3. VSRModel.predict(frames) → VSRResult(text, confidence, latency_ms)
  4. gate:  empty text → withheld_empty
  5. TextCleaner.cleanup(text, CleanupContext(source="vsr"))
  6. route by confidence + force_paste_mode:
        - listener: stash pending + threading.Timer(1.5s)
        - always:   paste now
        - never:    discard
  7. paste_text(...) → Ctrl+V
  8. _emit_final(UtteranceProcessed(...))
     → JSONL row to reports/silent_dictate_<date>.jsonl
     → append_latency_row(...) in reports/latency-log.md
     → subscriber callbacks (TUI, tests, eval harness)
```

Audio pipeline (two sub-flows):

- **PTT**: same as above but with `MicrophoneSource.push_to_talk_segment`
  driven by two `threading.Event`s; a guard timer caps each utterance at
  `mic.max_utterance_ms` so a stuck hotkey can never block forever.
- **VAD**: `HotkeyController(mode="toggle")` flips `_vad_active`; a
  single `_vad_consumer_thread` polls `mic.next_utterance(timeout=0.1)`
  and dispatches every detected utterance on its own thread. Because
  dispatches are concurrent, VAD utterances can **complete out of
  order** — this is documented in `docs/audio-dictate.md` and tests use
  multiset assertions accordingly.

Gates for the audio pipeline are: `silence (peak_dbfs ≤ floor)` /
`low VAD coverage` / `empty ASR text` / `confidence < confidence_floor`.
See `audio_dictate.py::_dispatch_*` for the exact order.

### 4.7. Events and telemetry

Every pipeline tick emits a `UtteranceProcessed` (frozen dataclass)
carrying per-stage latencies, the paste decision, and a `pipeline` tag
(`"silent"` or `"audio"`). Subscribers get it via `pipe.subscribe(cb)`.
The same object is serialised one-line-per-utterance into
`reports/<pipeline>_<YYYYMMDD>.jsonl`. This is the single source of
truth for TICKET-014's eval harness.

---

## 5. Development workflow

### 5.1. Adding a feature

1. Find (or create) the ticket in `tickets/`. Read its dependencies
   and acceptance criteria.
2. Land code + tests together. New modules should expose a Pydantic
   config, a small public surface, and be importable without side
   effects (mediapipe / cuda loads are lazy throughout the repo).
3. If your change touches a pipeline, extend its `_Deps` seam **and**
   add fakes + tests before touching the real factories.
4. Append one row to `reports/latency-log.md` via
   `append_latency_row(...)` whenever you introduce or move a per-stage
   measurement. Keep `p50_ms` and `samples` honest.
5. Update the per-feature doc in `docs/` and flip ticket status at the
   end.

### 5.2. Debugging

- `python -m sabi probe` — imports + camera + mic sanity.
- `python -m sabi cam-preview` / `lip-preview` — OpenCV windows for
  the visual stack.
- `python -m sabi mic-preview` — live dB meter + VAD indicator.
- `python -m sabi hotkey-debug` — prints `[TRIGGER START|STOP]`.
- `python -m sabi cleanup-smoke "text"` — one-shot Ollama call.
- `python -m sabi paste-test "text"` — clipboard + Ctrl+V with
  countdown.
- Pipeline logs: `reports/*.jsonl` is the best post-mortem source;
  each row has `event_type` (`trigger_start`, `utterance_processed`,
  `force_paste_hit`, `pipeline_error`, `vad_activated`, …).

### 5.3. Tests

- Hardware-free. **Do not introduce network, camera, mic, CUDA,
  clipboard, or real keyboard calls in `tests/`** — use the `_Deps`
  seam or the per-module fakes.
- `pytest -q` in under 10 s is the goal.
- Concurrency: if you assert on a list that comes from concurrent
  dispatch threads, use `sorted(...)` or a multiset compare — the VAD
  test in `tests/test_audio_dictate.py` is the reference.

### 5.4. Conventions

- **Pydantic v2** everywhere; `model_validator(mode="after")` for
  cross-field invariants. If your validator mutates fields, reload via
  `.model_validate(...)` after `model_copy(update=...)` — `model_copy`
  does not re-run validators.
- **Threading**: never call `thread.join()` unconditionally on threads
  that may not have started yet; use the `_safe_join` helper in the
  pipeline modules.
- **Logging**: `logging.getLogger(__name__)` per module, `INFO` for
  lifecycle events, `WARNING` for degrade-to-fallback, `ERROR` only
  when the user will see a stuck pipeline.
- **Comments**: explain intent, trade-offs, and subtle invariants;
  don't narrate obvious code.

---

## 6. Where to go next

- [`../tickets/README.md`](../tickets/README.md) — 24-ticket graph; the
  dictation track (001–015) is done or in progress, the meeting track
  (016–024) is not started.
- [`../project_roadmap.md`](../project_roadmap.md) — Phase 1 vs Phase 2
  vs fusion layer. Audio-visual fusion lives in **Phase 2 / Tier 2**
  and will be added as a new ticket after TICKET-014 has produced the
  first measurable baseline.
- [`silent-dictate.md`](silent-dictate.md) and
  [`audio-dictate.md`](audio-dictate.md) — the pipeline-specific
  reference docs (CLI flags, latency keys, JSONL schema, caveats).
- [`INSTALL.md`](INSTALL.md) — every install path, including Ollama,
  VB-Cable, and the CPU-only PyTorch fallback.

Welcome aboard.
