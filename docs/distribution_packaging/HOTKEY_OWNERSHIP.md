# Hotkey Ownership

Packaged desktop builds use Electron as the owner of global shortcuts.

The Python `keyboard` hook remains a CLI/development fallback for commands such as
`python -m sabi silent-dictate`, but Electron-spawned sidecars set
`SABI_SIDECAR_NO_HOTKEY=1` so Python does not register a second global hook.

## Current Desktop Behavior

- Default Windows/Linux accelerator: `Control+Alt+Space`.
- Default macOS accelerator: `CommandOrControl+Alt+Space`.
- Configurable pipeline: `silent`, `audio`, or `fused`.
- Configurable mode: `toggle` or `push_to_talk`.

Electron's built-in `globalShortcut` API fires when the accelerator activates, but
it does not provide a global key-release event. For TICKET-046, `push_to_talk` uses
the same repeated-press start/stop behavior as toggle mode. True hold-to-record and
release-to-stop needs a native keyup layer or a later onboarding/permissions pass.

## Why Electron Owns Packaged Shortcuts

- The desktop shell already owns tray state, settings, and app lifecycle.
- The renderer can stay isolated from Node APIs.
- The Python sidecar can focus on pipelines and JSON-RPC without double-triggering
  the same shortcut.
- macOS Accessibility permission handling belongs to desktop onboarding, not Python.

## CLI Behavior

Existing CLI commands continue to load `configs/hotkey.toml` and use the Python
hotkey implementation unless `SABI_SIDECAR_NO_HOTKEY=1` is explicitly set by the
caller.
