# TICKET-049 - Windows installer package

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: L
Depends on: TICKET-043, TICKET-044, TICKET-045, TICKET-046
Status: Partial

## Goal

Produce a signed `.exe` NSIS installer for Windows x64 via electron-builder that bundles the Electron app, the PyInstaller sidecar tree, icons, and license. Installation is per-user (no admin required), uninstall is clean, and running the installed app on a clean Windows 11 VM successfully reaches the onboarding wizard.

## System dependencies

- Windows 10/11 build host (or self-hosted runner) for native NSIS targets.
- Code-signing certificate (EV preferred; standard OV acceptable for early channels).
- Optional: VB-Cable installer redistributed under its license terms.

## Python packages

None.

## Work

- `desktop/build/electron-builder.yml` (Windows section):
  - `appId: com.sabi.desktop`.
  - `productName: "Sabi"`.
  - Targets: `nsis` (x64).
  - `extraResources`: bundle `packaging/sidecar/dist/sabi-sidecar/` -> `resources/sabi-sidecar/`.
  - File associations: none for v1.
  - Icons: `desktop/build/icons/icon.ico`.
- NSIS configuration:
  - Per-user install (`oneClick: false`, `perMachine: false`).
  - Custom finish page with "Launch Sabi" checkbox.
  - Uninstaller removes app dir and `userData`/cache only when user opts in (default off).
- Optional VB-Cable bundle:
  - If license permits redistribution, add `packaging/installers/vbcable/` and a "VB-Cable installer" button in the finish page; otherwise link to `docs/INSTALL-VBCABLE.md`.
  - Default v1 is "link out", not bundle.
- Code signing:
  - Read cert via env vars (`WIN_CSC_LINK`, `WIN_CSC_KEY_PASSWORD`) or Azure Trusted Signing options under `win.azureSignOptions`.
  - Document EV vs OV trade-offs in `docs/distribution_packaging/SIGNING_WINDOWS.md`.
  - SmartScreen reputation: note that fresh OV certs warn for weeks; EV avoids that.
- Build pipeline:
  - `npm run package:win` runs electron-builder for Windows targets only.
  - Output written to `desktop/dist/`.
  - `.gitignore` for `desktop/dist/`.
- Sanity tests on a clean Windows VM:
  - Install -> launch -> onboarding wizard reaches "Camera" step.
  - Uninstall -> no leftover files in `Program Files` or `LocalAppData\Sabi` (unless user opted to keep cache).
  - Sidecar binary launches under SmartScreen, signature verified.

## Acceptance criteria

- [ ] `npm run package:win` produces a signed `Sabi-<version>-setup.exe` in `desktop/dist/`.
- [ ] Installer runs end-to-end on a clean Windows 11 VM without admin elevation.
- [ ] Installed app launches and reaches the onboarding wizard.
- [x] Sidecar binary inside `resources/sabi-sidecar/` runs from the installed location and answers `meta.version`.
- [ ] Uninstall is clean by default and only removes user data when the user explicitly opts in.
- [x] `docs/distribution_packaging/SIGNING_WINDOWS.md` documents cert choice, env vars, and CI plan.
- [x] Installer file size below 250 MB (excluding model weights, which download on first launch per TICKET-048).

## Implementation notes

- Added Windows electron-builder NSIS config at `desktop/build/electron-builder.yml`.
- Added `npm run package:win` and `npm run validate:win-package`.
- Added Windows icon assets and signing/installer docs.
- Added a pruned release sidecar build under `packaging/sidecar/release-dist/`.
- Local self-signed packaging now produces `desktop/dist/Sabi-0.0.1-setup.exe` at approximately 174 MB.
- `npm run validate:win-package` verifies the generated package, packaged sidecar `meta.version`, and local Authenticode signature when `WIN_EXPECT_SIGNED=1`.
- Remaining blockers: a production OV/EV or Azure Trusted Signing certificate is still required for public release, and clean Windows 11 VM install/uninstall validation has not been run.

## Out of scope

- macOS DMG packaging (TICKET-050).
- Auto-update wiring (TICKET-051).
- Linux installer formats (TICKET-054).
- App Store distribution.

## Notes

- Per-user install avoids UAC prompts and matches user expectations for a tray app.
- Bundling VB-Cable is legally fine but operationally messy (driver install reboot); default to a link-out flow.
- SmartScreen warnings disappear faster on EV certs; budget for that if the product timeline matters.

## References

- `project_roadmap.md` lines 257-270 - electron-builder + signing baseline.
- TICKET-043 - sidecar binary that ships inside `resources/`.
- `docs/INSTALL-VBCABLE.md` (existing or planned) - link-out target.
