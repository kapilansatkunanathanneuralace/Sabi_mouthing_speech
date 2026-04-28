# TICKET-052 - Packaging CI matrix

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-043, TICKET-049, TICKET-050
Status: Not started

## Goal

Run packaging end-to-end in CI on Windows and macOS. Every push to `main` produces unsigned internal artifacts; tagged releases produce signed + notarized installers. The matrix encodes the OS-specific quirks (signing creds, notarization, sidecar build) so packaging stops being "works on my machine".

## System dependencies

- GitHub Actions (or equivalent) with hosted runners for Windows and macOS.
- Apple notarization credentials and a Developer ID cert (provisioned as repo secrets).
- Windows code-signing cert (cloud HSM, Azure Trusted Signing, or EV USB token via self-hosted runner).

## Python packages

None.

## Work

- `.github/workflows/desktop-build.yml`:
  - Triggers: `push` (main), `pull_request`, `workflow_dispatch`, `release` (published).
  - Matrix:
    - `os: [windows-latest, macos-13, macos-14]`.
  - Steps per OS:
    - Checkout with submodules (Chaplin).
    - Setup Python 3.11 + cache pip.
    - Setup Node 20 + cache npm.
    - Install Python deps (`pip install -e ".[dev,packaging]"`).
    - Build sidecar (`python scripts/build_sidecar.py`).
    - Build desktop (`cd desktop && npm ci && npm run package:<os>`).
    - Upload artifacts.
- Signing/notarization:
  - macOS: env vars `APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER`, `CSC_LINK`, `CSC_KEY_PASSWORD`.
  - Windows: `WIN_CSC_LINK`, `WIN_CSC_KEY_PASSWORD` for cloud cert; or Azure Trusted Signing env vars on a self-hosted runner.
  - PR builds skip signing.
- Cache strategy:
  - pip + npm caches keyed on lockfiles.
  - PyInstaller `build/` cache keyed on `pyproject.toml` + `sabi_sidecar.spec` hash.
- Artifact retention:
  - PR/main builds: 7-day retention, internal only.
  - Tagged releases: upload to GitHub Releases (and later S3/R2) via electron-builder publish.
- Documentation:
  - `docs/distribution_packaging/CI.md` lists secrets, runner requirements, and the local-equivalent commands.
- Smoke check after build:
  - On the same runner, run the `--version` of each installer where possible (NSIS uninstaller / `hdiutil` mount on macOS) to catch trivially broken artifacts.

## Acceptance criteria

- [ ] CI builds the sidecar + Electron app on Windows and macOS for every PR (unsigned).
- [ ] Tag pushes produce signed + notarized installers and zip files attached to a GitHub release draft.
- [ ] Build time per OS is below 25 minutes on hosted runners with the cache strategy in place.
- [ ] `docs/distribution_packaging/CI.md` exists and lists secrets, runner OS requirements, and local-equivalent commands.
- [ ] CI failures on signing/notarization surface clearly (named step, structured error).
- [ ] No secrets are printed to logs.

## Out of scope

- Linux build matrix (TICKET-054).
- App-store submissions.
- Performance benchmarks in CI (PoC-level packaging only).

## Notes

- Windows EV signing on hosted runners is painful (USB tokens); plan on Azure Trusted Signing or a self-hosted runner from the start.
- Apple notarization can be slow (5-15 minutes); keep the timeout generous.
- Cache misses on PyInstaller cost 5+ minutes; key the cache carefully.

## References

- TICKET-049 / TICKET-050 - the artifacts CI builds.
- `project_roadmap.md` line 305 - "Code signing setup (Mac + Windows), notarization in CI".
