# TICKET-050 - macOS DMG package

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: L
Depends on: TICKET-043, TICKET-044, TICKET-045, TICKET-046
Status: Not started

## Goal

Produce a signed and notarized `.dmg` (and matching `.zip` for auto-update) for macOS via electron-builder, covering both Apple Silicon (`arm64`) and Intel (`x64`) builds. A clean macOS install must reach the onboarding wizard, request the right permissions in the right order, and pass Gatekeeper without warnings.

## System dependencies

- A macOS 13+ build host (real Mac or hosted runner; M-series strongly preferred).
- Apple Developer Program membership.
- Developer ID Application + Developer ID Installer certificates.
- App-specific password or App Store Connect API key for notarization.

## Python packages

None.

## Work

- `desktop/build/electron-builder.yml` (macOS section):
  - `mac.target`: `[ { target: dmg, arch: [arm64, x64] }, { target: zip, arch: [arm64, x64] } ]`.
  - `mac.category`: `public.app-category.productivity`.
  - `hardenedRuntime: true`.
  - `gatekeeperAssess: false`.
  - `entitlements: desktop/build/entitlements.mac.plist`.
  - `entitlementsInherit: desktop/build/entitlements.mac.plist`.
  - `extendInfo`: usage descriptions for `NSCameraUsageDescription`, `NSMicrophoneUsageDescription`, `NSAccessibilityUsageDescription`, `NSInputMonitoringUsageDescription`.
- Entitlements (`desktop/build/entitlements.mac.plist`):
  - `com.apple.security.cs.allow-jit` (Electron requirement).
  - `com.apple.security.cs.allow-unsigned-executable-memory` (Torch requirement; revisit if a stricter policy is feasible).
  - `com.apple.security.device.camera`, `com.apple.security.device.microphone`.
  - Disable App Sandbox - this is a non-MAS Developer ID build.
- Notarization:
  - `notarize: true` with `APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` env vars.
  - Document the alternative `APPLE_ID` + app-specific password path.
- Sidecar bundling:
  - `extraResources` ships `packaging/sidecar/dist/sabi-sidecar/` -> `Contents/Resources/sabi-sidecar/`.
  - `afterPack` hook ensures every native binary inside the sidecar tree is signed; unsigned `.dylib` files break notarization.
- Optional virtual audio:
  - Link out to `docs/INSTALL-BLACKHOLE.md` (new doc) explaining the BlackHole install. Bundling drivers in v1 is out of scope.
- Build pipeline:
  - `npm run package:mac` runs electron-builder for macOS targets only.
  - Output to `desktop/dist/`.
- Sanity tests on a clean macOS VM/host:
  - Mount DMG, drag to Applications, launch.
  - First launch triggers Camera + Microphone + Accessibility + Input Monitoring prompts in onboarding (TICKET-047).
  - `spctl --assess --verbose` reports `accepted`.
  - `codesign -dv --verbose=4` shows the Developer ID signature.
- `docs/distribution_packaging/SIGNING_MACOS.md`:
  - Cert + provisioning, notarization env vars, common failure modes (unsigned native modules, invalid bundle IDs, hardened runtime entitlements missing).

## Acceptance criteria

- [ ] `npm run package:mac` produces signed + notarized `Sabi-<version>-arm64.dmg`, `Sabi-<version>-x64.dmg`, and matching `.zip` files.
- [ ] `spctl --assess --type execute -v /Applications/Sabi.app` returns `accepted`.
- [ ] Installed app launches on a clean macOS 13+ machine and reaches the onboarding wizard with all permission prompts firing at the right step.
- [ ] Notarization passes in CI (or locally) without manual stapling steps.
- [ ] Sidecar binary inside `Contents/Resources/sabi-sidecar/` runs and answers `meta.version`.
- [ ] `docs/distribution_packaging/SIGNING_MACOS.md` documents the cert + notarization workflow.

## Out of scope

- Mac App Store submission (different cert chain, sandboxed; not pursued).
- Bundling BlackHole (license + driver-install complexity).
- Linux packaging (TICKET-054).
- Auto-update wiring (TICKET-051).

## Notes

- Apple Silicon vs Intel: build per-arch; do not ship a "universal2" sidecar unless it has been verified end-to-end (Torch wheels can break universal builds).
- Notarization stapling is automatic in electron-builder; manual `xcrun stapler` is only a debug fallback.
- The hardest failure is "notarization succeeded but Gatekeeper still warns" - usually an unsigned `.dylib` inside the Python sidecar tree.

## References

- `project_roadmap.md` line 260 - macOS signing baseline.
- TICKET-043 - sidecar tree that must be signed end-to-end.
- TICKET-047 - onboarding step that drives macOS permission prompts.
