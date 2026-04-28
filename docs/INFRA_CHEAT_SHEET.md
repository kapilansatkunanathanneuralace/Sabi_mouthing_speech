# Sabi Infra Cheat Sheet

This is the simple-language version of the system. Use it when a senior reviewer asks "what is this thing doing?" and you need a clear answer without diving into every file.

## One-Sentence Pitch

Sabi is a local Windows PoC that turns either silent mouth movement or spoken audio into text, cleans that text locally, and pastes it into the app you are already using.

## The Big Picture

Think of the app like an assembly line:

1. **Trigger**: the hotkey says "start listening" and "stop listening."
2. **Capture**: webcam frames or microphone samples are collected.
3. **Recognition**: a model turns that signal into rough text.
4. **Cleanup**: a small local LLM fixes casing, punctuation, filler words, and stutters.
5. **Output**: the final text is pasted into the focused app.
6. **Measurement**: logs and eval reports tell us speed and accuracy.

## Key Terms In Plain English

| Term | Simple meaning | Why it matters |
| --- | --- | --- |
| **PoC** | Proof of concept. A working demo, not a polished product. | Sets expectations: local, developer-run, not packaged yet. |
| **Silent dictation** | Mouth words at the camera without relying on audio. | This is the main novel demo. |
| **Audio dictation** | Normal speech-to-text using the microphone. | It is the baseline we compare silent dictation against. |
| **VSR** | Visual speech recognition: lip-reading by model. | This powers silent dictation. |
| **ASR** | Automatic speech recognition: speech-to-text from audio. | This powers audio dictation. |
| **Chaplin / Auto-AVSR** | An open-source lip-reading model stack. | It is the model that reads mouth crops and predicts text. |
| **faster-whisper** | A fast local Whisper implementation. | It gives us strong spoken-audio transcription. |
| **MediaPipe** | Google's face/landmark detector library. | We use it to find the mouth before VSR. |
| **Lip ROI** | Region of interest around the lips. | The VSR model should see just the mouth area, not the whole room. |
| **Ollama** | Local app that serves LLMs over HTTP. | It lets cleanup run locally without cloud calls. |
| **Cleanup** | Text polishing after raw recognition. | It turns rough text into something paste-worthy. |
| **TUI** | Terminal user interface. | It shows live mode, Ollama status, CUDA status, utterances, and latencies. |
| **WER** | Word error rate. | Accuracy metric: lower WER means fewer word mistakes. |
| **p50 / p95** | Median and tail latency. | p50 shows normal speed; p95 shows the slow cases users still feel. |
| **dry-run** | Run without pasting. | Safer testing: prints/logs output instead of touching apps. |

## What Happens In Silent Dictation

Command:

```powershell
python -m sabi silent-dictate --ui tui
```

Flow:

1. You hold **Ctrl+Alt+Space**.
2. The webcam captures frames.
3. MediaPipe finds the face and mouth.
4. `LipROIDetector` crops the mouth into small normalized images.
5. Chaplin / Auto-AVSR predicts text from the mouth crops.
6. Ollama cleanup improves the raw text if Ollama is online.
7. The output layer pastes text into the active app.
8. The TUI and JSONL logs show what happened.

Good answer to a senior:

> "Silent dictation is not reading audio. It captures webcam frames, crops the mouth, sends those crops to a visual speech recognition model, optionally cleans the text with a local LLM, then pastes it. We also log confidence and per-stage latency so we know where it failed."

## What Happens In Audio Dictation

Command:

```powershell
python -m sabi dictate --ui tui
```

Flow:

1. You hold **Ctrl+Alt+Space**.
2. The microphone captures audio.
3. VAD helps decide what is speech.
4. faster-whisper transcribes the audio.
5. Ollama cleanup improves the text if available.
6. The output layer pastes into the active app.

Good answer:

> "Audio dictation is the control path. It uses a known-good speech model so we can compare silent dictation against something reliable."

## Why We Need Both Pipelines

Audio dictation answers: "What would normal speech recognition do here?"

Silent dictation answers: "Can we get usable text when the user cannot or does not want to speak out loud?"

The eval harness compares both on the same phrase list so we can see whether changes help silent dictation or just feel better in one manual demo.

## What The Eval Harness Does

Command:

```powershell
python -m sabi eval --dataset data/eval/sample --pipeline both --runs 1 --out reports/poc-eval-test.md
```

It does **not** open the live camera or mic. It reads saved `.mp4` and `.wav` files, runs the same model stages offline, and writes a markdown report.

Key report fields:

