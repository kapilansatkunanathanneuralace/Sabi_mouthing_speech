# macOS Signing and Notarization

TICKET-050 packages Sabi as a Developer ID macOS app. The macOS build must run on
macOS; Windows can prepare config and scripts, but it cannot build PyInstaller
macOS binaries, sign app bundles, notarize, staple, or run Gatekeeper checks.

## Required Accounts and Certificates

- Apple Developer Program membership.
- Developer ID Application certificate installed in the build keychain.
- App Store Connect API key for notarization, preferred:
  - `APPLE_API_KEY`
  - `APPLE_API_KEY_ID`
  - `APPLE_API_ISSUER`
- Alternative notarization path:
  - `APPLE_ID`
  - `APPLE_APP_SPECIFIC_PASSWORD`
  - `APPLE_TEAM_ID`

For sidecar deep signing, set one of:

```bash
export MAC_CODESIGN_IDENTITY="Developer ID Application: Example, Inc. (TEAMID)"
export CSC_NAME="$MAC_CODESIGN_IDENTITY"
```

## Build Order

From the repo root on macOS:

```bash
python -m pip install -e ".[packaging]"
python scripts/build_sidecar_release.py
```

Then package the app:

```bash
cd desktop
npm ci
npm run package:mac
npm run validate:mac-package
```

`npm run package:mac` builds both `.dmg` and `.zip` artifacts through
electron-builder for the current host architecture. Use `npm run package:mac:arm64`
or `npm run package:mac:x64` on matching macOS runners to produce per-arch outputs.
The `.zip` output is needed later for auto-update.

## Entitlements

The app uses `desktop/build/entitlements.mac.plist` for hardened runtime signing.
The current entitlements allow:

- JIT for Electron.
- Unsigned executable memory for the ML runtime stack.
- Camera and microphone device access.

This is a non-Mac-App-Store Developer ID build, so App Sandbox is not enabled.

## Sidecar Signing

The macOS app bundles a slim PyInstaller sidecar under:

```text
Sabi.app/Contents/Resources/sidecar/sabi-sidecar/
```

`desktop/scripts/after-pack-mac.mjs` signs native files inside that tree before
electron-builder signs and notarizes the app bundle. Unsigned `.dylib`, `.so`, or
native extension files inside the PyInstaller tree are a common cause of:

```text
notarization succeeded, but Gatekeeper still warns
```

If signing fails, inspect the exact file named in the error and verify it is not
quarantined, corrupted, or missing execute permissions.

## Runtime Packs

The DMG should not contain the full dictation runtime. Match the Windows bootstrap
model:

1. Bundle the slim sidecar in the app.
2. Publish full runtime zip artifacts separately.
3. Point the packaged runtime manifest at the published artifact URL.
4. Download, hash-verify, extract, and activate the runtime after install.

The active runtime path is:

```text
~/Library/Application Support/Sabi/runtime/full-cpu/current/
```

Downloaded runtime packs need their own signing/quarantine policy. At minimum,
verify that extracted runtime binaries answer `meta.version` and do not trigger
Gatekeeper warnings after download on a clean machine.

Useful inspection commands:

```bash
xattr -lr "$HOME/Library/Application Support/Sabi/runtime/full-cpu/current" | grep quarantine
codesign --verify --deep --strict --verbose=4 "$HOME/Library/Application Support/Sabi/runtime/full-cpu/current/sabi-sidecar/sabi-sidecar"
```

## Notarization and Gatekeeper Checks

After packaging:

```bash
spctl --assess --type execute -v /Applications/Sabi.app
codesign -dv --verbose=4 /Applications/Sabi.app
codesign --verify --deep --strict --verbose=4 /Applications/Sabi.app
```

Expected `spctl` result:

```text
/Applications/Sabi.app: accepted
source=Notarized Developer ID
```

If `spctl` fails, check:

- Bundle ID matches `com.sabi.desktop`.
- Developer ID certificate is valid and trusted.
- Hardened runtime is enabled.
- Entitlements are present.
- Every nested native binary is signed.
- Notarization credentials are set for the build.
- The stapled ticket is present on the `.app` inside the DMG.

## Clean Host Smoke

On a clean macOS 13+ host:

1. Mount the DMG.
2. Drag Sabi to Applications.
3. Launch Sabi.
4. Confirm onboarding appears.
5. Confirm Camera, Microphone, Accessibility, and Input Monitoring prompts occur
   at the expected onboarding steps.
6. Install the full runtime from the runtime panel.
7. Confirm Electron reconnects to the activated full runtime sidecar.
8. Run `meta.version` against both the bundled slim sidecar and activated runtime
   sidecar.
