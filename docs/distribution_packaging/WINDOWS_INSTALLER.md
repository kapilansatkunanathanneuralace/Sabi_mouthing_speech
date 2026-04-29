# Windows Installer

TICKET-049 packages the Electron desktop shell as a per-user NSIS installer for
Windows x64. The installer bundles the built Electron app and the PyInstaller sidecar
tree, but it does not bundle model weights.
It also does not bundle the full dictation runtime; the app downloads a separate
CPU runtime pack before enabling silent/audio/fused dictation.

## Prerequisites

- Windows 10/11 x64 build host.
- Node.js 20 LTS and npm 10.
- Built release sidecar at `packaging/sidecar/release-dist/sabi-sidecar/sabi-sidecar.exe`.
- Optional self-signed or production signing certificate env vars documented in
  `SIGNING_WINDOWS.md`.

Build the sidecar first from the repo root:

```powershell
python scripts/build_sidecar_release.py
```

Then package the desktop app:

```powershell
cd desktop
npm run package:win
```

Output is written to `desktop/dist/`, including `Sabi-<version>-setup.exe` and the
`win-unpacked/` tree used for local inspection.

## Validation

After packaging:

```powershell
cd desktop
npm run validate:win-package
```

The validation script checks:

- An NSIS setup executable exists in `desktop/dist/`.
- The installer archive stays below the 250 MB budget.
- The sidecar is present under `win-unpacked/resources/sidecar/sabi-sidecar/`.
- The full CPU runtime manifest is present under `win-unpacked/resources/runtime/`.
- The packaged sidecar answers `meta.version` over JSON-RPC.
- The installer Authenticode status is printed. Set `WIN_EXPECT_SIGNED=1` to fail
  validation unless Windows reports a valid signature.

For manual signature inspection, also run:

```powershell
Get-AuthenticodeSignature .\dist\Sabi-0.0.1-setup.exe | Format-List
```

## Local Self-Signed Installers

Developer machines can create and trust a local test certificate:

```powershell
cd desktop
npm run signing:create-local-cert -- -Trust
$env:WIN_CSC_LINK = ".certs\sabi-local-test-signing.pfx"
$env:WIN_CSC_KEY_PASSWORD = "<pfx password>"
$env:WIN_SELF_SIGNED_LOCAL = "1"
$env:WIN_EXPECT_SIGNED = "1"
npm run package:win
npm run validate:win-package
```

This packages without electron-builder's signing toolchain, signs the generated setup
executable with PowerShell, and makes local Authenticode validation pass on the same
user account when the certificate is trusted. It is not a production release
signature and other machines will not trust it unless the certificate is manually
imported there.

## Installing The App

After packaging, run `desktop/dist/Sabi-<version>-setup.exe`. The installer is
per-user, does not request admin elevation, and creates Start Menu and desktop
shortcuts. Launch Sabi from the finish page or shortcut and complete onboarding.

Model weights are intentionally excluded from the installer and download into
`%LOCALAPPDATA%\Sabi\models` through the app's cache manager. Uninstall keeps user
data and model cache by default.

## Full Dictation Runtime

The installer is a bootstrap app. It includes a slim sidecar for onboarding, probing,
model-cache operations, and runtime-pack installation. Real dictation requires a
separate full CPU sidecar runtime pack built with:

```powershell
python scripts/build_sidecar_full_cpu.py
```

Publish the generated zip and update `configs/runtime/full-cpu.json` with its URL,
SHA256, and size. On first launch, the desktop app can download, verify, extract, and
activate that runtime under `%LOCALAPPDATA%\Sabi\runtime\full-cpu`. After activation,
Electron restarts the sidecar from the full runtime path.

## VM Smoke

On a clean Windows 11 VM:

1. Run the setup executable without admin elevation.
2. Launch Sabi from the finish page or Start Menu.
3. Confirm the onboarding wizard appears and can advance to the Camera step.
4. Uninstall Sabi. User data and model cache are kept by default.

Model weights download on first launch through the TICKET-048 cache manager.

## Local Validation

Local validation on 2026-04-28 produced a self-signed
`desktop/dist/Sabi-0.0.1-setup.exe` of approximately 174 MB using the pruned release
sidecar. `npm run validate:win-package` passed with `Installer signature: Valid` on
the machine that created and trusted the local test certificate. The unpacked app
also launched in a bounded smoke test.

Self-signed trust is local to the developer machine. A production OV/EV or Azure
Trusted Signing certificate and clean Windows 11 VM install/uninstall validation are
still required before marking the Windows installer ticket fully done.
