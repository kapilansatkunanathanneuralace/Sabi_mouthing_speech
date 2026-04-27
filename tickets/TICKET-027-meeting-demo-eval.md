# TICKET-027 - Meeting demo runbook + listening-test eval

Phase: 1 - ML PoC
Epic: Eval
Estimate: M
Depends on: TICKET-015, TICKET-025, TICKET-026
Status: Not started

## Goal

Ship `docs/DEMO-MEETING.md` so a reviewer can reproduce PoC-4 (silent meeting into Zoom) cold on a fresh Windows machine, and extend `sabi.eval.harness` with a meeting-mode track that measures **end-to-end latency** (mouth stop -> first sample written to the virtual mic) and a **listening-test eval** that captures synthesized audio plus ground-truth text for human MOS-style scoring. This is how we know if meeting mode is actually usable, not just wired.

## System dependencies

- Everything from TICKET-015 + VB-Cable + a real Zoom (or Teams / Meet) test call - the demo itself requires a second participant to hear the synthesized voice, otherwise we are only testing "audio reaches the virtual mic", not "remote participant hears it clearly".
- Optional: a second account or a test meeting room. Document both options.

## Python packages

Already listed for the eval extras (TICKET-014):

- `jiwer`, `pandas`, `tabulate`.

New, eval-only:

- `librosa==0.10.2` - loads captured wavs, computes RMS, spectrogram summaries, optional PESQ-like sanity checks. Installed under the `eval` extras group.

## Work

- Write `docs/DEMO-MEETING.md`:
  1. **Overview.** Link to `project_roadmap.md` Flow 2 lines 97-144 and `docs/DEMO.md` for shared prerequisites.
  2. **Additional prerequisites.** VB-Cable installed + verified via probe; Kokoro weights cached; Ollama running (optional); a Zoom/Teams/Meet account; a second participant or a personal test meeting.
  3. **Cold-start meeting setup.** PowerShell block adding on top of `docs/DEMO.md`: confirm `python -m sabi probe` shows `CABLE Input / CABLE Output` PASS; run `python -m sabi tts-smoke "hello"`; run `python -m sabi vmic-smoke` and verify audio was captured from `CABLE Output`.
  4. **Meeting client config.** Screenshots-with-placeholders for Zoom / Teams / Meet showing how to set microphone to `CABLE Output` and speaker to the normal hardware output. Include the "Automatically adjust microphone volume" checkbox note (turn it off - it muddies the signal).
  5. **Live demo steps.** Start `python -m sabi silent-meeting`; TUI should show `mode=meeting`, `sink=CABLE Input`, `MUTED`. Hit `Ctrl+Alt+M` to unmute. Hold the trigger hotkey, mouth a phrase from the Harvard sentence list. Release. Verify the other participant hears the synthesized voice; measure the participant's perceived latency against the TUI's reported `end_to_end_ms`.
  6. **Mute toggle drill.** Press `Ctrl+Alt+M` mid-sentence; verify trailing audio cuts within one audio block.
  7. **Eval runbook.** `python -m sabi eval --pipelines silent_meeting --capture` runs the new eval track, described below.
  8. **Known failure modes.** Seed entries:
     - Zoom's noise-cancellation eating Kokoro's softer consonants -> mitigation "set Zoom > Audio > Background Noise Suppression to Low".
     - VB-Cable sample-rate mismatch -> crackle; mitigation "set both ends to 48 kHz in Windows Sound Control Panel".
     - Kokoro first-utterance JIT stall after a long idle period -> mitigation "keep `warm_up_on_init` true and issue a dummy synth every N minutes - follow-up ticket".
     - Confidence floor too strict -> "no audio at all" in real demos; document the F12 force-push behavior prominently.
     - Long utterances truncating against `max_output_seconds` in TICKET-020.
