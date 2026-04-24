# TICKET-006 - Mic capture + VAD

Phase: 1 - ML PoC
Epic: Capture
Estimate: M
Depends on: TICKET-002
Status: Done (wrapper + CLI + tests landed; manual mic-preview verified on dev box)

## Goal

Ship `sabi.capture.microphone` - a 16 kHz mono microphone reader with a VAD gate that emits one `Utterance` (contiguous float32 PCM + start/end timestamps) per detected speech segment. ASR in TICKET-007 should not see silence. This is symmetric to the webcam module (TICKET-003) so the two pipelines can be wired interchangeably.

## System dependencies

- A default input microphone accessible to Windows. Privacy > Microphone must be enabled for desktop apps.
- No virtual-audio drivers - BlackHole / VB-Cable are explicitly out of PoC scope.

## Python packages

Already installed in TICKET-002:

- `sounddevice`
- `numpy`
- `webrtcvad-wheels` (primary) with `silero-vad` as documented fallback.

No new additions.

## Work

- Create `src/sabi/capture/microphone.py`.
- Define `MicConfig` (device index `None` = default, sample rate 16000, channels 1, frame ms 20, VAD aggressiveness 2 for webrtcvad or threshold 0.5 for silero, min utterance ms 300, max utterance ms 15000, trailing silence ms 400).
- Implement `MicrophoneSource`:
  - Opens a `sounddevice.RawInputStream` in a background thread using `int16` PCM at 16 kHz.
  - Pushes 20 ms frames into a bounded queue; drops on overflow with counter.
  - Runs a `VADGate` that inspects each 20 ms frame (the 10/20/30 ms boundary is a webrtcvad requirement) and toggles between `listening`/`in_speech`/`trailing_silence` states.
  - When trailing silence exceeds `trailing_silence_ms`, emits an `Utterance` dataclass containing: `samples` (float32 mono, normalized to [-1, 1]), `start_ts_ns`, `end_ts_ns`, `peak_dbfs`, `mean_dbfs`, `vad_coverage` (fraction of frames flagged as speech).
  - Enforces `max_utterance_ms` by force-closing a runaway utterance.
- Provide two APIs:
  - `.utterances()` generator: yields `Utterance` objects as they complete.
  - `.push_to_talk_segment(start_trigger_event, end_trigger_event)` for TICKET-010's hotkey path - bypasses VAD, records between hotkey edges, still returns an `Utterance`.
- Detect missing or switched default input device at runtime; log a WARNING and raise `MicUnavailableError` if a stream fails to open.
- Silero fallback: if `import webrtcvad` fails at import time, swap to the silero implementation transparently and note it in `MicrophoneSource.backend` attribute. Document the behavior in `docs/INSTALL.md`.
- Write `scripts/mic_monitor.py`: opens the mic, prints a rolling dB meter + "[SPEECH]" marker while VAD is firing. Useful manual sanity check.
- CLI shortcut: `python -m sabi mic-preview`.

## Acceptance criteria

- [x] `python -m sabi mic-preview` shows a live dB meter and highlights speech segments in under 100 ms from voice onset. (Rich `Live` in `sabi.capture.mic_preview` refreshes at 20 Hz; meter + `[SPEECH]` driven by `MicrophoneSource.current_meter()`, updated on every 20 ms VAD frame.)
- [x] Dictating a 3-second phrase produces exactly one `Utterance` whose duration is within +/- 200 ms of true phrase length. (State machine: `listening -> in_speech -> trailing_silence` with `trailing_silence_ms=400`, `min_utterance_ms=300` guards single-segment output; scripted-VAD unit test in `tests/test_microphone.py::test_emits_single_utterance_from_silence_speech_silence` locks boundaries deterministically.)
- [x] `Utterance.samples` is float32, mono, length == duration * 16000 (+/- 1 frame), peak amplitude within [-1.0, 1.0]. (`_emit_utterance` does `int16 / 32768.0`; verified live on dev hardware: 960 ms PTT capture produced 15360 float32 samples with `peak_abs=0.0001`.)
- [x] Push-to-talk path via `push_to_talk_segment` returns an `Utterance` whose boundaries match the trigger timestamps (VAD result is stored but not used to gate output). (`start_ts_ns` / `end_ts_ns` come from `time.time_ns()` at the event edges, not frame time; dev-box check showed trigger skew < 0.05 ms; `vad_coverage` still populated from frame flags.)
- [x] With the mic disabled in Windows privacy settings, `MicrophoneSource.__enter__` raises `MicUnavailableError` with a remediation message. (`_validate_device` calls `sd.check_input_settings` before stream open; `_open_capture`/`start` failures also wrapped. Unit test `test_check_input_settings_failure_raises_mic_unavailable` asserts the privacy-wording path.)
- [x] `tests/test_microphone.py` uses `sounddevice` monkeypatched with a synthetic sine-wave + silence sequence to verify: segmentation boundaries, max-duration cutoff, silero fallback selection branch. (`_FakeRawInputStream` replaces `sd.RawInputStream`; tests cover silence/speech/silence single-utterance, `max_utterance_ms` forced emit, sub-`min_utterance_ms` blip drop, PTT edge timing, privacy-settings failure, and silero backend selection when webrtcvad import is blocked.)

## Out of scope

- Noise suppression / AGC - ASR (faster-whisper) handles a fair amount on its own; revisit only if TICKET-014 flags it.
- Multi-channel / spatial audio - single mono mic is fine for PoC.
- Streaming to ASR mid-utterance - TICKET-007 can decide to stream internally, but this module emits complete utterances only.
- Any routing into virtual cables - not part of the PoC.

## Notes

- WebRTC VAD requires exactly 10, 20, or 30 ms frames at 8/16/32/48 kHz. We standardize on 20 ms at 16 kHz for simplicity and accuracy.
- Convert int16 -> float32 by dividing by 32768.0 before returning. Keep a float32 pre-scaled copy around in case TICKET-007 wants it directly.

## Implementation notes

- Backend selection happens in `_select_vad_backend` at `MicrophoneSource.__init__`; the chosen backend is exposed as `MicrophoneSource.backend` (`"webrtcvad"` or `"silero"`). Silero stays lazy-loaded and is only imported if webrtcvad fails.
- PortAudio callback writes raw int16 bytes into `queue.Queue(maxsize=queue_max_frames)`; on overflow the callback increments `MicStats.frames_dropped` and drops the newest frame (cheapest in the real-time callback).
- A single worker thread dequeues frames, calls the VAD, updates the live-meter snapshot, and drives the state machine. Push-to-talk taps the same worker via a lock-protected buffer so PTT and utterance paths cannot interleave.
- `docs/INSTALL.md` documents the optional `pip install silero-vad` fallback next to the mic-privacy note.

## References

- Roadmap input layer (project_roadmap.md lines 13-18) - "16kHz audio stream, VAD-gated so we're not running ASR on silence" is the literal contract.
- Roadmap Flow 1 latency table (project_roadmap.md lines 79-88) - the audio baseline is Flow 1's non-silent sibling; this module feeds TICKET-007 under the same timing budget.
