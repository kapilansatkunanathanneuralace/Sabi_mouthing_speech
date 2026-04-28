# Sidecar Build

This document covers the PyInstaller sidecar introduced by `TICKET-043`.
The sidecar is the Python process that the future Electron app will spawn and
talk to over JSON-RPC on stdio.

## Prerequisites

Use Python 3.11 for release builds when possible. The current dev environment may
run newer Python versions, but release packaging should stay close to the model
wheel matrix.

Install the packaging extra:

```powershell
pip install -e ".[packaging]"
```

Windows release builds should run on Windows x64. macOS release builds must run on
macOS for the target architecture; PyInstaller does not cross-compile.

## Build

From the repo root:

```powershell
python scripts/build_sidecar.py
```

The script runs:

```powershell
python -m PyInstaller packaging/sidecar/sabi_sidecar.spec --noconfirm
```

Then it launches the generated sidecar and sends:

```json
{"jsonrpc":"2.0","id":1,"method":"meta.version"}
```

Expected output includes:

- `sidecar_root` - the generated folder.
- `sidecar_bin` - the executable to bundle into Electron.
- `bundle_size` - approximate size of the full tree.
- `largest_entries` / `largest_directories` - bundle size audit output.
- `smoke` - the JSON-RPC response.

Local Windows validation on 2026-04-28 produced a working
`packaging/sidecar/dist/sabi-sidecar/sabi-sidecar.exe` bundle. The bundle was
approximately 4.7 GB in the CUDA-enabled development environment and responded
to `meta.version` with protocol version `1.0.0`.

## Release Sidecar Profile

Windows installer builds use a pruned sidecar profile:

```powershell
python scripts/build_sidecar_release.py
```

This uses `packaging/sidecar/sabi_sidecar_release.spec` and writes output to:

```text
packaging/sidecar/release-dist/sabi-sidecar/
```

The release profile is intentionally smaller than the development sidecar. It keeps
the JSON-RPC server, onboarding probe surface, and cache methods, while avoiding the
eager `collect_submodules("sabi")` path that pulls CUDA-heavy Torch and eval stacks
from the developer environment. On 2026-04-28, local validation produced a 229.7 MB
release sidecar. Largest contributors:

- `cv2`: 147.6 MB
- `numpy.libs`: 20.0 MB
- `PIL`: 12.7 MB
- `sabi-sidecar.exe`: 12.1 MB

Full inference release builds should be produced from a CPU-only dependency
environment when the production runtime dependency set is finalized.

## Full CPU Runtime Pack

Real silent/audio/fused dictation needs the full ML runtime, which is intentionally
not bundled in the NSIS installer. Build that runtime separately from a CPU-only
environment:

```powershell
python scripts/build_sidecar_full_cpu.py
```

This uses `packaging/sidecar/sabi_sidecar_full_cpu.spec`, writes the frozen sidecar to
`packaging/sidecar/full-cpu-dist/`, then creates a zip and manifest under
`packaging/sidecar/runtime-packs/`. The full runtime pack should include Torch CPU,
TorchVision, MediaPipe, faster-whisper/CTranslate2, AV, SciPy, Chaplin resources, and
the Sabi dictation pipelines. Do not build this artifact from a CUDA development
environment unless you intentionally want a very large GPU runtime pack.

The desktop app reads `configs/runtime/full-cpu.json` from packaged resources and
activates the downloaded runtime under `%LOCALAPPDATA%\Sabi\runtime\full-cpu`.

## Output Layout

The generated tree is ignored by Git:

```text
packaging/sidecar/dist/sabi-sidecar/
  sabi-sidecar.exe       # Windows
  sabi-sidecar           # macOS/Linux-style name
  resources/
    configs/
    third_party/chaplin/
    sabi/cleanup/prompts/
```

The runtime helper in `src/sabi/runtime/paths.py` resolves these bundled resources
when `sys.frozen` is set by PyInstaller. Writable data such as downloaded model
weights, reports, and logs should go under the app-owned user data directory, not
inside the read-only bundle.

## Known Pitfalls

- **Use onedir, not onefile.** Onefile adds startup extraction time and tends to
  break dynamic ML resources.
- **MediaPipe needs data files.** Missing `mediapipe/modules` often appears as a
  runtime `FileNotFoundError`.
- **webrtcvad-wheels uses different metadata.** A local PyInstaller hook is used
  so the contrib `webrtcvad` hook does not require missing `webrtcvad` metadata.
- **Torch ships native libraries.** Missing `torch` / `torchvision` binaries can
  appear as missing `.dll` / `.dylib` errors only after the frozen app starts.
- **Chaplin must be bundled.** `third_party/chaplin` is a git submodule; make sure
  it is initialized before building.
- **Model weights are not bundled.** The frozen sidecar still downloads and verifies
  VSR weights via `models.download_vsr`.
- **Build per OS.** Windows builds on Windows, macOS builds on macOS. Code signing
  and notarization are handled later by `TICKET-049` and `TICKET-050`.

## Manual Smoke

After building, you can run the smoke manually:

```powershell
$req = '{"jsonrpc":"2.0","id":1,"method":"meta.version"}'
$req | packaging\sidecar\dist\sabi-sidecar\sabi-sidecar.exe
```

For CI or local opt-in tests:

```powershell
$env:SABI_SIDECAR_BIN = "packaging\sidecar\dist\sabi-sidecar\sabi-sidecar.exe"
pytest tests/test_sidecar_smoke.py
```

## Windows Installer Prerequisite

`TICKET-049` uses the release sidecar output:

```powershell
python scripts/build_sidecar_release.py
cd desktop
npm run package:win
```

The desktop package config copies `packaging/sidecar/release-dist/sabi-sidecar/` into
Electron's resources as `resources/sidecar/sabi-sidecar/`, which matches the
production sidecar lookup in the Electron main process.
