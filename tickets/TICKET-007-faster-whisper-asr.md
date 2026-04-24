# TICKET-007 - faster-whisper ASR baseline

Phase: 1 - ML PoC
Epic: ASR
Estimate: M
Depends on: TICKET-002
Status: Not started

## Goal

Wrap `faster-whisper` behind `ASRModel.transcribe(utterance) -> ASRResult(text, segments, avg_logprob, per_word_confidence, latency_ms)` so the audio pipeline (TICKET-012) can use the same result shape as the VSR pipeline. Uses the `small` INT8 checkpoint from the roadmap MVP table. Per-word confidences are deliberately preserved because Phase 2 fusion (roadmap Tier 2, deferred) will need them.

## System dependencies

- Windows: no extra system deps beyond what ships with the `faster-whisper` wheel (CTranslate2 brings its own runtime).
- Disk: ~500 MB for the `small` model once downloaded to the local cache.
- GPU acceleration via CTranslate2 CUDA if available; otherwise CPU INT8 works on modern laptops inside the 150-300 ms range per short utterance.

## Python packages

Already installed in TICKET-002:

- `faster-whisper`
- `numpy`

No new additions.

## Work

- Create `src/sabi/models/asr.py`.
- Define `ASRModelConfig` (model size `"small"`, compute type `"int8_float16"` when CUDA is present else `"int8"`, beam size 1 for latency, language `"en"` (configurable), vad_filter `False` because we already VAD-gated upstream).
- Define `ASRResult` dataclass mirroring `VSRResult` from TICKET-005: `text`, `segments` (list of dicts with start/end/text/avg_logprob), `confidence` (normalized 0-1, derived from `avg_logprob`), `per_word_confidence` (list of `(word, start, end, probability)`), `latency_ms`.
- Implement `ASRModel`:
  - Lazy-loads `WhisperModel` on first call so CLI startup stays fast.
  - `.transcribe(utterance: Utterance) -> ASRResult`: feeds `utterance.samples` directly (float32 mono 16 kHz matches faster-whisper's expected input). Captures wall-clock latency around the `model.transcribe` call and decoding.
  - `.warm_up()`: runs one dummy inference on a 0.5 s silent clip to pay the JIT / kernel init cost before the user hits the hotkey.
  - Returns an empty-string result (not an error) when the utterance is silence or below a configured SNR.
- Add a CLI smoke test: `python -m sabi asr-smoke <wav_path>` prints text, segments, latency.
- Provide a regression fixture at `data/fixtures/asr/hello_world.wav` with ground-truth transcript in `hello_world.txt`. The test asserts WER < 10% on this clip with the `small` INT8 setting, as a floor check.
- Write `tests/test_asr.py` that monkeypatches `WhisperModel` to validate: config wiring, confidence conversion, empty-input handling, per-word list shape.

## Acceptance criteria

- [ ] `python -m sabi asr-smoke data/fixtures/asr/hello_world.wav` prints the expected transcript with WER < 10% and latency under 500 ms on the reference laptop (CPU INT8) or under 200 ms with CUDA.
- [ ] `ASRModel.transcribe(empty_utterance)` returns `ASRResult(text="", confidence=0.0, ...)` without raising.
- [ ] Per-word confidences are populated when the model supports them and the empty list when they are not, never `None`.
- [ ] Latency is appended to `reports/latency-log.md` for each smoke-test run with stage `asr` and the detected device.
- [ ] First-call inference latency after `warm_up()` is within 20% of steady-state inference latency (asserted in the smoke script, logged rather than hard-failed in test).

## Out of scope

- Streaming partial hypotheses - we return complete transcripts per utterance. Streaming is a Phase 2 latency optimization.
- Multi-language handling - PoC fixes the language to English. The config leaves the knob in place for future tickets.
- Upgrade to NVIDIA Parakeet TDT - explicit "upgrade path" in the roadmap core models table, not PoC.
- Any integration with the LLM cleanup pass - that composition happens in TICKET-012.

## Notes

- `compute_type="int8_float16"` is the fastest common mode on consumer NVIDIA cards with modest VRAM; pure `int8` is the fallback on CPU and also the safe bet if CUDA runtime mismatches the wheel.
- Keep `vad_filter=False` - letting faster-whisper run its own internal VAD after TICKET-006 already gated silence just burns latency.

## References

- Roadmap core models table (project_roadmap.md line 24) - "ASR: faster-whisper small (INT8)" is the MVP target.
- Roadmap Flow 1 latency spirit (project_roadmap.md lines 79-88) - we set the audio-baseline budget to match so TICKET-014 can compare silent vs audio honestly.
- Roadmap risks, latency budget (project_roadmap.md line 222) - "97ms TTS + ~200ms ASR" is the perceived ceiling this model must stay under.
