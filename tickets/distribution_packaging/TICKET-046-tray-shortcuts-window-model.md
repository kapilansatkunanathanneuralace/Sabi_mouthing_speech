# TICKET-046 - Tray app, global shortcuts, and window model

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-044, TICKET-045
Status: Done

## Goal

Give the Electron app the OS-resident behaviors a real desktop tool needs: a tray icon, a settings window, an overlay window stub, app lifecycle that does not quit on window close (Windows + macOS), and global shortcuts for push-to-talk / toggle that match the current Python defaults. Decide explicitly that **Electron owns global shortcuts** and the Python sidecar's `keyboard`-based hooks are dev-only fallbacks; this avoids double triggers when both layers run.

## System dependencies

- macOS Accessibility permission for global shortcuts (handled in onboarding, TICKET-047).
- Windows: nothing extra at install time; UAC-free.

## Python packages

None.

## Work

- Tray (`desktop/electron/tray.ts`):
  - 16x16/32x32 icons under `desktop/build/icons/`.
  - Menu: app status, "Start dictation", "Stop dictation", "Open settings", "Quit".
  - Status reflects sidecar connection from TICKET-045.
- Window model:
  - Settings window (existing main window from TICKET-044, repurposed): hidden by default; opened from tray.
  - Overlay window stub: frameless, transparent, always-on-top, click-through, hidden until enabled by a setting. Real overlay UX lands in a follow-up ticket.
- Global shortcuts (`desktop/electron/shortcuts.ts`):
  - Default chord: `Ctrl+Alt+Space` (Windows) / `Cmd+Alt+Space` (macOS), matching `configs/hotkey.toml` semantics.
  - Push-to-talk and toggle modes - read mode from a settings store.
  - Calls `dictation.silent.start` / `.stop` (or `dictation.fused.*` per setting) on the sidecar via TICKET-045.
- Settings store (`desktop/electron/settings.ts`):
  - JSON file under `app.getPath('userData')`.
  - Schema: `mode`, `hotkey`, `pipeline`, `pasteOnAccept`, `overlayEnabled`.
  - Validated with zod; corrupt files are quarantined and replaced with defaults.
- Hotkey ownership:
  - Document in `docs/distribution_packaging/HOTKEY_OWNERSHIP.md` that Electron owns shortcuts in the packaged app.
  - The Python sidecar must default to "no global hotkey" when started by Electron (env flag `SABI_SIDECAR_NO_HOTKEY=1`).
  - Existing CLI behavior unchanged.
- Tests:
  - Settings store: round-trip + corruption + migration unit tests.
  - Shortcut wiring: mocked Electron, verify start/stop calls land on the RPC client.

## Acceptance criteria

- [x] Tray icon appears on Windows with menu actions and live status text. macOS tray validation requires a macOS host.
- [x] Closing the settings window keeps the app running; quitting from the tray menu actually exits.
- [x] `Ctrl+Alt+Space` (Win) / `Cmd+Alt+Space` (mac) triggers the configured pipeline through the sidecar. With Electron `globalShortcut` only, PTT uses repeated shortcut presses for start/stop; release-to-stop is documented as a follow-up limitation.
- [x] Settings window can switch mode (PTT vs toggle) and pipeline (silent/audio/fused) and persist across restarts.
- [x] Sidecar started by Electron honors `SABI_SIDECAR_NO_HOTKEY=1` and does not register its own keyboard hook.
- [x] `docs/distribution_packaging/HOTKEY_OWNERSHIP.md` exists and is linked from `desktop/README.md`.
- [x] Settings unit tests pass.

## Out of scope

- Functional overlay UX (transcript, confidence) - future ticket.
- Permissions wizard (TICKET-047).
- Per-app rules / mode auto-switch (project roadmap Phase 2/3 work).

## Notes

- macOS will not deliver global shortcuts until Accessibility is granted; surface that clearly and route the user to onboarding.
- Always-on-top + click-through overlays are flag-sensitive; getting them wrong on Windows can swallow the user's clicks.
- Keep the chord configurable from day one; users will rebind it.

## References

- `src/sabi/input/hotkey.py` - existing Python hotkey behavior.
- `configs/hotkey.toml` - default chord.
- ADR-001 (TICKET-041) - architecture boundary that this ticket realizes.