- **Raw WER**: model output accuracy before cleanup.
- **Cleaned WER**: accuracy after Ollama cleanup.
- **Latency tables**: time spent in capture, ROI, VSR/ASR, cleanup, and output.
- **Known failures**: no face, silence, low confidence, empty output, or cleanup fallback.

Good answer:

> "The eval harness is our scoreboard. It replays fixed clips so we can compare changes without relying on memory or one lucky demo."

## Personal Fused Eval Is Not Training

The fused eval dataset under `data/eval/fused` is a personal benchmark dataset. It
contains your webcam video and microphone audio for the same phrase list, and it
lets the fused pipeline measure how well ASR, VSR, fusion, and cleanup work for
your setup.

Command:

```powershell
python -m sabi fused-eval-check --dataset data/eval/fused
python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --out reports/poc-eval-fused-personal.md
```

This does **not** fine-tune Chaplin, Whisper, the fusion combiner, or the cleanup
prompt. No model changes automatically after collection. If the report shows a
problem, the next step is manual tuning: improve capture conditions, adjust
fusion thresholds, compare cleanup prompts, or open a future fine-tuning ticket.

Good answer:

> "The personal fused dataset is our measuring stick, not a training set. It tells us what fails for this user and environment. The current PoC does not learn from it automatically."

## Important Files To Know

| Path | What it is |
| --- | --- |
| `src/sabi/cli.py` | Command entry point for `python -m sabi ...`. |
| `src/sabi/capture/` | Webcam, lip ROI, microphone, and VAD code. |
| `src/sabi/models/vsr/model.py` | Chaplin / Auto-AVSR wrapper. |
| `src/sabi/models/asr.py` | faster-whisper wrapper. |
| `src/sabi/cleanup/ollama.py` | Local LLM cleanup client. |
| `src/sabi/output/inject.py` | Clipboard and Ctrl+V paste logic. |
| `src/sabi/input/hotkey.py` | Hotkey trigger layer. |
| `src/sabi/pipelines/` | Wires capture, models, cleanup, and paste into full flows. |
| `src/sabi/eval/harness.py` | Offline WER + latency report generator. |
| `reports/latency-log.md` | Shared latency history. |
| `docs/DEMO.md` | How to reproduce the demo. |

## Questions A Senior Might Ask

### Is this cloud-based?

No. The models and cleanup run locally. Ollama is local HTTP on `127.0.0.1`. If Ollama is down, cleanup is bypassed and the pipeline still returns raw text.

### What is Chaplin?

Chaplin is the visual speech recognition model stack we use for lip-reading. In simple terms, it looks at a sequence of mouth crops and guesses the spoken words.

### Why crop the lips first?

The lip crop removes irrelevant pixels. The model should focus on mouth movement, not the user's background, hair, or lighting.

### What is MediaPipe doing?

MediaPipe detects face landmarks. We use those landmarks to find the mouth reliably frame by frame.

### Why use faster-whisper if this is about silent speech?

It gives us a strong audio baseline. If audio gets a phrase right and silent gets it wrong, we know the silent side needs work. It also becomes one input to future fusion.

### What does "fusion" mean?

Fusion means combining audio and visual predictions. If audio is noisy but lips are clear, or lips are unclear but audio is good, the combined system can choose the stronger evidence.

### What happens when confidence is low?

The pipeline withholds the paste. In listener mode it gives you a short F12 window to paste anyway.

### Why paste instead of typing through an API?

Clipboard paste works across many Windows apps without app-specific integrations. It is simple and good enough for a PoC, but it has edge cases like Slack paste debounce and clipboard managers.

### What is the biggest risk?

Silent VSR accuracy and robustness. Lighting, face angle, camera quality, and phrase choice can all hurt it. That is why the eval harness and known-failure logs matter.

### How do we know if a change helped?

Run `python -m sabi eval` on the same local dataset before and after. Compare WER and latency percentiles in the generated reports.

### What should I say if a demo fails?

Name the stage. For example: "The TUI says Ollama is offline, so cleanup was bypassed," or "The JSONL log shows no face, so the silent pipeline correctly refused to paste." The goal is not to pretend every case works; it is to show we can attribute failures.

## Quick Defense Script

If you need a 30-second explanation:

> "This repo is a local Windows PoC for dictation. There are two current paths: silent dictation from webcam lip movement using Chaplin VSR, and audio dictation from microphone speech using faster-whisper. Both go through optional local Ollama cleanup and then paste into the focused app. The TUI shows live status, and the eval harness replays fixed recordings to measure WER and per-stage latency. The main risks are VSR accuracy, lighting/face tracking, and Windows paste edge cases, and we log each of those so failures are explainable."