- Extend `sabi.eval.harness`:
  - Add a `SilentMeetingOfflineRunner(video_path, capture_dir) -> UtteranceProcessed`:
    - Feeds frames through the same pipeline path as TICKET-025 with capture replaced by a sequence-backed fake and the sink replaced by a `CapturingSink` that writes incoming samples to `<capture_dir>/<phrase_id>.wav` instead of the VB-Cable device.
    - Reuses the real `TTSEngine` so synthesis quality and latency are representative.
  - End-to-end latency measurement: `end_to_end_ms` is `trigger_stop_ns` -> first sample appended to the captured wav. Added to the report as a new column.
  - Listening-test output: writes `reports/meeting-eval-<date>/<phrase_id>.wav` (git-ignored) plus a `reports/meeting-eval-<date>/scorecard.csv` with columns: `phrase_id`, `ground_truth_text`, `cleaned_text`, `end_to_end_ms`, `tts_ttfb_ms`, `capture_duration_ms`, `human_mos` (blank, filled in by a human listener).
  - Harness summary section rendered in the main markdown report: per-phrase table + p50/p95 `end_to_end_ms` and `tts_ttfb_ms` across all runs, plus a stub "MOS (human)" column that is populated later.
- Write `scripts/meeting_live_latency.py`: optional real-mic-loopback measurement that plays a clap/marker through the user's real mic while the pipeline is running, so we can verify the end-to-end real latency against the offline eval numbers. Kept as a manual tool, not wired into CI.
- Extend `tests/test_eval_harness.py` with meeting-track cases using a stub TTS yielding deterministic fake audio and a `CapturingSink` backed by a numpy buffer. Assert: `end_to_end_ms` computed correctly, captured wav has expected sample count, scorecard.csv has the right columns.
- Cross-link `docs/DEMO-MEETING.md` from `tickets/README.md`, `README.md`, and `docs/DEMO.md` ("For meeting mode, see DEMO-MEETING.md").

## Acceptance criteria

- [ ] A developer reproducing from `docs/DEMO.md` + `docs/DEMO-MEETING.md` on a fresh machine can get PoC-4 working in a test Zoom meeting within 90 minutes (installer downloads + model pulls included).
- [ ] `python -m sabi eval --pipelines silent_meeting --capture --dataset data/eval/sample` produces a markdown report with a meeting-track section + a folder of captured wavs + a scorecard CSV.
- [ ] The scorecard CSV columns match the listening-test protocol documented in `docs/DEMO-MEETING.md`; a human listener can fill in `human_mos` without modifying the file structure.
- [ ] Captured wavs are mono, at the sink's configured sample rate, and decodable by `librosa.load` without error.
- [ ] `scripts/meeting_live_latency.py` produces a measurement file under `reports/` when run against a known loopback.
- [ ] The "Known failure modes" section contains the five seeded entries and has space for field additions.
- [ ] Links from `tickets/README.md` and top-level `README.md` to `docs/DEMO-MEETING.md` resolve.
- [ ] Meeting demo runbook recorder `scripts/record_demo.ps1` (from TICKET-015) accepts a `-Meeting` flag that additionally records the output side of `CABLE Input` alongside the screen capture, so demo artifacts include the participant's view and the synthesized audio stream.

## Out of scope

- Automated human scoring - MOS requires a human ear; we capture the data to score, we do not score automatically. A cheap MOS-proxy metric can be a follow-up ticket.
- PESQ / STOI implementation - optional and pay-per-reference; the listening test is good enough for PoC.
- Two-way latency (round-trip including Zoom's network) - impossible to measure without a controlled second endpoint; we stop at end-of-pipeline.
- Multi-language meeting eval - English only for PoC.
- Sharing captured audio externally - stays in `reports/` which is git-ignored by default.

## Notes

- Capture directly from the in-process sink via `CapturingSink`, not via recording `CABLE Output` - recording the device adds the Windows audio stack's own latency and jitter to the measurement and obscures what the pipeline is actually doing.
- Keep the scorecard CSV dead simple so a non-engineer listener can score it in a spreadsheet.

## References

- Roadmap Flow 2 latency budget (project_roadmap.md lines 124-136) - "Total: mouth stop -> others hear your voice 400-500 ms" is the number this eval exists to measure.
- Roadmap Phase 1 Week 3 (project_roadmap.md line 176) - "First real meeting using synthesized voice" is the demo this runbook lets us stage.
- Roadmap risks (project_roadmap.md lines 218-225) - each seeded failure mode maps to a listed risk (accuracy, latency, privacy, cross-platform, model drift).
