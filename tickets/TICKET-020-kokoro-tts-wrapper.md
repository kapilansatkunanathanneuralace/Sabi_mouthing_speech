# TICKET-020 - Kokoro TTS wrapper (RealtimeTTS streaming)

Phase: 1 - ML PoC
Epic: Output
Estimate: L
Depends on: TICKET-002
Status: Not started

## Goal

Wrap Kokoro-82M behind `TTSEngine.speak(text) -> TTSStream` (a generator of float32 24 kHz mono PCM frames) using the `RealtimeTTS` library with its Kokoro engine. The engine must start producing audio frames before the full sentence is synthesized - the roadmap calls out 97 ms time-to-first-byte as the target, and streaming is the whole reason we can hide the rest of the pipeline behind the TTS playback. The audio consumer is TICKET-021 (virtual mic sink), so this ticket does **not** open any output device itself.

## System dependencies

- Kokoro checkpoint + voices bundle, downloaded on first run via RealtimeTTS's own fetcher. Approx 350 MB.
- GPU inference strongly preferred (CPU is 5-10x slower and will not meet the TTFB budget); we do not hard-require CUDA but log a warning.
- Windows: `espeak-ng` is often pulled by Kokoro variants for G2P; if RealtimeTTS's Kokoro engine bundles a phonemizer we skip this. Document whichever path actually ships.

## Python packages

Add to `pyproject.toml` dependencies:

- `RealtimeTTS[kokoro]==0.4.8` (or the current release that pins Kokoro). We use the extras-installed variant so the Kokoro engine and tokenizer come in together.
- `soundfile==0.12.1` - for writing TTS output to wav during smoke tests and eval.
- `phonemizer==3.2.1` (if RealtimeTTS's Kokoro extra does not pull it transitively). Leave out if unnecessary on install.

Already available (TICKET-002):

- `torch`, `torchaudio`
- `numpy`
- `sounddevice` (used by the sink ticket, not here).

## Work

- Create `src/sabi/output/tts.py`.
- Define `TTSConfig` (engine `"kokoro"`, voice name (default from Kokoro's en voices), sample_rate 24000, device `"cuda" | "cpu" | "auto"`, max_output_seconds 30, frame_ms 20, warm_up_on_init True).
- Define `TTSFrame` dataclass: `samples` (float32 mono at config sample rate, length = frame_ms * sample_rate / 1000), `is_first` bool, `is_last` bool, `timestamp_ns`, `synth_latency_ms` (only set on `is_first` for TTFB measurement).
- Define `TTSStream` as a finite generator of `TTSFrame` that the virtual mic sink consumes.
- Implement `TTSEngine`:
  - Lazy-initializes `RealtimeTTS.TextToAudioStream` with `RealtimeTTS.KokoroEngine(voice=...)` on first call (or at construction if `warm_up_on_init=True`). RealtimeTTS handles chunking and pushes PCM into a queue as Kokoro generates it.
  - `.warm_up()`: runs a single-syllable synthesis ("ok") to pay the first-run compile/graph cost.
  - `.speak(text: str) -> TTSStream`:
    - Starts the underlying RealtimeTTS stream.
    - Yields `TTSFrame`s as audio arrives, rechunked to exactly `frame_ms` at the configured sample rate so the sink can schedule them deterministically.
    - Measures wall-clock from `.speak()` call to first yielded frame; attaches to the first frame's `synth_latency_ms`.
    - Honors `max_output_seconds`: force-closes the stream and raises `TTSOverrunError` if Kokoro produces more audio than expected (catches pathological runs away).
  - Thread-safety: `.speak()` serializes calls on an internal lock - only one utterance synthesizes at a time. The meeting pipeline enforces the same policy above.
- CLI: `python -m sabi tts-smoke "hello meeting"` synthesizes to `reports/tts_smoke_<ts>.wav` via `soundfile.write` and prints TTFB + total synth time.
- Write `tests/test_tts.py` with `RealtimeTTS.TextToAudioStream` monkeypatched to push fake PCM into the queue, verifying: frame chunking math, first-frame TTFB capture, lock serialization, max-duration cutoff.

## Acceptance criteria

- [ ] `python -m sabi tts-smoke "hello meeting"` produces a playable 24 kHz mono wav under `reports/` in under 2 s on the reference GPU laptop.
- [ ] First-frame TTFB logged in the smoke run is under 150 ms on GPU (loosened from the 97 ms roadmap target to account for our RealtimeTTS abstraction; tightening is a later optimization).
- [ ] On CPU-only hardware the smoke command still succeeds but prints a WARNING that meeting-mode latency will not meet the roadmap budget.
- [ ] Every yielded `TTSFrame` is exactly `frame_ms * sample_rate / 1000` samples except the last, which may be short; the consumer in TICKET-021 can rely on that.
- [ ] `TTSStream` is fully consumable once and closes cleanly on exhaustion or on caller `close()`.
- [ ] Latency appended to `reports/latency-log.md` stage `tts`.
- [ ] Unit tests pass with monkeypatched RealtimeTTS.

## Out of scope

- Voice cloning - explicit Phase 3 upgrade path in the roadmap (project_roadmap.md line 188). Our PoC uses the Kokoro default voice.
- Audio routing / playback - belongs to TICKET-021. This ticket yields frames, it does not play them.
- TTS caching - no repeated-phrase cache for PoC; every `speak()` resynthesizes.
- Multi-language voices - PoC fixes English. The config knob is there for a later ticket.
- Interruption / barge-in - meeting mode does not need mid-utterance stop for PoC.

## Notes

- Keep the TTS process single-utterance at a time. Trying to overlap Kokoro runs on a single GPU usually hurts TTFB more than it helps throughput.
- Do not resample inside `speak()`. 24 kHz is Kokoro's native rate; TICKET-021 deals with matching VB-Cable's expected rate.

## References

- Roadmap core models table (project_roadmap.md line 27) - "TTS: Kokoro-82M via RealtimeTTS" is the MVP target.
- Roadmap Flow 2 step 5 (project_roadmap.md line 131) - "TTS synthesis (Kokoro-82M) 97 ms TTFB" is the budget this ticket measures against.
- Roadmap Flow 2 UX notes (project_roadmap.md lines 138-139) - "TTS streams - it can start speaking before the full sentence is decoded, which hides latency" is the reason streaming is non-negotiable here.
