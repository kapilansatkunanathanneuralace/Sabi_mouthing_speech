# TICKET-028 - Meeting mute / unmute instant toggle

Phase: 1 - ML PoC
Epic: Orchestration
Estimate: S
Depends on: TICKET-023, TICKET-027
Status: Not started

## Goal

Wire a global hotkey that toggles the virtual mic sink mute bit in under 1 ms, without touching the TTS engine or VSR pipeline. Dropping buffered audio on mute prevents stale syllables from leaking after unmute.

## System dependencies

None new.

## Python packages

None new.

## Work

- Create `src/sabi/orchestration/meeting_mute.py`.
- Define `MeetingMuteConfig`.
- Implement `MeetingMuteController` with `mute()`, `unmute()`, and hotkey registration.
- Extend the TUI to render a `MUTED` indicator during meeting mode.
- Add `python -m sabi mute-debug`.
- Add `tests/test_meeting_mute.py`.

## Acceptance criteria

- [ ] `Ctrl+Alt+M` toggles virtual mic mute while `python -m sabi silent-meeting` is running.
- [ ] Muting mid-sentence stops output within one audio block.
- [ ] Unmute does not leak old buffered audio.
- [ ] Mute works regardless of privacy switch state.
- [ ] `python -m sabi mute-debug` reports < 1 ms median synthetic toggle latency.
- [ ] Startup state is muted by default.

## Out of scope

- Audible confirmation.
- Integration with meeting-client mute APIs.
- Auto-mute on repeated low confidence.
- Hold-to-speak semantics beyond the normal trigger hotkey.

## Notes

- Do not log or allocate on the hotkey path.
- Pair mute state with visible TUI status.

## References

- Roadmap Flow 2 UX note (project_roadmap.md line 140).
- Roadmap orchestration layer (project_roadmap.md lines 47-52).
