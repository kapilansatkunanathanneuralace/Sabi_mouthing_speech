# TICKET-041 - Packaging architecture ADR

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: S
Depends on: -
Status: Done

## Goal

Lock the packaging direction for turning the current Python CLI PoC into an installable desktop app. Write an Architecture Decision Record (ADR) that pins the stack to **Electron + React UI + PyInstaller Python sidecar**, defines the module boundary between the three pieces, and declares Windows and macOS as first-class targets with Linux deferred. Output is a single committed doc that all later distribution_packaging tickets reference, plus a stub `desktop/` folder layout proposal so subsequent tickets do not re-debate location/naming.

## System dependencies

- None at this stage; this ticket is doc-only.

## Python packages

None.

## Work

- Add `docs/adr/ADR-001-desktop-packaging.md` covering:
  - Context: today the only entry point is `sabi` / `python -m sabi` driven by `src/sabi/cli.py`; product wants a clickable installer.
  - Decision: Electron main process + React (Vite) renderer + Python sidecar built with PyInstaller, communicating over JSON-RPC on stdio.
  - Rejected alternatives: Tauri (Rust learning curve), pure native (two codebases), pure web/PWA (cannot inject text or own a virtual mic), pure PyInstaller-only Tk/PyQt app (drops the roadmap UX plan).
  - Cross-platform stance: Windows + macOS supported in the same Electron build config; Linux researched separately under `TICKET-054`.
  - Single source of truth for resource paths: introduce a "resource root" abstraction (folder selection at runtime) so dev (`repo/`) and frozen (`AppData`/`Application Support`) layouts both resolve `third_party/chaplin`, `configs/`, model cache, and reports.
  - CLI compatibility promise: the existing Typer commands stay working as developer/debug tools; the desktop UI talks to the sidecar API, not the CLI.
- Add `docs/distribution_packaging/README.md` index pointing at this ADR + the new ticket folder so onboarding finds it.
- Propose target folder layout (no code yet):
  - `desktop/electron/` (main + preload)
  - `desktop/renderer/` (Vite + React)
  - `desktop/build/` (electron-builder config + icons)
  - `packaging/sidecar/` (PyInstaller spec + hooks)
  - `packaging/installers/` (extra installer assets, e.g. VB-Cable / BlackHole bundles in later tickets).
- Update `tickets/README.md` "Out of scope" list so it no longer says Electron / sidecar / signing are deferred (point at this new ticket track instead).

## Acceptance criteria

- [x] `docs/adr/ADR-001-desktop-packaging.md` exists, is reviewed, and explicitly names: Electron, React (Vite), PyInstaller, JSON-RPC over stdio, Windows + macOS first.
- [x] ADR documents at least three rejected alternatives with reasons (Tauri, native, PWA).
- [x] ADR captures the "resource root" abstraction requirement and lists the current REPO_ROOT-relative call sites (e.g. `src/sabi/models/vsr/_chaplin_path.py`, `src/sabi/input/hotkey.py`) that must move behind it.
- [x] `tickets/README.md` "Out of scope" wording is updated to reference the distribution_packaging track instead of declaring packaging deferred.
- [x] `docs/distribution_packaging/README.md` indexes ADR-001 and the new ticket folder.

## Out of scope

- Writing any Electron / React / PyInstaller code (later tickets).
- Choosing a code-signing vendor (TICKET-049 / TICKET-050).
- Designing the React UI (TICKET-044, TICKET-047).
- Linux packaging implementation (TICKET-054).

## Notes

- This ADR is the contract every later packaging ticket reads first; treat it as load-bearing.
- The roadmap already favors Electron + React + Python sidecar (`project_roadmap.md` lines 225-310); this ADR codifies that for the repo.

## References

- `project_roadmap.md` lines 225-310 - "Packaging & Distribution - Simple Path (Electron + React)".
- `tickets/README.md` lines 26-34 - current "Out of scope" packaging stance, to be updated.
- `src/sabi/cli.py` - existing Typer surface that the sidecar will wrap.
