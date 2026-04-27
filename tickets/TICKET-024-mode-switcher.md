# TICKET-024 - Mode switcher / orchestrator

Phase: 1 - ML PoC
Epic: Orchestration
Estimate: M
Depends on: TICKET-010, TICKET-023
Status: Not started

## Goal

Introduce a single central `Orchestrator` that owns the user-facing mode state (`off`, `dictation`, `meeting`, `silent_dictation`) and decides which pipeline handles a hotkey trigger. Merges the hotkey signal from TICKET-010 with the focus signal from TICKET-023 plus a privacy switch. Replaces the ad-hoc per-pipeline hotkey wiring that TICKET-011 / TICKET-012 stood up directly - those pipelines now subscribe to `Orchestrator.on_utterance_request` instead of subscribing to `HotkeyController` themselves.

## System dependencies

None new.

## Python packages

None new.

## Work

- Create `src/sabi/orchestration/modes.py`.
- Define the state machine:
  - States: `off`, `dictation` (audio), `silent_dictation` (VSR), `meeting` (silent meeting flow).
  - Transitions:
    - CLI entrypoint selects the initial mode; `python -m sabi orchestrator --start-mode silent_dictation` boots in the matching state.
    - Hotkey `Ctrl+Alt+M` toggles `meeting` <-> previous mode (used by TICKET-026 for mute).
    - `Ctrl+Alt+.` cycles through modes (configurable).
    - Auto-switch: when the foreground classifier reports `zoom`/`teams`/`meet` and the current mode is a dictation mode, the orchestrator proposes a switch to `meeting`. Auto-switch is **off by default** and opt-in via `configs/orchestrator.toml` - the roadmap privacy principle is "off by default, push-to-talk" (project_roadmap.md line 223).
  - Privacy switch: hard key (default `Ctrl+Alt+P`) flips camera + mic off instantly. While the privacy switch is on, the orchestrator ignores hotkey triggers and the pipelines know to not open hardware. Camera/mic stay off until explicitly turned back on, even across auto-switches.
- Define `UtteranceRequest`: `trigger_event` (from TICKET-010), `mode`, `focus_snapshot` (latest FocusEvent or None), `privacy_on` bool.
- Implement `Orchestrator`:
  - Constructs / owns `HotkeyController` and `ForegroundWatcher`.
  - Maintains the state machine; exposes `.current_mode`.
  - `.on_utterance_request(callback)`: pipelines subscribe; only the pipeline matching the current mode receives the request.
  - Logs every transition with a reason (`"cli"`, `"hotkey"`, `"auto-switch"`, `"privacy"`). TICKET-013 surfaces this in the TUI.
- Refactor references:
  - TICKET-011 and TICKET-012's pipelines no longer subscribe to `HotkeyController` directly; they subscribe to `Orchestrator.on_utterance_request` filtered by mode. Update the existing tickets' notes section to cross-reference this ticket so the change is obvious to whoever picks up the refactor. The refactor itself is tracked under this ticket, not re-opening 011/012.
  - TICKET-025 builds on this directly.
- CLI: `python -m sabi orchestrator` runs the full system with all installed pipelines registered, defaulting to `silent_dictation`. `--mode`, `--start-muted`, `--auto-switch` flags.
- `tests/test_orchestrator.py` exercises the state machine with stub hotkey and stub focus sources:
  - CLI-driven mode transitions.
  - Hotkey-driven transitions and cooldown.
  - Auto-switch fires only when `auto_switch=True`.
  - Privacy switch blocks utterance dispatches.
  - Only the currently-registered pipeline receives requests.

## Acceptance criteria

- [ ] `python -m sabi orchestrator --start-mode silent_dictation` runs the silent-dictation pipeline; opening Zoom does not switch modes unless `--auto-switch` is set.
- [ ] With `--auto-switch`, focusing Zoom transitions the orchestrator to `meeting`; exiting Zoom back to a text editor proposes transitioning back - configurable whether the return is automatic or requires confirmation.
- [ ] `Ctrl+Alt+P` flips the privacy switch; subsequent hotkey presses do nothing; the TUI reflects the privacy state.
- [ ] Only the pipeline matching the current mode receives the `UtteranceRequest`; others are inert until the mode is active.
- [ ] State transitions are logged with the reason field populated correctly.
- [ ] Unit tests pass with all peripherals stubbed.

## Out of scope

- Granular per-app rules beyond the Zoom/Teams/Meet auto-switch (e.g., Slack tone overrides) - noted in `CleanupContext.focused_app` for future tickets but not implemented here.
- Voice-wake trigger - input layer upgrade path; not PoC.
- Scheduling / calendar awareness ("you have a meeting in 5 min, pre-warm the meeting pipeline") - cute, out of PoC.
- Multi-user / profile switching - single-user PoC.
- Treating the new fused-dictation pipeline (TICKET-017) as a fourth mode - TICKET-017 ships its own CLI and operates outside the orchestrator state machine for v1; lifting fused-dictation into the orchestrator (e.g. as a `fused_dictation` mode that auto-fuses when both modalities are present) is a follow-up once the orchestrator and fused pipeline are both in.

## Notes

- Keep the orchestrator allocation-free on the hot path. Under load (fast hotkey mashing) state transitions should not allocate per call - use cached event objects where reasonable.
- The orchestrator is the only place that knows which pipelines exist. This keeps TICKET-011/012/017/025 from having to know about each other.

## References

- Roadmap orchestration layer (project_roadmap.md lines 47-52) - "Mode switcher: Dictation / Meeting / Silent / Always-on ... Privacy switch ... Per-app rules" is the full spec this ticket implements.
- Roadmap risk, privacy perception (project_roadmap.md line 223) - "Camera + mic always-on is a non-starter ... Lead with 'off by default, push-to-talk' framing." Privacy switch defaults follow this.
- Roadmap Flow 2 UX note (project_roadmap.md line 142) - the Zoom/Teams/Meet auto-switch is the direct feature.
