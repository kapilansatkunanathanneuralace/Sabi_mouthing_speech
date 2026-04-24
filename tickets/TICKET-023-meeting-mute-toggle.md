# TICKET-023 - Meeting mute / unmute instant toggle

Phase: 1 - ML PoC
Epic: Orchestration
Estimate: S
Depends on: TICKET-018, TICKET-022
Status: Not started

## Goal

Wire a global hotkey (default `Ctrl+Alt+M`) that toggles the virtual mic sink mute bit in under 1 ms, without touching the TTS engine or the VSR pipeline. Honors the roadmap's "Mute/unmute toggle must be instant - never block the meeting mic behind the pipeline" UX note. Also drops any buffered audio on mute so a user slamming mute while Kokoro is still speaking a sentence does not get a stale trailing syllable on unmute.

## System dependencies

None new.

## Python packages

None new.

## Work

- Create `src/sabi/orchestration/meeting_mute.py`.
- Define `MeetingMuteConfig` (binding default `Ctrl+Alt+M`, start_state `"muted"` (safer default - user unmutes explicitly once the pipeline is warm), drop_buffer_on_mute True, audible_confirmation False (no click/beep by default)).
- Implement `MeetingMuteController`:
  - Registers the hotkey via `HotkeyController` (TICKET-010) using its toggle semantics - does **not** drive the orchestrator's mode machine, since muting and mode-switching are independent.
  - Owns a reference to the live `VirtualMicSink` (injected by TICKET-022 on pipeline start).
  - `.mute()`: calls `sink.mute(True)` and, if `drop_buffer_on_mute`, also calls `sink.drop_queued()`. Sets an internal state flag and emits a `MeetingMuteEvent` for the TUI (TICKET-013) to render.
  - `.unmute()`: calls `sink.mute(False)`. Does not touch the queue - on unmute, the *next* TTS synthesis feeds in normally.
  - The mute hotkey path is constant-time and allocation-free - it can reach the sink bit flip in under 1 ms.
- Ensure the mute hotkey works even when the orchestrator's privacy switch (TICKET-021) is on. They are separate concerns - privacy blocks all capture, while mute blocks meeting output specifically.
- Extend TICKET-013's TUI to render a `MUTED` indicator in the header when the meeting pipeline is active and the sink is muted. Color consistently with the privacy switch indicator.
- `scripts/mute_debug.py` runs the hotkey + a fake sink (in-memory buffer) and prints elapsed time from keypress to mute-bit flipped. Useful for verifying the 1 ms SLA.
- CLI shortcut: `python -m sabi mute-debug`.
- `tests/test_meeting_mute.py`:
  - Asserts `mute()` calls `sink.mute(True)` and `drop_queued()`.
  - Asserts `unmute()` flips only the bit, not the queue.
  - Asserts the time between synthetic key event and sink flag flip is under 1 ms on CI hardware (use a tight loop + fake sink; no real keyboard).
  - Asserts the privacy switch does not gate the mute hotkey.

## Acceptance criteria

- [ ] `Ctrl+Alt+M` toggles the virtual mic mute state while `python -m sabi silent-meeting` is running. TUI indicator updates immediately.
- [ ] Pressing mute while TTS is mid-sentence causes Zoom's "Are you talking? You're muted." style visualizations (or simply silent output) to stop within one audio block (~20 ms) of the keypress.
- [ ] On unmute, a subsequent mouthed utterance is audible without any leaked buffered audio from the previous utterance (tested manually during `silent-meeting` smoke runs, and in unit tests via the fake sink's captured samples).
- [ ] Mute can be toggled regardless of the orchestrator's privacy switch state.
- [ ] `scripts/mute_debug.py` reports < 1 ms median latency between a synthesized press event and sink flag flip on CI hardware.
- [ ] The default startup state is muted so the user explicitly unmutes once the pipeline is warm and they are ready to "speak".

## Out of scope

- Visible audible confirmation (beep/click) - `audible_confirmation` knob exists but the PoC ships with it off.
- Integration with Zoom / Teams / Meet mute API to also toggle the *meeting client's* mute state - unnecessary because the user typically wants their real mic and the virtual mic muted in opposite states, not together.
- Auto-mute when the pipeline's confidence is low across N consecutive utterances - potentially a later polish ticket, not PoC.
- "Hold to speak" in meeting mode - that behavior is already available via the normal trigger hotkey.

## Notes

- The 1 ms budget is realistic on modern Windows with a cold `keyboard`-library hook; do not do anything else on the hot path (no logging, no JSON, no pub/sub cascades). The event for the TUI is posted to the TUI's queue from a worker, not from the hotkey hook itself.
- Pair the mute hotkey with a visible TUI state, not an audible cue - beeps into Zoom will be heard by meeting participants as clicks.

## References

- Roadmap Flow 2 UX note (project_roadmap.md line 140) - "Mute/unmute toggle must be instant - never block the meeting mic behind the pipeline" is the literal requirement this ticket satisfies.
- Roadmap orchestration layer (project_roadmap.md lines 47-52) - positions mute alongside mode switcher and privacy switch.
