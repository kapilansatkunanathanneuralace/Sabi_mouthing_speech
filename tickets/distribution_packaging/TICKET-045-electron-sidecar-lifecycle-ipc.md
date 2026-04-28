# TICKET-045 - Electron sidecar lifecycle + IPC bridge

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: L
Depends on: TICKET-042, TICKET-043, TICKET-044
Status: Done

## Goal

Spawn the Python sidecar from Electron, exchange JSON-RPC over its stdio, surface its lifecycle to the renderer, and recover from crashes. After this ticket the Electron shell can run `meta.version`, `probe.run`, and `dictation.silent.start --dry-run` against the sidecar and show results in the React UI - without using the CLI.

## System dependencies

- A built `sabi-sidecar` binary from TICKET-043, or the dev fallback `python -m sabi sidecar`.

## Python packages

None.

## Work

- `desktop/electron/sidecar/`:
  - `path.ts` - resolves the sidecar binary location: in dev, runs `python -m sabi sidecar` from the repo; in production, points at the bundled binary inside `process.resourcesPath`.
  - `process.ts` - `SidecarProcess` class wrapping `child_process.spawn`; manages stdin/stdout, stderr-to-log, restart-on-crash with backoff (3 attempts, then surface error).
  - `rpc.ts` - JSON-RPC 2.0 client: framed write, id-keyed pending requests, notification subscriber, timeout handling.
  - `health.ts` - calls `meta.version` periodically; emits "connected"/"disconnected" to the renderer.
- Renderer integration:
  - Add `useSidecar()` React hook that exposes connection state, version, and a typed `call(method, params)` function.
  - Replace the placeholder version pill from TICKET-044 with the live sidecar version.
  - Add a Probe panel that calls `probe.run` and renders the result.
- Lifecycle:
  - Sidecar starts on app boot, stops on quit, restarts on unexpected exit.
  - Renderer-initiated crash recovery: a banner with "Reconnect" button when health checks fail.
- Logging:
  - Pipe sidecar stderr to `electron-log` (or equivalent) under user data dir.
  - Add a developer "Open log folder" menu item for support workflows.
- Tests:
  - `desktop/electron/sidecar/__tests__/rpc.test.ts` covers framing, id matching, error mapping, and timeout.
  - Mock the child_process for `process.test.ts` (no real Python in CI).

## Acceptance criteria

- [x] On app launch, Electron spawns the sidecar and the renderer header shows the sidecar protocol + app version within 5 s.
- [x] Killing the sidecar process from outside causes the renderer to show "Disconnected", and the app auto-restarts the sidecar within 3 s.
- [x] The Probe panel calls `probe.run` and renders camera/mic/torch/mediapipe rows.
- [x] Renderer cannot directly access Node APIs (context isolation kept on).
- [x] All RPC unit tests pass without spawning a real sidecar.
- [x] Sidecar stderr ends up in a log file accessible from a menu item.

## Out of scope

- Tray icon and global shortcuts (TICKET-046).
- Onboarding (TICKET-047).
- Streaming partial transcripts to the UI - separate work, not blocking.

## Notes

- Always prefer JSON-RPC notifications for streaming progress (download bars, status pings); keep request/response for control plane.
- Backoff matters: a tight restart loop on a crashed sidecar can mask real bugs.
- Isolation matters: never `eval` strings from the sidecar in the renderer; always validate against the protocol schema.

## References

- TICKET-042 - protocol contract.
- TICKET-043 - frozen binary location.
- `project_roadmap.md` line 238 - "[Electron Main] <-> [Python Sidecar]".
