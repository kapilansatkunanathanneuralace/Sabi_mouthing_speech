# Architecture, Vision & Product Roadmap

## TL;DR

The system is a multimodal voice + vision assistant. Audio handles the easy case (speak aloud, dictate, join meetings), vision handles the hard case (silent speech via lip reading, noisy environments, context awareness). The MVP is audio-first with Chaplin as the silent-speech validator, and vision graduates from "lip reading only" to "full scene + screen understanding" over the following months.

---

## Recommended Architecture

Four layers, each swappable:

### 1. Input Layer

- **Microphone** — 16kHz audio stream, VAD-gated so we're not running ASR on silence
- **Webcam** — face/lip crop at 25 fps for VSR; lower-res (256px) full-frame for scene context
- **Screen capture** (optional) — triggered only for context-aware commands, not always-on
- **Hotkey / wake trigger** — push-to-talk, toggle, or voice wake, user's choice

### 2. Core Models

| Function | MVP | Upgrade path |
| --- | --- | --- |
| ASR | faster-whisper small (INT8) | NVIDIA Parakeet TDT (CUDA) |
| VSR (lip reading) | Chaplin / Auto-AVSR | VALLR or custom fine-tune |
| LLM cleanup | Ollama 3B local | 7B local or hosted fallback |
| TTS | Kokoro-82M via RealtimeTTS | Voice-cloned Kokoro per user |
| Vision (scene) | None at MVP | Small VLM (Moondream / Florence-2) |

### 3. Fusion Layer

The fusion layer is where this gets interesting. Rather than picking ASR *or* VSR, we run both when possible and weight by confidence:

- Audio confident, face visible → ASR primary, VSR as tiebreaker on low-confidence words
- Audio noisy (café, meeting), face visible → upweight VSR, use it to correct ASR
- No face visible → pure ASR
- No audio (muted, silent speech) → pure VSR

This is the single biggest accuracy lever and also the main reason vision isn't optional.

### 4. Output Layer

- **Text injection** — clipboard + paste via PyAutoGUI. Faster and more reliable than character-by-character typing, handles emoji and unicode.
- **TTS output** — Kokoro-82M → BlackHole (Mac) or VB-Cable (Windows) virtual mic. Routes into Zoom/Meet/Teams as your voice.
- **Overlay UI** — transparent floating window for live transcript / confidence / mode indicator.

### 5. Orchestration

- Mode switcher: Dictation / Meeting / Silent / Always-on
- Privacy switch (camera off, mic off, fully local)
- Per-app rules (auto-mode-switch when Zoom is focused, etc.)

---

## Core User Flows

Two end-to-end flows drive the product. Everything in the architecture above exists to make these work reliably.

### Flow 1 — Silent Dictation (mouth in front of computer → text input)

You're at your laptop. You don't want to speak aloud — open office, partner asleep, can't concentrate through speech, or just don't feel like it. You hold a hotkey, mouth your words at the camera, and text appears in whatever app is focused (Slack, Docs, Notes, VS Code, anywhere).

```
[Webcam]
    ↓  face/lip crop at 25 fps
[Lip Detection]
    ↓  isolated mouth region
[VSR Model — Chaplin / Auto-AVSR]
    ↓  raw text prediction
[LLM Cleanup — Ollama 3B]
    ↓  punctuation, filler removal, casing
[Clipboard]
    ↓
[PyAutoGUI paste] → focused app
```

**Step-by-step with latency budget:**

| # | Step | Latency |
| --- | --- | --- |
| 1 | User triggers silent mode (hotkey, toggle, or auto) | instant |
| 2 | Webcam streams lip crop at 25 fps | real-time |
| 3 | Lip detection isolates mouth region | ~10 ms |
| 4 | VSR model predicts text from lip motion | 100–200 ms |
| 5 | LLM cleanup (filler, punctuation, casing) | 50–150 ms |
| 6 | Text placed on clipboard | <5 ms |
| 7 | PyAutoGUI paste into focused app | <20 ms |
|  | **Total end-to-end after mouth stops** | **~300–400 ms** |

**UX notes:**

- Hotkey trigger = "only record when I want to," privacy-safe default
- If camera can't see the mouth (occluded, looking away), fail silently rather than emit garbage text
- Live overlay shows transcript as it's being predicted so the user can cancel bad output before paste
- App-aware cleanup: tone for Slack vs. Docs vs. code comments is different; the LLM step uses the focused app as context

### Flow 2 — Silent Meeting (mouth in meeting → your voice into the call)

You're on Zoom / Meet / Teams. You want to talk but can't — family member in the room, sore throat, you're in a café, or you just prefer not to speak aloud. You mouth your words, and the meeting hears a voice (synthesized, or your cloned voice later) speaking them in real time.

```
[Webcam]
    ↓  face/lip crop at 25 fps
[Lip Detection]
    ↓
[VSR Model — Chaplin / Auto-AVSR]
    ↓  raw text
[LLM Cleanup — Ollama 3B, meeting register]
    ↓  clean, spoken-style text
[TTS — Kokoro-82M via RealtimeTTS]
    ↓  audio stream (97 ms TTFB)
[Virtual Mic — BlackHole (Mac) / VB-Cable (Windows)]
    ↓
[Zoom / Meet / Teams] → other participants hear "your" voice
```

