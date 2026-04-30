# TICKET-050 - macOS DMG package

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: L
Depends on: TICKET-043, TICKET-044, TICKET-045, TICKET-046
Status: Not started

## Goal

Produce a signed and notarized `.dmg` (and matching `.zip` for auto-update) for macOS via electron-builder, covering both Apple Silicon (`arm64`) and Intel (`x64`) builds. The package should mirror the current Windows bootstrap model: the app ships a slim onboarding/cache/runtime-install sidecar, while the full dictation runtime is downloaded and activated after install from a published runtime pack. A clean macOS install must reach the onboarding wizard, request the right permissions in the right order, and pass Gatekeeper without warnings.

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
  - Build a slim macOS PyInstaller sidecar equivalent to the Windows release profile (`packaging/sidecar/release-dist/sabi-sidecar/`) for onboarding, probes, model-cache operations, and runtime-pack installation.
  - `extraResources` ships the slim sidecar to `Contents/Resources/sidecar/sabi-sidecar/`, matching the production lookup shape used on Windows (`resources/sidecar/sabi-sidecar/`).
  - `afterPack` hook ensures every native binary inside the bundled slim sidecar tree is signed; unsigned `.dylib` files break notarization.
  - Confirm `meta.version`, `probe.run`, `cache.status`, and runtime install methods work from inside the signed app bundle.
- Full runtime pack:
  - Add macOS runtime manifests under `configs/runtime/` (for example `full-cpu-macos-arm64.json` and `full-cpu-macos-x64.json`, or one manifest if the runtime manager remains single-platform at package time).
  - Build full dictation-capable macOS runtime packs separately from the DMG, per architecture; do not ship a universal2 runtime until Torch/MediaPipe/faster-whisper have been verified end-to-end.
  - Publish the runtime zip artifacts to temporary GitHub Release hosting, matching the current Windows `sabi-runtime-packs` flow, or to the production artifact store when available.
  - The installed app downloads, hash-verifies, extracts, and activates the full runtime under `~/Library/Application Support/Sabi/runtime/full-cpu/current/`.
  - Electron should prefer the active full runtime sidecar over the bundled slim sidecar after activation, same as Windows.
  - Document whether downloaded runtime zips are signed/notarized themselves, and how quarantine/xattr handling is verified after download and extraction.
- Optional virtual audio:
  - Link out to `docs/INSTALL-BLACKHOLE.md` (new doc) explaining the BlackHole install. Bundling drivers in v1 is out of scope.
- Build pipeline:
  - `python scripts/build_sidecar_release.py` (on macOS) builds the slim macOS sidecar before packaging.
  - Add/adjust a full-runtime build script for macOS runtime packs if `scripts/build_sidecar_full_cpu.py` remains Windows-specific.
  - `npm run package:mac` runs electron-builder for macOS targets only.
  - Output to `desktop/dist/`.
- Sanity tests on a clean macOS VM/host:
  - Mount DMG, drag to Applications, launch.
  - First launch triggers Camera + Microphone + Accessibility + Input Monitoring prompts in onboarding (TICKET-047).
  - Onboarding can install the full runtime from the published runtime URL and relaunch/reconnect the sidecar from `~/Library/Application Support/Sabi/runtime/full-cpu/current/`.
  - `spctl --assess --verbose` reports `accepted`.
  - `codesign -dv --verbose=4` shows the Developer ID signature.
  - Downloaded/activated full runtime sidecar answers `meta.version` and does not trip Gatekeeper/quarantine checks.
- `docs/distribution_packaging/SIGNING_MACOS.md`:
  - Cert + provisioning, notarization env vars, common failure modes (unsigned native modules, invalid bundle IDs, hardened runtime entitlements missing).
  - Include runtime-pack signing/notarization/quarantine guidance, not just DMG signing.

## Acceptance criteria

- [ ] `npm run package:mac` produces signed + notarized `Sabi-<version>-arm64.dmg`, `Sabi-<version>-x64.dmg`, and matching `.zip` files.
- [ ] `spctl --assess --type execute -v /Applications/Sabi.app` returns `accepted`.
- [ ] Installed app launches on a clean macOS 13+ machine and reaches the onboarding wizard with all permission prompts firing at the right step.
- [ ] Full macOS runtime pack downloads from the configured manifest URL, verifies SHA256, extracts under `~/Library/Application Support/Sabi/runtime/full-cpu/current/`, and becomes the preferred sidecar.
- [ ] Notarization passes in CI (or locally) without manual stapling steps.
- [ ] Slim sidecar binary inside `Contents/Resources/sidecar/sabi-sidecar/` runs and answers `meta.version`.
- [ ] Activated full runtime sidecar runs and answers `meta.version` without Gatekeeper/quarantine warnings.
- [ ] `docs/distribution_packaging/SIGNING_MACOS.md` documents the cert + notarization workflow for both the app bundle and runtime packs.

## Out of scope

- Mac App Store submission (different cert chain, sandboxed; not pursued).
- Bundling BlackHole (license + driver-install complexity).
- Linux packaging (TICKET-054).
- Auto-update wiring (TICKET-051).
- Production CDN/storage selection for runtime packs; temporary GitHub Release hosting can be used for test builds.

## Notes

- Apple Silicon vs Intel: build per-arch for both the app and full runtime packs; do not ship a "universal2" sidecar unless it has been verified end-to-end (Torch wheels can break universal builds).
- Notarization stapling is automatic in electron-builder; manual `xcrun stapler` is only a debug fallback.
- The hardest failure is "notarization succeeded but Gatekeeper still warns" - usually an unsigned `.dylib` inside the Python sidecar tree, or a downloaded runtime zip that preserves quarantine attributes after extraction.
- Windows now uses `docs/distribution_packaging/WINDOWS_SIDECAR_RUNTIME_FLOW.md`: slim sidecar bundled in the installer, full runtime zip hosted via GitHub Release, downloaded after install, and activated from user data. macOS should follow the same product shape unless a macOS-specific signing constraint forces a different runtime distribution path.

## References

- `project_roadmap.md` line 260 - macOS signing baseline.
- TICKET-043 - sidecar tree that must be signed end-to-end.
- TICKET-047 - onboarding step that drives macOS permission prompts.
- `docs/distribution_packaging/WINDOWS_SIDECAR_RUNTIME_FLOW.md` - current Windows bootstrap sidecar + full runtime download model to mirror.
