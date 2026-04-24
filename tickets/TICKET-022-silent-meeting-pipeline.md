# TICKET-022 - Silent-meeting pipeline (PoC-3)

Phase: 1 - ML PoC
Epic: Pipeline
Estimate: L
Depends on: TICKET-005, TICKET-018, TICKET-019, TICKET-021
Status: Not started

## Goal

Wire TICKET-003 (webcam) + TICKET-004 (lip ROI) + TICKET-005 (Chaplin VSR) + TICKET-019 (meeting-register cleanup) + TICKET-017 (Kokoro TTS) + TICKET-018 (virtual mic sink) into a silent-meeting pipeline driven by the orchestrator from TICKET-021. Exposes `python -m sabi silent-meeting`. Users mouth words at the camera; Zoom / Teams / Meet, with mic set to `CABLE Output`, hears a synthesized voice speaking those words - roadmap Flow 2 end-to-end.

## System dependencies

All inherited: webcam, CUDA (strongly recommended for TTS latency), Ollama (optional, degrades gracefully per TICKET-008), VB-Cable installed, RealtimeTTS + Kokoro weights cached locally.

## Python packages

No new dependencies; everything pinned already.

## Work

- Create `src/sabi/pipelines/silent_meeting.py`.
- Define `SilentMeetingConfig` composing `WebcamConfig`, `LipROIConfig`, `VSRModelConfig`, `CleanupConfig` (register forced to `"meeting"`), `TTSConfig`, `VirtualMicConfig`, and orchestrator references. Config file `configs/silent_meeting.toml`.
- Implement `SilentMeetingPipeline`:
  - On construction: registers with the orchestrator for mode `"meeting"` via `Orchestrator.on_utterance_request`. Warms up `VSRModel` and `TTSEngine`. Resolves the VB-Cable device via `sabi.output.virtual_mic.resolve_devices()` and opens a `VirtualMicSink` that stays open for the whole meeting (not per-utterance - reopening the sink per utterance adds perceptible latency and risks leaking a buffer gap into Zoom).
  - On `UtteranceRequest` (trigger start): opens the webcam, starts lip ROI worker, buffers frames. Webcam stays closed between utterances to respect the privacy-first UX.
  - On trigger stop: closes capture, runs `VSRModel.predict` on the buffered frames.
  - If confidence is below a configurable floor (default 0.4), **abort synthesis by default** - sending a bad utterance to a real meeting is worse than saying nothing. User can override per-utterance by holding F12 during the trigger window, same pattern as TICKET-011.
  - Feeds cleaned text into `TTSEngine.speak()` and pipes the resulting `TTSStream` to `VirtualMicSink.play_stream()`. The pipeline does not block on the stream finishing; it records the first-audio timestamp, then moves on, so the next trigger can start immediately.
  - Implements the roadmap's "push to mouth" UX policy: between utterances, the sink emits silence (the sink does that by default when the queue is empty; this pipeline only needs to not push frames it does not have).
- Stage-timing contract: `latencies = {"capture_ms": ..., "roi_ms": ..., "vsr_ms": ..., "cleanup_ms": ..., "tts_ttfb_ms": ..., "sink_handoff_ms": ..., "end_to_end_ms": ...}` where `end_to_end_ms` is trigger-stop to first audio frame written to the device. Matches the Flow 2 latency table in the roadmap.
- Structured log at `reports/silent_meeting_<date>.jsonl`.
- CLI: `python -m sabi silent-meeting` runs until Ctrl+C. `--dry-run` routes TTS audio to a local speaker instead of the virtual mic (useful when VB-Cable is not installed or Zoom is not running). `--force-cpu` for debugging on non-CUDA machines.
- Unit test `tests/test_silent_meeting.py` uses stub components (fake webcam -> canned lip frames -> stub VSR -> stub cleanup -> stub TTS yielding fake frames -> stub sink capturing frames in memory) and verifies:
  - End-to-end wiring produces frames at the sink in the correct order.
  - Low-confidence utterances suppress synthesis by default.
  - F12 override forces synthesis even below the confidence floor.
  - Latency plumbing covers every stage.
  - Webcam is not opened until a trigger starts; is released when the trigger ends.

## Acceptance criteria

- [ ] `python -m sabi silent-meeting` registers the meeting pipeline with the orchestrator and idles until triggered.
- [ ] Mouthing a short phrase during a Zoom call (with Zoom's mic set to `CABLE Output`) produces synthesized speech audible to the other participant. Target end-to-end latency < 650 ms on the reference GPU laptop (looser than the 400-500 ms roadmap budget because Chaplin is a validator; the per-stage log lets us see which stage is over budget).
- [ ] With VB-Cable missing, pipeline fails at startup with the remediation error from TICKET-016.
- [ ] With Ollama off, cleanup bypasses and raw Chaplin text is synthesized.
- [ ] With the face occluded, the utterance aborts quietly and nothing is synthesized.
- [ ] Low-confidence utterances stay silent by default; F12 during the trigger window forces synthesis.
- [ ] `reports/silent_meeting_<date>.jsonl` records one JSON object per attempted utterance with the full `latencies` dict.
- [ ] Latency rows appended to `reports/latency-log.md` with `ticket=TICKET-022` for every smoke run.
- [ ] Unit tests pass with all hardware mocked out.

## Out of scope

- TTS sounding like the user (voice cloning) - Phase 3 upgrade.
- Two-way turn-taking / barge-in - the PoC is one-way output.
- Echo / feedback cancellation - users can hear the synthesized voice via Zoom's "Test Speaker and Microphone" in preview; real meetings are fine because the speaker output is a different device from the CABLE Output input.
- Lip-sync to the user's actual face on camera - the user may leave their camera off in the meeting entirely; if they do not, sync is the meeting participants' problem to perceive, not ours to compensate.
- Auto-mode-switch inside the pipeline - handled centrally by TICKET-021.

## Notes

- Keep the `VirtualMicSink` open for the whole pipeline lifetime. Opening per utterance pays a ~100 ms driver warm-up each time - perceptible as a "pop" at the beginning of every sentence.
- `TTSStream` is single-consumer; the pipeline must drain it or the RealtimeTTS internal queue stays full and subsequent `speak()` calls block.

## References

- Roadmap Flow 2 (project_roadmap.md lines 97-144) - the full spec this pipeline implements, including the latency table.
- Roadmap Phase 1 Week 3 (project_roadmap.md line 176) - "Meeting mode shipped - TTS -> virtual mic routed to Zoom. First real meeting using synthesized voice." This ticket is the entire Week 3 milestone.
- Roadmap Flow 2 UX notes (project_roadmap.md lines 138-144) - "TTS streams", "Push to mouth mode for introverts: only synthesize while actively mouthing", "App detection" are the behaviors this pipeline composes.