**One-time setup (required for this flow):**

- Install BlackHole (Mac) or VB-Cable (Windows)
- In the meeting app's audio settings, select the virtual device as the input microphone
- In our app, select the virtual device as the TTS output sink

**Step-by-step with latency budget:**

| # | Step | Latency |
| --- | --- | --- |
| 1 | User toggles silent meeting mode | instant |
| 2 | Webcam captures lip region at 25 fps | real-time |
| 3 | Lip detection + VSR | 100–200 ms |
| 4 | LLM cleanup (meeting register, not chat) | 50–150 ms |
| 5 | TTS synthesis (Kokoro-82M) | 97 ms TTFB |
| 6 | Audio routed to virtual mic | <20 ms |
| 7 | Meeting app picks up audio as its microphone | pipeline-dependent |
|  | **Total: mouth stop → others hear your voice** | **~400–500 ms** |

**UX notes:**

- TTS streams — it can start speaking before the full sentence is decoded, which hides latency
- Voice cloning upgrade (Phase 3 of roadmap) means it's the user's actual voice, not the Kokoro default
- Mute/unmute toggle must be instant — never block the meeting mic behind the pipeline
- "Push to mouth" mode for introverts: only synthesize while actively mouthing, dead silence otherwise
- App detection: when Zoom/Meet/Teams is frontmost, default to meeting mode rather than dictation mode

---

## How Vision Gets Used (tiered rollout)

### Tier 1 — Lip reading (MVP)

Chaplin / Auto-AVSR handles silent speech input. This is the headline feature — user can type by mouthing words without making sound. Validates the entire thesis.

### Tier 2 — Audio-visual fusion

Once ASR and VSR are both running, fuse their outputs. Biggest accuracy lift in the real-world environments people actually work in (open offices, cafés, shared spaces). This is where vision earns its keep for the 90% of users who *can* speak aloud.

### Tier 3 — Scene & screen context

- What app is the user in? (dictating into Slack vs. writing code vs. replying to email — different tone, different corrections)
- What's on screen? (if user says "summarize this," we know what "this" is)
- Who else is in the room? (switch to silent mode if someone walks up)

### Tier 4 — Gaze + gesture (future)

Gaze for cursor placement, head nods for confirmation, eyebrow raise to toggle listening. Only worth building once the core is rock-solid — gesture input has a high "looks great in a demo, hates real life" failure mode.

---

## Product Roadmap

### Phase 1 — Foundation (Weeks 1–3)

This is the 24-ticket MVP from the build guide.

- **Week 1:** Chaplin installed, faster-whisper wired up, text injection working. Silent speech demo works end-to-end on one laptop.
- **Week 2:** Dictation + silent speech both functional. Full internal demo.
- **Week 3:** Meeting mode shipped — TTS → virtual mic routed to Zoom. First real meeting using synthesized voice.

### Phase 2 — Fusion & polish (Weeks 4–6)

- Audio-visual fusion live (confidence-weighted ASR + VSR)
- Filler removal and LLM cleanup pass
- Mode switcher, hotkeys, per-app rules
- Edge-case hardening: accents, background noise, multiple faces in frame, camera obscured

### Phase 3 — Extend (Months 2–3)

- Scene & screen context (Tier 3 vision)
- Voice cloning for TTS — user's own voice in meetings, not Kokoro default
- Personalization: per-user vocab, style, and correction learning
- Cross-platform: ship Windows (VB-Cable) alongside Mac; Linux after that

### Phase 4 — Depth (Months 3–6)

- End-to-end latency target: <200ms from speech-end to text-appear
- Multi-lingual support (Whisper handles this natively; VSR is the bottleneck)
- Conversational TTS (not one-shot — actual back-and-forth with interruption handling)
- If BCI/neural signals become available: integrate as a third input modality alongside audio + vision

### Phase 5 — Scale (6+ months)

- Cloud sync across devices
- Enterprise mode (compliance, audit logs, admin controls)
- Open API for third-party integrations
- Hardware collab / reference integrations (glasses, wearables) if/when relevant

---

## Open decisions

- **GPU baseline:** CUDA-only for Parakeet, or invest in MPS (Apple Silicon) support? Affects who can run the better ASR locally.
- **Always-on vision:** privacy + battery tradeoff. Default probably "on while app is frontmost," off otherwise.
- **Local vs hybrid cloud:** how much are we willing to send off-device? MVP should be fully local; after that, optional cloud fallback for hard audio or long-form.
- **Fine-tuning strategy:** per-user adaptation (small LoRA) vs. population-level fine-tunes only.

---

## Risks & mitigations

