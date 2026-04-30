# Windows Sidecar Runtime Flow

This note explains how the Windows desktop app is packaged, what lands on the
user's machine during the initial install, and how the larger full-runtime sidecar
zip is used after install.

## Packaging Summary

The Windows installer is a bootstrap NSIS package built by electron-builder. It
contains the Electron shell, renderer assets, icons, config files, and a slim
PyInstaller sidecar. It intentionally does not contain model weights or the full
ML dictation runtime.

Build the slim sidecar first:

```powershell
python scripts/build_sidecar_release.py
```

Then build the Windows installer:

```powershell
cd desktop
npm run package:win
```

`desktop/scripts/package-win.mjs` checks that the slim sidecar exists at
`packaging/sidecar/release-dist/sabi-sidecar/sabi-sidecar.exe`, then invokes
electron-builder with `desktop/build/electron-builder.yml`.

The packaged output is written to `desktop/dist/`, including:

- `Sabi-<version>-setup.exe`
- `win-unpacked/`, which is useful for local inspection and validation

## Initial Install Layout

The installer is configured as a per-user install:

- `oneClick: false`
- `perMachine: false`
- `allowElevation: false`
- `runAfterFinish: true`
- desktop and Start Menu shortcuts enabled

The bundled slim sidecar is copied through `extraResources`:

```yaml
extraResources:
  - from: ../packaging/sidecar/release-dist/sabi-sidecar
    to: sidecar/sabi-sidecar
```

After installation, Electron resolves that sidecar from:

```text
<install resources>/sidecar/sabi-sidecar/sabi-sidecar.exe
```

In a packaged Electron app, this is addressed as:

```text
process.resourcesPath/sidecar/sabi-sidecar/sabi-sidecar.exe
```

The installed app also carries the full-runtime manifest from
`configs/runtime/full-cpu.json` as:

```text
process.resourcesPath/runtime/full-cpu.json
```

## What The Slim Sidecar Does

The slim sidecar is the always-present Python process used immediately after
installation. It is built from `packaging/sidecar/sabi_sidecar_release.spec`.

That profile keeps enough Python code for:

- JSON-RPC lifecycle and `meta.version`
- onboarding probes
- model cache status, verification, and downloads
- runtime-pack installation flow

It excludes the heavy dictation dependencies, including Torch, faster-whisper,
MediaPipe, AV, SciPy, and related ML stacks. This keeps the installer small enough
for a first-run bootstrap package.

The frozen sidecar entrypoint is `packaging/sidecar/entry.py`. It starts
`sabi.sidecar.server.run_stdio_server()`, which reads line-delimited JSON-RPC
requests from stdin and writes JSON-RPC responses to stdout. Electron starts this
process in `desktop/electron/sidecar/process.ts`.

## Full Runtime Zip

Real silent, audio, and fused dictation require the full CPU runtime. That runtime
is built separately:

```powershell
python scripts/build_sidecar_full_cpu.py
```

The script uses `packaging/sidecar/sabi_sidecar_full_cpu.spec`, writes a full
PyInstaller sidecar tree under `packaging/sidecar/full-cpu-dist/`, then creates a
zip and manifest under:

```text
packaging/sidecar/runtime-packs/
```

The full runtime zip should include the ML stack needed for dictation, including
Torch CPU, TorchVision, MediaPipe, faster-whisper/CTranslate2, AV, SciPy, Chaplin
resources, and the Sabi dictation pipelines.

The generated zip is not bundled into the NSIS installer. Instead, publish it and
update `configs/runtime/full-cpu.json` with its URL, SHA256, size, version, and
`sidecar_dir`.

For local development, `configs/runtime/full-cpu.json` may point at a `file:///...`
URL. For production, it should point at a published HTTPS URL.

The current temporary hosting target is a public GitHub Release asset:

```text
https://github.com/kapz28/sabi-runtime-packs/releases/download/full-cpu-v0.0.1-win-x64/sabi-full-cpu-runtime-0.0.1-win-x64.zip
```

That release asset is suitable for testing downloads on other machines. Move it to
dedicated storage or a CDN before relying on it for high-volume production traffic.

## Post-Install Activation

The runtime zip is used after the app is installed, from the renderer's
`RuntimePanel`. The user clicks **Install full runtime**, which calls:

```text
window.sabi.runtime.download()
```

The preload bridge forwards that to Electron IPC, and `desktop/electron/main.ts`
routes it to `RuntimeManager.download()` in `desktop/electron/runtime.ts`.

`RuntimeManager.download()` does the full activation flow:

1. Reads `process.resourcesPath/runtime/full-cpu.json`.
2. Chooses the runtime source from an explicit parameter, `SABI_FULL_RUNTIME_ZIP`,
   or `manifest.url`.
3. Downloads or copies the zip to
   `%LOCALAPPDATA%\Sabi\runtime\full-cpu\downloads\`.
4. Verifies the SHA256 against the manifest.
5. Extracts the zip with PowerShell `Expand-Archive` into a staging directory.
6. Confirms the extracted sidecar exists at
   `staging/<sidecar_dir>/sabi-sidecar.exe`.
7. Moves staging to `%LOCALAPPDATA%\Sabi\runtime\full-cpu\current`.
8. Writes `runtime-pack.json` into the active runtime directory.
9. Reconnects the Electron sidecar process.

After activation, the active runtime sidecar lives at:

```text
%LOCALAPPDATA%\Sabi\runtime\full-cpu\current\sabi-sidecar\sabi-sidecar.exe
```

## Runtime Selection

Electron chooses which sidecar to start in `desktop/electron/sidecar/path.ts`.

In development:

1. `SABI_DESKTOP_SIDECAR_BIN`, if set.
2. `packaging/sidecar/dist/sabi-sidecar/sabi-sidecar.exe`, if present.
3. `python -m sabi sidecar`.

In a packaged app:

1. The active full runtime sidecar, if present under
   `%LOCALAPPDATA%\Sabi\runtime\full-cpu\current`.
2. The bundled slim sidecar under `process.resourcesPath/sidecar/sabi-sidecar`.

This means the initial install can launch and onboard using the slim sidecar. Once
the full runtime zip is downloaded and activated, Electron restarts the sidecar and
uses the full runtime for dictation.

## Data Locations

The installer and sidecar bundle are read-only application resources. User-owned
data is stored outside the install directory:

- Full runtime: `%LOCALAPPDATA%\Sabi\runtime\full-cpu`
- Model weights: `%LOCALAPPDATA%\Sabi\models`
- Runtime downloads: `%LOCALAPPDATA%\Sabi\runtime\full-cpu\downloads`

Uninstall keeps user data and model cache by default.

## Validation Points

`npm run validate:win-package` checks the important packaged layout:

- NSIS setup executable exists in `desktop/dist/`.
- Installer archive stays below the 250 MB budget.
- Slim sidecar exists under `win-unpacked/resources/sidecar/sabi-sidecar/`.
- Runtime manifest exists under `win-unpacked/resources/runtime/full-cpu.json`.
- Packaged slim sidecar answers `meta.version`.
- Installer signature status is reported.

For a clean Windows VM smoke test, install `Sabi-<version>-setup.exe`, launch the
app, confirm onboarding appears, install the full runtime from the runtime panel,
and verify dictation actions become available.
