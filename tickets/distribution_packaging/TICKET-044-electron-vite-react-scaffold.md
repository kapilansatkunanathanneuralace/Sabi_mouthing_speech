# TICKET-044 - Electron + Vite + React scaffold

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-041
Status: Done

## Goal

Stand up the Electron + Vite + React app skeleton in `desktop/` so future packaging tickets can start adding real features instead of bootstrapping. Output is a clickable empty-shell app that opens a window with the renderer, has a working preload bridge, builds in dev and production, and does not yet talk to the sidecar (that lands in TICKET-045).

## System dependencies

- Node.js 20 LTS on Windows and macOS dev machines.
- npm 10+ (or pnpm 9+, but pick one and standardize).

## Python packages

None.

## Work

- Initialize `desktop/package.json`:
  - `name: "sabi-desktop"`, `version: "0.0.1"`, private.
  - Scripts: `dev`, `build`, `preview`, `package` (electron-builder, real config lands in TICKET-049/050), `lint`, `typecheck`.
  - Engines field pinning Node 20.
- Renderer (`desktop/renderer/`):
  - Vite + React 18 + TypeScript template.
  - Minimal landing screen showing app version + a "Status: not connected" pill.
  - ESLint + Prettier config matching the existing repo style as closely as possible (line-length 100 to mirror Python tooling).
- Main process (`desktop/electron/main.ts`):
  - Creates a single `BrowserWindow` (1024x720, hidden until ready-to-show).
  - Loads Vite dev URL in dev, file:// build in production.
  - Quits on window close on Windows/Linux, stays alive on macOS (standard pattern).
- Preload (`desktop/electron/preload.ts`):
  - Exposes a typed `window.sabi` namespace with placeholder `version()` returning a constant for now.
  - Uses `contextBridge` and `contextIsolation: true`, `nodeIntegration: false`.
- TypeScript config split: `tsconfig.base.json`, `tsconfig.electron.json`, `tsconfig.renderer.json`.
- Add `desktop/README.md` describing dev workflow, folder layout, and "this scaffold does nothing yet".
- Update top-level `README.md`:
  - New "Desktop app (alpha)" section pointing at `desktop/README.md`.
  - Note that the Python CLI remains the dev path.

## Acceptance criteria

- [x] `cd desktop && npm install && npm run dev` starts Vite and Electron on Windows. macOS validation requires a macOS host.
- [x] `npm run build` produces a production renderer bundle and a compiled main + preload bundle.
- [x] `window.sabi.version()` returns the Electron app version through the preload bridge.
- [x] ESLint + TypeScript checks pass with zero errors.
- [x] `desktop/README.md` documents the dev/build/package scripts.
- [x] No Python sidecar integration yet (intentional; TICKET-045 owns that).

## Out of scope

- Real IPC to Python (TICKET-045).
- Tray icon, hotkeys, onboarding (TICKET-046, TICKET-047).
- Code signing or installer config (TICKET-049, TICKET-050).
- Auto-update wiring (TICKET-051).

## Notes

- Keep `nodeIntegration: false` from the start - retrofitting context isolation later is painful.
- Pin Electron and electron-builder versions in `desktop/package.json`; floating versions break CI.
- Treat `desktop/` as a sibling workspace; do not entangle it with the Python build.

## References

- `project_roadmap.md` lines 251-256 - dev workflow summary.
- ADR-001 from TICKET-041 - architecture binding.
