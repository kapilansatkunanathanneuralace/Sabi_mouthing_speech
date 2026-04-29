# Sabi Desktop

This is the Electron + Vite + React shell for the installable Sabi desktop app.
Electron owns the Python sidecar process, talks to it with JSON-RPC over stdio, and
exposes a narrow `window.sabi` bridge to the renderer.

## Prerequisites

- Node.js 20 LTS.
- npm 10 or newer.

The package `engines` field pins the release target to Node 20. Newer local Node
versions may install with an engine warning, but release and CI should use Node 20.

## Scripts

```powershell
npm install
npm run dev
npm run typecheck
npm run lint
npm run test
npm run build
npm run preview
npm run package
npm run package:win
npm run validate:win-package
```

- `dev` starts Vite and then opens Electron against the dev server.
- `typecheck` checks both Electron and renderer TypeScript projects.
- `lint` runs ESLint over the desktop workspace.
- `test` runs mocked sidecar lifecycle and JSON-RPC unit tests.
- `build` compiles Electron main/preload code and the production renderer bundle.
- `preview` serves the built renderer bundle for UI inspection.
- `package` runs an unpacked electron-builder package smoke.
- `package:win` builds the Windows NSIS target from `build/electron-builder.yml`.
- `validate:win-package` checks Windows package output and sidecar placement.

## Windows Installer

Build the PyInstaller sidecar first, then run the Windows package command:

```powershell
cd ..
python scripts\build_sidecar_release.py
cd desktop
npm run package:win
npm run validate:win-package
```

The package config copies `packaging/sidecar/release-dist/sabi-sidecar/` into
Electron resources as `resources/sidecar/sabi-sidecar/`. Local unsigned builds are
allowed for smoke testing when signing env vars are absent; release builds must sign
the installer as described in `docs/distribution_packaging/SIGNING_WINDOWS.md`.
The full packaging architecture is documented in
`docs/distribution_packaging/ELECTRON_DISTRIBUTION_ARCHITECTURE.md`.

Current local validation produces a self-signed `Sabi-0.0.1-setup.exe` of about
174 MB, validates packaged sidecar `meta.version`, and launches the unpacked app in a
bounded smoke test. Production signing and clean Windows VM install/uninstall
validation are still required before TICKET-049 can be marked done.

## Layout

```text
desktop/
  electron/
    main.ts       # BrowserWindow lifecycle
    preload.ts    # typed window.sabi bridge
    sidecar/      # process, JSON-RPC, path resolution, health checks
  renderer/
    index.html
    src/
      App.tsx     # sidecar status and probe panel
      main.tsx
      styles.css
```

## Sidecar Behavior

In development, Electron prefers a built local sidecar at
`../packaging/sidecar/dist/sabi-sidecar/sabi-sidecar.exe` when it exists. Otherwise
it falls back to `python -m sabi sidecar` from the repository root. You can force a
specific binary with:

```powershell
$env:SABI_DESKTOP_SIDECAR_BIN = "..\packaging\sidecar\dist\sabi-sidecar\sabi-sidecar.exe"
npm run dev
```

In production, Electron resolves the bundled sidecar from `process.resourcesPath`.
TICKET-049 and TICKET-050 own the exact installer layout.

The renderer can request `meta.version`, `probe.run`, and other JSON-RPC methods via
`window.sabi.sidecar.call()`. It cannot access Node APIs directly.

## Tray, Windows, And Shortcuts

Sabi now runs as a resident tray app. Closing the settings window hides it; use the
tray menu's `Quit` action to exit the app. The tray menu can open settings, open
logs, and start/stop the configured dictation pipeline.

The settings window persists a JSON settings file under Electron's user data
directory. It controls shortcut mode, accelerator, pipeline, paste behavior, and the
overlay stub. The overlay window is frameless, transparent, always-on-top, and
click-through; real transcript overlay UX is still future work.

Electron owns packaged-app global shortcuts. See
[`../docs/distribution_packaging/HOTKEY_OWNERSHIP.md`](../docs/distribution_packaging/HOTKEY_OWNERSHIP.md).
The current Electron-only implementation uses repeated shortcut presses for
`push_to_talk` start/stop because Electron `globalShortcut` does not emit key-release
events.

## First Launch Onboarding

Fresh settings show a guided first-launch wizard before the main dashboard. The
wizard resumes from the last saved step if the user quits midway. It verifies camera
and microphone access with `probe.run`, checks platform permissions through Electron
helpers, downloads VSR and ASR model assets with `cache.download`, and surfaces
progress notifications from the Python sidecar.

On completion, the settings file records `onboardingCompleted: true` and returns the
user to the main dashboard. Optional Ollama and virtual mic setup can be skipped;
dictation still works with existing graceful fallback behavior.

## Model Asset Cache

The Python sidecar owns model downloads and hash verification through `cache.status`,
`cache.verify`, `cache.download`, and `cache.clear`. Cached assets live outside the
installer:

- Windows: `%LOCALAPPDATA%\Sabi\models`
- macOS: `~/Library/Application Support/Sabi/models`
- Linux future path: `$XDG_DATA_HOME/sabi/models`

The settings dashboard shows each manifest's status, size, Verify, Re-download,
Clear, and Open folder controls. `models.download_vsr` remains as a compatibility
sidecar method for older callers.

## Logs

Sidecar stderr is written through `electron-log` under the Electron user data logs
folder. Use the app menu item or the renderer `Open log folder` button to open it.

## Current Boundary

This desktop track now wires lifecycle, health, logging, `probe.run`, tray behavior,
global shortcuts, onboarding, and model-cache management. Installer polish remains in
later tickets.
