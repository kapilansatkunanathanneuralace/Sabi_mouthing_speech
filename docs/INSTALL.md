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

## Ollama (TICKET-008 cleanup pass)

`sabi.cleanup` posts to a **local** Ollama instance to clean up dictated
text (filler removal, punctuation, casing, stutter collapse). The
pipeline degrades gracefully when Ollama is unreachable, so installing
it is optional for the capture/VSR/ASR tickets but required to satisfy
TICKET-008 acceptance criteria.

1. Install Ollama for Windows from [ollama.com/download](https://ollama.com/download).
2. Pull the default model tag (matches `configs/cleanup.toml`):

    ```powershell
    ollama pull llama3.2:3b-instruct-q4_K_M
    ```

3. Confirm the daemon is reachable:

    ```powershell
    curl http://127.0.0.1:11434/api/tags
    ```

4. Run the smoke test:

    ```powershell
    python -m sabi cleanup-smoke "um i think it might like work"
    ```

    With Ollama running you should see a cleaned sentence (e.g. `"I
    think it might work."`) and `fallback : False`. With Ollama stopped
    the command still exits `0`, prints the raw text unchanged, and logs
    a single WARNING.

Edit `configs/cleanup.toml` to switch the model tag, tighten timeouts,
or point at a remote Ollama host. See
[`docs/cleanup-prompt.md`](cleanup-prompt.md) for prompt versioning.

## Paste injection (TICKET-009)

`python -m sabi paste-test "hello world"` copies a string to the
clipboard, fires `Ctrl+V` after a 3 s countdown, and restores the prior
clipboard on a background thread. See
[`docs/paste-injection.md`](paste-injection.md) for the Windows-specific
gotchas (Slack debounce, `OpenClipboard` contention, focus stealing).

## Hotkey trigger (TICKET-010)

`python -m sabi hotkey-debug` prints `[TRIGGER START]` / `[TRIGGER STOP]`
as you press the configured chord (default Ctrl+Alt+Space). Push-to-talk
and toggle modes are both supported. See
[`docs/hotkey.md`](hotkey.md) for the binding format, corporate AV
caveats, and the rationale behind the chord-parsing workaround for the
`keyboard` library's single-callback-per-chord limitation.

## Silent dictation (TICKET-011)

`python -m sabi silent-dictate` is the end-to-end PoC: hold the hotkey,
mouth a phrase, and the pipeline captures frames, runs Chaplin VSR,
cleans the text through Ollama, and pastes into the focused window.
Low-confidence utterances wait on a configurable force-paste key (F12
by default). See [`docs/silent-dictate.md`](silent-dictate.md) for the
CLI flags, per-stage latency contract, JSONL schema, and the
`keep_camera_open` privacy trade-off. `--dry-run` prints the cleaned
text to stdout instead of pasting, so you can iterate on the pipeline
without a typing target.

## Audio dictation (TICKET-012)

`python -m sabi dictate` is the audio counterpart to `silent-dictate`:
speak into the microphone (push-to-talk or VAD streaming), the pipeline
runs faster-whisper ASR + Ollama cleanup, and pastes into the focused
window. PTT holds utterances behind a 1.5 s force-paste window (F12 by
default); VAD auto-pastes by default because the stream cannot pause.
See [`docs/audio-dictate.md`](audio-dictate.md) for the full flag list,
the mode-specific force-paste policy (`force_paste_mode_ptt` /
`force_paste_mode_vad`), latency contract, and JSONL schema. Use
`--ptt-open-per-trigger` to reopen the microphone per PTT press
(privacy-oriented) or leave it off for snappier latency.

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
