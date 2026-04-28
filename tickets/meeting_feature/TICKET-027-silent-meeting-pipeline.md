# TICKET-027 - Silent-meeting pipeline (PoC-4)

Phase: 1 - ML PoC
Epic: Pipeline
Estimate: L
Depends on: TICKET-005, TICKET-023, TICKET-024, TICKET-026
Status: Not started

## Goal

Wire webcam capture, lip ROI, Chaplin VSR, meeting-register cleanup, Kokoro TTS, virtual mic sink, and the orchestrator into a silent-meeting pipeline. Users mouth words at the camera; Zoom / Teams / Meet, with mic set to `CABLE Output`, hears synthesized speech.

## System dependencies

Webcam, CUDA strongly recommended, Ollama optional, VB-Cable installed, Kokoro weights cached locally.

## Python packages

No new dependencies.

## Work

- Create `src/sabi/pipelines/silent_meeting.py`.
- Define `SilentMeetingConfig`.
- Implement `SilentMeetingPipeline`:
  - Registers with orchestrator mode `"meeting"`.
  - Opens capture only during trigger windows.
  - Runs VSR, meeting cleanup, TTS, and virtual mic playback.
  - Aborts low-confidence utterances by default with a force override.
  - Emits status events and structured JSONL logs.
- Add `python -m sabi silent-meeting` with `--dry-run`.
- Add `tests/test_silent_meeting.py` with all hardware mocked.

## Acceptance criteria

- [ ] `python -m sabi silent-meeting` registers meeting mode and idles until triggered.
- [ ] Mouthing a short phrase during a test meeting produces synthesized speech audible to another participant.
- [ ] Missing VB-Cable fails at startup with remediation from TICKET-021.
- [ ] Ollama-off path bypasses cleanup and still synthesizes raw text.
- [ ] Low confidence stays silent by default; force override synthesizes.
- [ ] `reports/silent_meeting_<date>.jsonl` records latencies.
- [ ] Latency rows append to `reports/latency-log.md`.
- [ ] Unit tests pass with hardware mocked.

## Out of scope

- Voice cloning.
- Two-way turn-taking / barge-in.
- Echo cancellation.
- Lip-sync to the user's actual meeting camera.
- Auto-mode-switch inside the pipeline.
- Audio-visual fusion in the meeting flow.

## Notes

- Keep `VirtualMicSink` open for the pipeline lifetime.
- Drain TTS streams fully so future synth calls do not block.

## References

- Roadmap Flow 2 (project_roadmap.md lines 97-144).
- Roadmap Phase 1 Week 3 (project_roadmap.md line 176).
- Roadmap Flow 2 UX notes (project_roadmap.md lines 138-144).
