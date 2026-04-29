# TICKET-043 - PyInstaller sidecar build

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: L
Depends on: TICKET-042
Status: Done

## Goal

Produce a standalone, no-Python-required `sabi-sidecar` binary tree using PyInstaller for both Windows (x64) and macOS (arm64 + x64). Use `--onedir` mode because Torch, OpenCV, and MediaPipe ship many dynamic resources that break under `--onefile`. The output is what every later installer ticket bundles into the Electron app.

## System dependencies

- Windows: Python 3.11 x64, MSVC build tools (only if any dependency falls back to source).
- macOS: Python 3.11 universal or arm64, Xcode CLI tools, Apple Developer ID cert (signing comes in TICKET-050).
- Both: enough disk space; expect ~600 MB - 1.5 GB sidecar tree depending on torch flavor.

## Python packages

- `pyinstaller>=6.5` added to `[project.optional-dependencies] packaging` in `pyproject.toml`.
- No runtime dependency changes; sidecar imports the same `sabi` package from TICKET-042.

## Work

- Add `packaging/sidecar/sabi_sidecar.spec` PyInstaller spec:
  - Entry script: `packaging/sidecar/entry.py` that calls `sabi.sidecar.server.main()`.
  - `datas`: `mediapipe` modules tree, `third_party/chaplin/`, `configs/`, prompt templates under `src/sabi/cleanup/prompts/`, plus any `*.tflite` / `*.onnx` files MediaPipe ships dynamically.
  - `hiddenimports`: `torch`, `torchvision`, `torchaudio`, `pytorch_lightning`, `omegaconf`, `hydra`, `faster_whisper`, `webrtcvad`, `sounddevice`, `pyperclip`, `keyboard`, `pyautogui`.
  - Exclude: `tkinter`, unused QT plugins, large unused torch backends if practical.
- Add `scripts/build_sidecar.py` that:
  - Runs PyInstaller with the spec.
  - Verifies the resulting binary launches and answers a `meta.version` JSON-RPC call.
  - Prints the resolved bundle size + tree layout.
- Add a small smoke test under `tests/test_sidecar_smoke.py` that is skipped unless `SABI_SIDECAR_BIN` env var points at a built artifact, so CI can opt-in.
- Document the build steps in `docs/distribution_packaging/SIDECAR_BUILD.md`:
  - Per-OS prerequisites.
  - `python scripts/build_sidecar.py` usage.
  - Known PyInstaller pitfalls for `mediapipe` (missing `modules/` tree) and `torch` (missing `lib*.dylib` / `lib*.dll`).
- Add a `.gitignore` rule for `packaging/sidecar/build/` and `packaging/sidecar/dist/`.
- Make sure the runtime resource root selection from TICKET-042 routes to a "next to the binary" `resources/` directory in the frozen layout, falling back to repo root in dev.

## Acceptance criteria

- [x] `python scripts/build_sidecar.py` produces `packaging/sidecar/dist/sabi-sidecar/` on Windows. macOS validation requires a macOS host and is deferred to installer/CI tickets.
- [x] The resulting `sabi-sidecar` binary responds to `meta.version` over stdio in the local Windows workspace.
- [x] Frozen runtime paths resolve `configs/vsr_weights.toml`; full `models.download_vsr` binary validation is deferred to model-download QA because it requires network/model cache setup.
- [x] `dictation.silent.start --dry-run` is covered by sidecar dispatcher tests; frozen binary validation is deferred to desktop QA after installer integration.
- [x] Bundle size and resolved layout are printed by the build script and recorded in `docs/distribution_packaging/SIDECAR_BUILD.md`.
- [x] Build artifacts are excluded from Git via `.gitignore`.

## Out of scope

- Code signing the sidecar binary (covered by TICKET-049 / TICKET-050 for the parent installer).
- Reducing bundle size below 200 MB (a stretch goal, not a gate).
- CUDA-specific builds; first cut targets CPU torch wheels to keep the matrix tractable.

## Notes

- Prefer `--onedir`; `--onefile` adds 3-10 s startup and triggers more antivirus false positives.
- MediaPipe and Chaplin assets are the most common cause of "works in dev, fails in dist" - the spec must explicitly add them.
- macOS arm64 vs x64 wheels for torch differ; build per-arch and ship per-arch installers.

## References

- `src/sabi/models/vsr/_chaplin_path.py` - asset resolution that must accept the frozen layout.
- `configs/vsr_weights.toml` - manifest the frozen sidecar must still find.
- `project_roadmap.md` line 235 - "Python sidecar (PyInstaller)" baseline.
