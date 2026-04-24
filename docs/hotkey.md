# Hotkey trigger (TICKET-010)

`sabi.input.hotkey.HotkeyController` is the single layer the pipelines
(TICKET-011 / TICKET-012) subscribe to for "start recording" / "stop
recording" events. Downstream code never imports the `keyboard`
package directly; it calls `controller.bus.subscribe_start(...)` /
`subscribe_stop(...)` and gets a `TriggerEvent` on a dedicated worker
thread.

## Modes

- **push_to_talk** (default): `on_start` fires once the chord has been
  held for `min_hold_ms`. `on_stop` fires the moment any part of the
  chord is released. Shorter presses are treated as accidental taps
  and produce no events.
- **toggle**: alternating presses flip `on_start` / `on_stop`. A
  second press within `min_hold_ms` is treated as a keyboard debounce
  and ignored.

Both modes enforce `cooldown_ms` on successful `on_start` events so a
bouncing key or an over-eager CLI harness cannot double-fire.

## Binding format

The `binding` string is passed straight through to the `keyboard`
package, so anything the upstream parser accepts works:

- `ctrl+alt+space` (default - picked to avoid collisions with Slack,
  VS Code, and Windows).
- `ctrl+shift+f12`, `f9`, `ctrl+alt+d`, etc.

Edit [`configs/hotkey.toml`](../configs/hotkey.toml) to change the
default without touching code.

## Windows caveats

- The `keyboard` package installs a **process-global Windows hook**.
  Administrator is not required on Windows (unlike Linux), but some
  corporate antivirus / EDR tools block global hooks outright. If
  `sabi hotkey-debug` silently never fires, start with a simple
  binding (`f9`) and verify the tool is not blocked.
- The hook must be released explicitly on shutdown.
  `HotkeyController.stop()` removes the specific hooks it registered,
  and `HotkeyController` also registers an `atexit` fallback via a
  weak reference so an un-finalized controller still cleans up on
  interpreter exit.
- `keyboard.add_hotkey` cannot attach two callbacks to the same chord
  string (the second registration overwrites the first; see the
  upstream TODO in `.venv/.../keyboard/__init__.py`). Push-to-talk
  therefore uses `on_press_key` / `on_release_key` on the trigger key
  plus release hooks on the modifier keys, with `keyboard.is_pressed`
  as the authoritative chord check.

## CLI debug

```powershell
python -m sabi hotkey-debug
python -m sabi hotkey-debug --mode toggle
python -m sabi hotkey-debug --binding "ctrl+shift+f12" --min-hold-ms 50
```

Press / hold / release the chord and watch `[TRIGGER START]` /
`[TRIGGER STOP]` lines. Ctrl+C to exit; the controller unhooks on the
way out.

`scripts/hotkey_debug.py` is an equivalent entry point that works
without the `sabi` console script installed:

```powershell
python scripts/hotkey_debug.py --mode push_to_talk
```

## Programmatic API

```python
from sabi.input import HotkeyConfig, HotkeyController

with HotkeyController(HotkeyConfig()) as controller:
    controller.bus.subscribe_start(lambda e: print("start", e))
    controller.bus.subscribe_stop(lambda e: print("stop", e))
    # Eval harness / tests: drive the same bus without a physical key.
    start = controller.bus.fire_start_cli("push_to_talk")
    controller.bus.fire_stop_cli("push_to_talk", start)
```

`TriggerEvent` carries `trigger_id`, `mode`, `started_at_ns`, and
`reason` (`"hotkey"` or `"cli"`). `on_stop` events share the matching
`on_start` event's `trigger_id` and `started_at_ns` so downstream code
can compute hold duration without keeping its own bookkeeping.
