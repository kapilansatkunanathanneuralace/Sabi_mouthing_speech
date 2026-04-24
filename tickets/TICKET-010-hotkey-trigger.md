# TICKET-010 - Hotkey / trigger layer

Phase: 1 - ML PoC
Epic: Injection
Estimate: S
Depends on: TICKET-002
Status: Done

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

- [x] `python -m sabi hotkey-debug` prints `[TRIGGER START]` on Ctrl+Alt+Space press and `[TRIGGER STOP]` on release (push-to-talk mode). Toggle mode (via `--mode toggle`) fires start on press #1, stop on press #2. *(CLI wired in `src/sabi/cli.py` calling `sabi.input.run_hotkey_debug`. `test_ptt_emits_start_after_min_hold_and_stop_on_release` and `test_toggle_alternating_presses_start_then_stop` cover the behavior with a faked `keyboard` module; live verification is a human step on a machine with the Windows hook available.)*
- [x] Holding the hotkey for 50 ms does not fire `on_start` (under `min_hold_ms`). *(`test_ptt_short_tap_does_not_fire_start` with `min_hold_ms=200` and a 50 ms hold asserts no events are emitted.)*
- [x] Two successful presses within `cooldown_ms` only produce one trigger. *(`test_ptt_cooldown_suppresses_second_start` with `cooldown_ms=1000` fires the chord twice and asserts only a single start/stop pair.)*
- [x] CLI-driven triggers and real key triggers both emit `TriggerEvent` with the same fields; only `reason` differs. *(`TriggerBus.fire_start_cli` / `fire_stop_cli` return events with `reason="cli"`; `test_fire_cli_events_share_contract` asserts the payload matches the hotkey-origin events field-for-field apart from `reason`.)*
- [x] Cleaning up (context exit) removes the hook - pressing Ctrl+Alt+Space after exit does not print anything. *(`HotkeyController.stop()` calls the remover returned by every `on_press_key` / `on_release_key` / `add_hotkey` registration and joins the bus worker; `test_stop_removes_hooks_and_joins_worker` verifies the callback lists are empty after `stop()`. An `atexit` weakref fallback runs the same cleanup if the context manager is bypassed.)*
- [x] Unit tests pass with the monkeypatched `keyboard` layer; tests do not require the real hook. *(11 tests in `tests/test_hotkey.py`; the full suite now runs 94 tests with no real Windows hook interaction.)*

## Implementation notes

- New files: `configs/hotkey.toml`, `src/sabi/input/__init__.py`, `src/sabi/input/hotkey.py`, `scripts/hotkey_debug.py`, `tests/test_hotkey.py`, `docs/hotkey.md`.
- Edited files: `src/sabi/cli.py` (`hotkey-debug` command), `docs/INSTALL.md` (brief cross-link).
- The bundled `keyboard` package cannot attach two `add_hotkey` callbacks to the same chord string (the second registration overwrites the first, upstream TODO). Push-to-talk is therefore implemented with `on_press_key` + `on_release_key` on the trigger key plus `on_release_key` on each modifier, using `keyboard.is_pressed(binding)` as the authoritative chord check. Toggle mode uses a single `add_hotkey` call since it does not need paired press / release hooks.
- `TriggerBus` is a thread-safe queue with a dedicated daemon worker thread; subscriber callbacks always run on the bus worker, never on the Windows hook thread. Exceptions in a subscriber are logged and swallowed so one bad consumer cannot stall the bus.
- `HotkeyController.__init__` accepts a `keyboard_module` injection seam so the test suite can drive the controller with a `FakeKeyboard` stand-in and never import the real hook.
- Full suite: 94 passed (`pytest -q`), up from 83 after TICKET-009.

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
