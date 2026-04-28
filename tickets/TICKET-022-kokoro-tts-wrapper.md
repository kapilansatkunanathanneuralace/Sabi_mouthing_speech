# TICKET-022 - Kokoro TTS wrapper (RealtimeTTS streaming)

Phase: 1 - ML PoC
Epic: Output
Estimate: L
Depends on: TICKET-002
Status: Not started

## Goal

Wrap Kokoro-82M behind `TTSEngine.speak(text) -> TTSStream` using `RealtimeTTS`. The engine must start producing audio frames before the full sentence is synthesized so meeting mode can stream speech into the virtual mic with low perceived latency. The audio consumer is TICKET-023, so this ticket does not open any output device itself.

## System dependencies

- Kokoro checkpoint + voices bundle, downloaded on first run via RealtimeTTS.
- GPU inference strongly preferred; CPU should still run with a latency warning.
- Windows phonemizer requirements documented based on the RealtimeTTS Kokoro engine path that ships.

## Python packages

Add to `pyproject.toml` dependencies:

- `RealtimeTTS[kokoro]` at the current compatible release.
- `soundfile` for smoke-test WAV output.
- `phonemizer` only if the Kokoro extra does not pull it transitively.

Already available:

- `torch`, `torchaudio`, `numpy`.

## Work

- Create `src/sabi/output/tts.py`.
- Define `TTSConfig`, `TTSFrame`, and `TTSStream`.
- Implement `TTSEngine` with lazy initialization, optional warm-up, single-utterance locking, stream chunking, first-frame latency measurement, and max-duration cutoff.
- Add `python -m sabi tts-smoke "hello meeting"` to synthesize a WAV under `reports/` and print latency.
- Write `tests/test_tts.py` with RealtimeTTS monkeypatched to emit fake PCM.

## Acceptance criteria

- [ ] `python -m sabi tts-smoke "hello meeting"` produces a playable 24 kHz mono WAV under `reports/`.
- [ ] First-frame TTFB is logged and is under 150 ms on the reference GPU laptop after warm-up.
- [ ] CPU-only hardware succeeds with a warning that meeting-mode latency will be worse.
- [ ] Every yielded `TTSFrame` is the configured frame length except the final short frame.
- [ ] `TTSStream` closes cleanly on exhaustion or caller close.
- [ ] Latency appended to `reports/latency-log.md` stage `tts`.
- [ ] Unit tests pass with monkeypatched RealtimeTTS.

## Out of scope

- Voice cloning.
- Audio routing / playback.
- TTS caching.
- Multi-language voices.
- Interruption / barge-in.

## Notes

- Keep synthesis single-utterance at a time.
- Do not resample inside `speak()`; TICKET-023 handles sink sample-rate matching.

## References

- Roadmap core models table (project_roadmap.md line 27).
- Roadmap Flow 2 step 5 (project_roadmap.md line 131).
- Roadmap Flow 2 UX notes (project_roadmap.md lines 138-139).
