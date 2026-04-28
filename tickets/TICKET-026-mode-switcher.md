# TICKET-026 - Mode switcher / orchestrator

Phase: 1 - ML PoC
Epic: Orchestration
Estimate: M
Depends on: TICKET-010, TICKET-025
Status: Not started

## Goal

Introduce a central `Orchestrator` that owns user-facing mode state and decides which pipeline handles a hotkey trigger. It merges hotkey state, foreground app state, and a privacy switch so dictation and meeting flows are not wired as separate one-off CLIs forever.

## System dependencies

None new.

## Python packages

None new.

## Work

- Create `src/sabi/orchestration/modes.py`.
- Define states: `off`, `dictation`, `silent_dictation`, `fused_dictation`, and `meeting`.
- Define `UtteranceRequest`.
- Implement `Orchestrator` with state transitions, privacy switch, optional auto-switch, and pipeline subscription.
- Add `python -m sabi orchestrator`.
- Add `tests/test_orchestrator.py`.

## Acceptance criteria

- [ ] `python -m sabi orchestrator --start-mode silent_dictation` runs the silent dictation path.
- [ ] `--start-mode fused_dictation` dispatches utterances to the fused pipeline.
- [ ] Auto-switch to meeting mode only happens when enabled.
- [ ] Privacy switch blocks capture and utterance dispatch.
- [ ] Only the active pipeline receives `UtteranceRequest`.
- [ ] Unit tests pass with peripherals stubbed.

## Out of scope

- Granular per-app rules beyond meeting-app auto-switch.
- Voice-wake trigger.
- Calendar-aware pre-warm.
- Multi-user profile switching.

## Notes

- The orchestrator is the only place that knows which pipelines exist.
- Fused dictation should be included as a first-class mode now that TICKET-017 exists.

## References

- Roadmap orchestration layer (project_roadmap.md lines 47-52).
- Roadmap privacy risk (project_roadmap.md line 223).
- Roadmap Flow 2 UX note (project_roadmap.md line 142).