- **Lip reading in the wild is hard.** Chaplin is a validator, not a production model. Budget a fine-tune on real user data by Month 2.
- **Latency budget is tight.** 97ms TTS + ~200ms ASR + network + injection can get to perceptible lag. Every ms matters — measure end-to-end from day one.
- **Privacy perception.** Camera + mic always-on is a non-starter for most users. Lead with "off by default, push-to-talk" framing.
- **Cross-platform audio routing.** BlackHole is Mac-only, VB-Cable is Windows, Linux has no clean analog — plan to delay Linux or use PulseAudio modules.
- **Model drift / upgrades.** Lock model versions per release; don't silently pull new weights.

---

## Packaging & Distribution — Simple Path (Electron + React)

If we want the path of least resistance instead of Tauri, the answer is **Electron + React + Python sidecar**. Same shape as the more advanced plan, but using the most well-trodden desktop stack on the web — every dev knows it, every AI tool can help with it, and the answer to almost any question already exists on Stack Overflow.

### Architecture (3 pieces)

1. **React UI (Vite)** — overlay, settings panel, onboarding wizard, license screens. Pure web tech, zero native code.
2. **Electron shell (Node main process)** — OS-level stuff: hotkeys (`globalShortcut`), tray icon, accessibility permissions, clipboard, app lifecycle. Bridges the React UI to the Python sidecar via IPC.
3. **Python sidecar (PyInstaller)** — the ML pipeline (faster-whisper, Chaplin, Ollama, Kokoro). Runs as a child process spawned by Electron, communicates over stdin/stdout JSON-RPC or a local WebSocket.

```
[React UI]  ↔  [Electron Main]  ↔  [Python Sidecar]
  (UI)         (system access)      (ML pipeline)
```

This split is intentional: each piece is best-in-class for its job, and we don't have to port any ML to JavaScript.

### Why Electron over Tauri for path-of-least-resistance

- Team is React-fluent already; no Rust learning curve
- Bigger community, more npm packages for niche needs (virtual audio bindings, accessibility hooks)
- `electron-builder` is the most mature desktop packaging tool that exists
- Trade-off: bundle is ~150MB instead of ~10MB and uses ~200MB more RAM. For our user (M-series Macs and modern PCs), this is invisible.

### Dev workflow

- `npm run dev` — Vite serves React with hot reload, Electron loads it from [localhost](http://localhost), Python sidecar runs in dev mode
- All three pieces hot-reload independently
- Single command to package: `npm run dist` — spits out signed .dmg + .exe

### Packaging & signing

- **electron-builder** handles macOS + Windows + Linux from one config
- **Mac:** Apple Developer account ($99/yr), Developer ID Application + Installer certs, notarization via `electron-notarize`
- **Windows:** EV code signing cert from DigiCert/Sectigo (~$300/yr) — required to avoid SmartScreen warnings
- Models downloaded from Cloudflare R2 on first launch (don't bundle weights — installer stays under 200MB)
- BlackHole `.pkg` / VB-Cable `.exe` bundled inside the installer, run from the setup wizard

### Distribution

- **Direct download** from the website (`download.neuralace.co/mac`, `/windows`)
- **No App Stores** — Mac sandbox blocks virtual audio + text injection; Windows Store is barely worth the friction
- Landing page does OS detection + serves the right installer
- Single-click install on both platforms, signed so no scary warnings

### Auto-update

- **electron-updater** (built into electron-builder)
- Checks on launch + every 24h
- Ships updates from a GitHub release or S3 bucket
- Staged rollout via percentage flags so a bad release doesn't hit everyone at once

### One-time user setup (the unavoidable friction)

This is the same problem any plan has — system-level audio + accessibility require user consent. The order:

1. Download the .dmg / .exe → double-click → install
2. App opens onboarding wizard
3. Walk through permissions: Camera → Mic → Accessibility (for paste) → Install BlackHole/VB-Cable (for meeting mode)
4. Sign in, or skip (anonymous local mode)
5. First-launch model download (~3GB, progress bar)
6. Done — system tray icon live, hotkey active

### Why not pure web app

Browsers can't inject text into other apps and can't create virtual mics. A PWA gets us "dictate into our web app" but not "dictate into Slack / VS Code / Notion" or "talk in Zoom as the synthesized voice." That's most of the product.

### Why not fully native (Swift on Mac, C# on Windows)

Two codebases to maintain, neither in a language the team is fluent in. Electron lets one team ship to both platforms from one repo. The 8 hours/week saved on platform parity buys way more product than the 50MB bundle savings cost.

### 2-week ship plan

| Days | Work |
| --- | --- |
| 1–3 | electron-builder skeleton, React UI scaffolded, Python sidecar wired via stdin/stdout |
| 4–6 | Onboarding wizard, permissions flow, model download with progress bar |
| 7–9 | BlackHole/VB-Cable installer integration, virtual mic detection |
| 10–11 | Code signing setup (Mac + Windows), notarization in CI |
| 12–13 | electron-updater wired up, staged rollout config, landing page download flow |
| 14 | Internal dogfood, capture install metrics |

Shippable v1 in two weeks if focused.

---

> Parent page: [Silent Speech / Voice System — Build Guide](https://www.notion.so/Silent-Speech-Voice-System-Build-Guide-34bb1d31499481bf85c9c292872db550?pvs=21)
>