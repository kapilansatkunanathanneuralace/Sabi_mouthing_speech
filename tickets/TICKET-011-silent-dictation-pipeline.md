# TICKET-011 - Silent-dictation pipeline (PoC-1)

Phase: 1 - ML PoC
Epic: Pipeline
Estimate: L
Depends on: TICKET-005, TICKET-008, TICKET-009, TICKET-010
Status: Not started

## Goal

Wire TICKET-003 (webcam) + TICKET-004 (lip ROI) + TICKET-005 (Chaplin VSR) + TICKET-008 (cleanup) + TICKET-009 (paste) + TICKET-010 (hotkey) into a working silent-dictation PoC the dev can demo on their laptop. Exposes `python -m sabi silent-dictate`. Every stage logs its per-utterance latency so we can compare against the 300-400 ms roadmap budget and drive TICKET-014's report.

## System dependencies

All inherited from the tickets above: working webcam, CUDA (ideally), Ollama running (optional - bypasses gracefully), mic privacy not required for this pipeline.

## Python packages

No new dependencies. Everything is already pinned by TICKET-002 + TICKET-005.

## Work

- Create `src/sabi/pipelines/silent_dictate.py`.
- Define `SilentDictateConfig` composing the per-module configs: `WebcamConfig`, `LipROIConfig`, `VSRModelConfig`, `CleanupConfig`, `InjectConfig`, `HotkeyConfig`. Single `configs/silent_dictate.toml` overlays the defaults.
- Implement `SilentDictatePipeline`:
  - On construction: instantiates each component, warms up the VSR model and the Ollama cleaner, registers hotkey callbacks. Does **not** open the webcam yet (camera opens only when a trigger starts).
  - `on_trigger_start(TriggerEvent)`: opens `WebcamSource`, spins up a worker thread that pulls frames -> lip ROIs -> appends to an in-memory buffer. Renders a "recording" status to the overlay hook (TICKET-013 will subscribe).
  - `on_trigger_stop(TriggerEvent)`: closes capture, hands buffer to `VSRModel.predict`, feeds result text to `TextCleaner.cleanup`, then `paste_text`. Emits a structured event `UtteranceProcessed` with per-stage latencies.
  - If the lip ROI returned `None` for a majority of frames during the utterance (configurable, default 60%), pipeline aborts paste with an ERROR "camera could not see your mouth; nothing pasted" - honors the roadmap's fail-silently rule.
  - If `VSRResult.confidence` is below a configurable floor (default 0.35), overlay shows the raw text but withholds paste by default; user can press a configurable "force paste" key (default F12) within 1.5 s to push it anyway. Default behavior is documented clearly and tuned during TICKET-014 eval.
- Stage-timing contract: every `UtteranceProcessed` event carries a dict `latencies = {"capture_ms": ..., "roi_ms": ..., "vsr_ms": ..., "cleanup_ms": ..., "inject_ms": ..., "total_ms": ...}`. Write a row to `reports/latency-log.md` on every processed utterance with `ticket=TICKET-011`.
- CLI: `python -m sabi silent-dictate` runs the pipeline until Ctrl+C. `--dry-run` swaps paste for "print to stdout" (TICKET-009's dry-run flag). `--force-cpu` forces CPU inference for smoke-testing on machines without CUDA.
- Logging: structured JSON lines to `reports/silent_dictate_<date>.jsonl` with trigger events, per-stage timings, final text, final `used_fallback` flag. Eval harness (TICKET-014) re-reads this.
- Unit test `tests/test_silent_dictate.py` uses mock components (fake `WebcamSource` yielding fixture frames, stub `VSRModel` returning canned text, stub `TextCleaner` returning identity, dry-run paste, fake `TriggerBus`) to verify end-to-end wiring: trigger -> frames collected -> VSR called -> cleanup called -> paste called, with latencies plumbed into the event.

## Acceptance criteria

- [ ] `python -m sabi silent-dictate` starts without crashing on a machine that passes `python -m sabi probe`.
- [ ] Holding the hotkey while mouthing a short, simple phrase ("hello world") into the camera produces pasted text in the focused app within 500 ms (looser than the 300-400 ms roadmap budget because Chaplin is a validator, not a production model - tightening is a Phase 2 concern).
- [ ] With Ollama stopped, the pipeline still pastes - cleanup silently falls back per TICKET-008.
- [ ] With the camera deliberately occluded, no text is pasted and the log line explains why.
- [ ] `reports/silent_dictate_<date>.jsonl` accumulates one JSON object per processed utterance with the full `latencies` dict.
- [ ] Unit test passes with all hardware deps mocked out.
- [ ] Latency summary appended to `reports/latency-log.md` for each smoke run.

## Out of scope

- Audio-visual fusion with ASR - explicitly a Phase 2 / TICKET-future item. This pipeline is VSR-only.
- TTS / virtual mic / meeting mode - Flow 2 of the roadmap, out of PoC.
- App-aware cleanup routing - the `CleanupContext.focused_app` field is passed through but unused in the PoC prompt.
- Streaming partial VSR hypotheses to the overlay - TICKET-013 can simulate from completed utterances; true streaming is a Phase 2 latency ticket.

## Notes

- Preserve the user's focus through the whole trigger window. The overlay (TICKET-013) must **not** steal focus, or Ctrl+V lands in the wrong place.
- Keep the webcam closed whenever the hotkey is idle so the webcam LED only turns on during active capture. Matches the "privacy-safe default" UX note in the roadmap.

## References

- Roadmap Flow 1 (project_roadmap.md lines 58-95) - full spec this pipeline implements, including the latency table and UX notes.
- Roadmap Phase 1 Week 2 (project_roadmap.md line 175) - "Dictation + silent speech both functional. Full internal demo." This ticket is the silent half.
- Roadmap risks, latency budget (project_roadmap.md lines 222-223) - explains why we log every stage from day one.
