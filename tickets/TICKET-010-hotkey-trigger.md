# TICKET-010 - Hotkey / trigger layer

Phase: 1 - ML PoC
Epic: Injection
Estimate: S
Depends on: TICKET-002
Status: Not started

## Goal

Provide a global hotkey layer the pipelines subscribe to, supporting both **push-to-talk** (record while held) and **toggle** (press to start, press to stop) modes. The hotkey is what enforces the roadmap's "only record when I want to, privacy-safe default" UX. Downstream pipelines (TICKET-011/012) never touch the `keyboard` library directly.

## System dependencies

- Windows 10/11.
- The `keyboard` Python package uses a global Windows hook - Administrator privileges are not required on Windows (unlike Linux) but some corporate security tools can block the hook. Documented in `docs/hotkey.md`.

## Python packages

Already in TICKET-002:

- `keyboard`
- `pydantic`

No new additions.

## Work

- Create `src/sabi/input/hotkey.py`.
- Define `HotkeyConfig`:
  - `mode`: `"push_to_talk"` or `"toggle"`.
  - `binding`: default `"ctrl+alt+space"` - chosen because it is unlikely to collide with Slack, VS Code, or Windows defaults.
  - `min_hold_ms`: 80 - shorter presses in push-to-talk mode are treated as accidental taps and ignored.
  - `cooldown_ms`: 150 - minimum gap between successful triggers to prevent double-firing.
- Implement a `TriggerBus` event emitter with two events: `on_start` and `on_stop`. Callbacks receive a `TriggerEvent(trigger_id, mode, started_at_ns, reason="hotkey" | "cli")`.
- Implement `HotkeyController`:
  - Registers `keyboard.on_press_key` / `keyboard.on_release_key` for the binding in push-to-talk mode.
  - Registers `keyboard.add_hotkey` with a counter for toggle mode (press starts, next press stops).
  - Dispatches through `TriggerBus` on a dedicated thread to avoid blocking the keyboard hook.
  - Enforces `min_hold_ms` (push-to-talk) and `cooldown_ms` (both modes) before firing `on_start`.
  - Clean `start()` / `stop()` lifecycle tied to a context manager so the CLI can always unhook.
- Provide a CLI-only trigger path so the eval harness (TICKET-014) can drive the pipeline without a physical keypress. `TriggerBus.fire_start_cli()` / `fire_stop_cli()` synthesize events that share the same downstream contract.
- `scripts/hotkey_debug.py` prints `"[TRIGGER START]"` and `"[TRIGGER STOP]"` timestamps as you press/hold/release the hotkey - handy manual check.
- CLI shortcut: `python -m sabi hotkey-debug`.
- `tests/test_hotkey.py` with the `keyboard` library's internal hook functions monkeypatched to inject synthetic press/release events and verify: push-to-talk gating (min_hold_ms drops taps), toggle state machine (odd presses start, even presses stop), cooldown enforcement, dispatcher thread shutdown on context exit.

## Acceptance criteria

- [ ] `python -m sabi hotkey-debug` prints `[TRIGGER START]` on Ctrl+Alt+Space press and `[TRIGGER STOP]` on release (push-to-talk mode). Toggle mode (via `--mode toggle`) fires start on press #1, stop on press #2.
- [ ] Holding the hotkey for 50 ms does not fire `on_start` (under `min_hold_ms`).
- [ ] Two successful presses within `cooldown_ms` only produce one trigger.
- [ ] CLI-driven triggers and real key triggers both emit `TriggerEvent` with the same fields; only `reason` differs.
- [ ] Cleaning up (context exit) removes the hook - pressing Ctrl+Alt+Space after exit does not print anything.
- [ ] Unit tests pass with the monkeypatched `keyboard` layer; tests do not require the real hook.

## Out of scope

- Voice wake-word - listed as an option in the roadmap input layer but deferred; the PoC uses hotkey only.
- Per-app auto-mode-switch ("mode switcher" in the roadmap orchestration layer) - TICKET-013 owns the UI for mode state, this ticket just emits the raw trigger.
- System tray icon / global indicator - not needed for PoC.
- Non-Windows platforms.

## Notes

- `keyboard`'s hook is process-global and must be stopped explicitly; a dangling hook survives the Python process on crash only in rare cases but worth handling gracefully via `atexit`.
- Some chat apps register Ctrl+Alt+Space themselves (rare). Expose the binding in `configs/hotkey.toml` so reassignment does not require a code change.

## References

- Roadmap input layer (project_roadmap.md line 16) - "Hotkey / wake trigger - push-to-talk, toggle, or voice wake, user's choice".
- Roadmap Flow 1 step 1 (project_roadmap.md line 82) - "User triggers silent mode (hotkey, toggle, or auto) - instant".
- Roadmap Flow 1 UX notes (project_roadmap.md line 92) - "Hotkey trigger = 'only record when I want to,' privacy-safe default".
