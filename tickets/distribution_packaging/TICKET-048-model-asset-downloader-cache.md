# TICKET-048 - Model asset downloader and cache manager

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-042, TICKET-047
Status: Done

## Goal

Move first-launch model setup out of "user runs a CLI" and into a managed app cache. Models live outside the installer (so installers stay small and signable) but inside an app-controlled directory so we can version, hash-verify, garbage collect, and re-download without admin rights. Reuses `configs/vsr_weights.toml` as the manifest source of truth.

## System dependencies

- Disk space: VSR + ASR + cleanup assets together can exceed ~3 GB.
- Network access on first launch (offline-first installs are deferred).

## Python packages

None new. Reuses the existing download script behavior at `src/sabi/models/vsr/download.py`.

## Work

- Promote `src/sabi/models/vsr/download.py` to a generic `src/sabi/runtime/asset_cache.py`:
  - `AssetManifest` Pydantic model: list of `{name, url, sha256, relative_path, kind}`.
  - `AssetCache(app_home)` with `ensure(manifest_name)`, `verify(manifest_name)`, `clear(manifest_name)`, `path_of(name)`.
  - Streams progress to the sidecar (already wired in TICKET-042).
- Define manifests under `configs/manifests/`:
  - `vsr.toml` (copy of `vsr_weights.toml`).
  - `asr.toml` for faster-whisper checkpoints (initially CPU-only `small` INT8).
  - `cleanup.toml` documenting Ollama model name (does not host a download URL; the cleanup model still installs via Ollama).
- App home selection:
  - Windows: `%LOCALAPPDATA%\Sabi\models`.
  - macOS: `~/Library/Application Support/Sabi/models`.
  - Linux (future): `$XDG_DATA_HOME/sabi/models`.
- Cache UX:
  - Settings panel in the renderer: per-manifest status (present/missing/corrupt), "Verify", "Re-download", "Open folder".
  - Disk usage shown per manifest.
- Sidecar wiring:
  - New methods `cache.status`, `cache.verify`, `cache.download`, `cache.clear` mirroring the manifest set.
- Migration:
  - On first run, if `data/models/vsr/` exists from dev usage, offer to symlink/move it to the new app cache instead of re-downloading.
- Tests:
  - Manifest validation, hash mismatch handling, partial-download resume (best effort), clear/verify round-trip.

## Acceptance criteria

- [x] First launch in a clean profile downloads VSR + ASR assets into the platform-correct app home and verifies SHA-256 against the manifest.
- [x] Repeat launches do not re-download; `cache.status` returns `present`.
- [x] Tampering with a cached file (truncate / overwrite) makes `cache.verify` return `corrupt`, and the UI offers a one-click re-download.
- [x] Renderer cache panel shows status, size, and "Open folder" for each manifest.
- [x] Sidecar `cache.*` methods are covered by tests using a fake transport.
- [x] `configs/vsr_weights.toml` continues to work for the existing CLI flow (no regressions).

## Implementation notes

- Added `sabi.runtime.asset_cache.AssetCache` and `configs/manifests/`.
- Added `cache.status`, `cache.verify`, `cache.download`, and `cache.clear`.
- Kept `models.download_vsr` as a compatibility wrapper over the VSR cache manifest.
- Windows path behavior was validated locally; macOS path behavior should be validated on a macOS host.

## Out of scope

- Bundling Ollama itself - we still rely on the user installing it externally.
- Differential / patch updates of model assets (whole-file replacement is fine for the PoC).
- Telemetry of cache size or download failures.

## Notes

- Keeping models out of the installer is the single biggest factor in fast, signable releases.
- Always hash-verify before declaring `present`; partial downloads are common on flaky networks.
- macOS Gatekeeper is not happy with executable bits inside `Application Support`; only weights and configs go here.

## References

- `src/sabi/models/vsr/download.py` - origin of the cache code.
- `configs/vsr_weights.toml` - existing manifest format.
- TICKET-047 - onboarding step that consumes this cache.
