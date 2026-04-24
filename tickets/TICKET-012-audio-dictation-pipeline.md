# TICKET-012 - Audio-dictation pipeline (PoC-2 baseline)

Phase: 1 - ML PoC
Epic: Pipeline
Estimate: M
Depends on: TICKET-006, TICKET-007, TICKET-008, TICKET-009, TICKET-010
Status: Not started

## Goal

Wire TICKET-006 (mic + VAD) + TICKET-007 (faster-whisper) + TICKET-008 (cleanup) + TICKET-009 (paste) + TICKET-010 (hotkey) into a working **spoken dictation** pipeline. Exposes `python -m sabi dictate`. This is the A/B baseline for the silent pipeline: we want like-for-like latency and quality numbers so TICKET-014's eval harness can draw a defensible comparison.

## System dependencies

All inherited from the tickets above. No webcam required for this pipeline.

## Python packages

No new dependencies; everything is already pinned.

## Work

- Create `src/sabi/pipelines/audio_dictate.py`.
- Define `AudioDictateConfig` composing `MicConfig`, `ASRModelConfig`, `CleanupConfig`, `InjectConfig`, `HotkeyConfig`. Single `configs/audio_dictate.toml` overlays the defaults.
- Implement `AudioDictatePipeline`:
  - On construction: instantiates components, warms up the ASR model via `ASRModel.warm_up()` and Ollama via `TextCleaner.is_available()`. Does not open the mic yet.
  - Supports two capture modes via config:
    - `trigger_mode = "push_to_talk"`: mic opens on `on_trigger_start`, records until `on_trigger_stop`, bypasses VAD and always emits the full held segment.
    - `trigger_mode = "vad"`: mic runs continuously after one-time hotkey activation, VAD segments into utterances, each utterance goes through the rest of the pipeline. Pressing the hotkey a second time deactivates the pipeline (not just the current utterance).
  - On each complete utterance: `ASRModel.transcribe` -> `TextCleaner.cleanup` -> `paste_text`. Emits `UtteranceProcessed` with the same shape as TICKET-011 but a different `pipeline="audio"` tag.
  - Confidence floor handling: if `ASRResult.confidence` is below a configurable threshold (default 0.4, tuned in eval), the overlay shows the raw text but withholds paste unless user confirms with F12 - matches the VSR pipeline's "cancel bad output before paste" UX.
- Stage-timing contract: `latencies = {"capture_ms": ..., "vad_ms": ..., "asr_ms": ..., "cleanup_ms": ..., "inject_ms": ..., "total_ms": ...}`. `"capture_ms"` is trigger-stop minus first-voiced-frame for fair comparison with the silent pipeline's `"capture_ms"`.
- Structured log at `reports/audio_dictate_<date>.jsonl`; TICKET-014 merges this with the silent log.
- CLI: `python -m sabi dictate` runs until Ctrl+C. `--mode push-to-talk|vad` overrides trigger mode. `--dry-run` routes through the paste dry-run path. `--force-cpu` makes faster-whisper run CPU-only.
- Unit test `tests/test_audio_dictate.py` uses stub components (fake `MicrophoneSource` yielding a canned `Utterance`, stub `ASRModel` returning canned `ASRResult`, stub `TextCleaner`, dry-run paste) to verify wiring, latency plumbing, and confidence-floor withholding.

## Acceptance criteria

- [ ] `python -m sabi dictate` starts and binds the hotkey without crashing after `python -m sabi probe` passes.
- [ ] Pressing and holding the hotkey while speaking a short phrase produces pasted text within 500 ms of release on the reference laptop (CUDA) / under 800 ms CPU-only.
- [ ] In VAD mode, speaking three short phrases back-to-back produces three separate pasted outputs, each correctly segmented.
- [ ] With Ollama off, output falls back to raw ASR and pastes unchanged.
- [ ] `reports/audio_dictate_<date>.jsonl` records one JSON object per utterance.
- [ ] On confidence below the threshold, the default behavior (withhold paste pending F12) is observable in the overlay and log, and can be disabled via config.
- [ ] Unit test passes with all hardware mocked.
- [ ] Latency rows written to `reports/latency-log.md` with `ticket=TICKET-012` for every smoke run.

## Out of scope

- Audio-visual fusion with the silent pipeline - deferred to Phase 2 (roadmap Tier 2). This ticket stays pure-audio.
- Streaming ASR partials - ASR still returns complete utterances. Tightening latency to roadmap targets is a Phase 2 task.
- App-aware cleanup - `CleanupContext.focused_app` is plumbed but not used by the PoC prompt.
- Meeting mode (TTS out) - Flow 2 of the roadmap, explicitly out of PoC scope.

## Notes

- Keep `AudioDictatePipeline` and `SilentDictatePipeline` structurally parallel so the eval harness can treat them interchangeably: same `UtteranceProcessed` shape, same JSONL schema, same latency-log format. If a field is not applicable to one pipeline, it is present with value `null` rather than missing.
- faster-whisper's `int8_float16` compute type shaves meaningful time off ASR on GPU machines; if a CUDA machine comes out slower than CPU int8 in eval, that mode was silently not selected - assert the chosen compute type in the log.

## References

- Roadmap core models table (project_roadmap.md lines 22-28) - "ASR: faster-whisper small (INT8)" + "LLM cleanup: Ollama 3B local" is the audio stack this pipeline wires.
- Roadmap Phase 1 Week 2 (project_roadmap.md line 175) - "Dictation + silent speech both functional. Full internal demo." - this ticket is the dictation half.
- Roadmap Flow 1 UX note (project_roadmap.md line 94) - "Live overlay shows transcript as it's being predicted so the user can cancel bad output before paste" - the confidence-floor behavior is the first pass at this policy.
