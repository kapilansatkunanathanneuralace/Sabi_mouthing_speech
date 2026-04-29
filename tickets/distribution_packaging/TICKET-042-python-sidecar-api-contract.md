# TICKET-042 - Python sidecar API contract

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-041
Status: Done

## Goal

Add a `sabi sidecar` daemon mode that exposes the existing pipeline functionality through a stable JSON-RPC over stdio interface. The desktop app must never need to spawn `sabi silent-dictate` and parse its stdout; it talks to a long-running Python process whose protocol is versioned and documented. CLI behavior in `src/sabi/cli.py` stays unchanged so developers keep their current workflow.

## System dependencies

- None new; reuses the existing pipelines (`silent_dictate`, `audio_dictate`, `fused_dictate`), `probe`, and model download flows.

## Python packages

- No new runtime deps. Use stdlib `json`, `asyncio`, and the existing typer/pydantic stack.
- Optional dev: `pytest-asyncio>=0.23` for testing the dispatcher under `[project.optional-dependencies] dev`.

## Work

- Add `src/sabi/sidecar/` package:
  - `protocol.py` - request/response/event Pydantic schemas, version constant `SIDECAR_PROTOCOL_VERSION = "1.0.0"`.
  - `dispatcher.py` - registers handlers, dispatches JSON-RPC 2.0 method calls, and emits `notification` events for streaming updates (status, partial transcript, errors).
  - `server.py` - reads framed JSON from stdin, writes framed JSON to stdout, logs to stderr only.
  - `handlers/` - one module per surface area: `probe`, `models`, `dictation`, `fused`, `eval`, `meta`.
- Wire methods (initial set):
  - `meta.version` - protocol + app version.
  - `meta.shutdown` - graceful drain.
  - `probe.run` - structured probe results (camera, mic, torch, mediapipe, ollama).
  - `models.download_vsr` - streams progress notifications.
  - `dictation.silent.start` / `.stop` / `.status` - wraps `SilentDictatePipeline` with `--dry-run` honored.
  - `dictation.audio.start` / `.stop` / `.status` - wraps `AudioDictatePipeline`.
  - `dictation.fused.start` / `.stop` / `.status` - wraps `FusedDictatePipeline`.
  - `eval.run` - thin wrapper around the eval harness for QA tools.
- Add `python -m sabi sidecar` Typer command that starts the server. No interactive output, no prompts.
- Resource-root abstraction (introduced under TICKET-041) is consumed here:
  - Add `src/sabi/runtime/paths.py` with `app_home()`, `models_dir()`, `configs_dir()`, `reports_dir()`, `chaplin_dir()`.
  - Refactor `src/sabi/models/vsr/_chaplin_path.py` and `src/sabi/input/hotkey.py` to read from `runtime.paths` (no behavior change in dev).
- Tests: `tests/test_sidecar_protocol.py`, `tests/test_sidecar_dispatcher.py` covering version handshake, unknown-method error, streaming notifications, and shutdown.

## Acceptance criteria

- [x] `python -m sabi sidecar` starts and responds to `{"jsonrpc":"2.0","id":1,"method":"meta.version"}` with the protocol version + app version on stdout.
- [x] Unknown methods return JSON-RPC error code `-32601` (Method not found) without crashing the process.
- [x] `models.download_vsr` streams at least one progress notification before completing and reuses the existing `configs/vsr_weights.toml` manifest.
- [x] Each `dictation.*` method honors a `dry_run` flag and reuses the existing pipeline classes.
- [x] `src/sabi/runtime/paths.py` is the only place that resolves repo-root-style paths; the two refactor sites compile against the new helper.
- [x] All sidecar tests pass without touching real hardware (use the existing `_Deps` injection seams).
- [x] Existing CLI commands (`silent-dictate`, `dictate`, `fused-dictate`, `probe`, etc.) keep working unchanged.

## Out of scope

- Bundling the sidecar with PyInstaller (TICKET-043).
- Spawning the sidecar from Electron (TICKET-045).
- Adding meeting-mode methods (those land alongside TICKET-027 once meeting work resumes).

## Notes

- Stick to JSON-RPC 2.0 framing rather than inventing a bespoke protocol; Electron has multiple battle-tested clients.
- Notifications are the hot path for UI: keep them small and frequent rather than waiting for a final result.
- Treat the protocol version as an API: bump on breaking changes, not on additive ones.

## References

- `src/sabi/cli.py` - subcommands the sidecar wraps.
- `src/sabi/pipelines/silent_dictate.py`, `audio_dictate.py`, `fused_dictate.py` - underlying pipelines.
- `project_roadmap.md` line 235 - "Python sidecar (PyInstaller) ... communicates over stdin/stdout JSON-RPC or a local WebSocket".
