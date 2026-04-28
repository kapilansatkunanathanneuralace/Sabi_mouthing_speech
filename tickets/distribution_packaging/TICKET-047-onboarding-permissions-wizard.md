# TICKET-047 - Onboarding and permissions wizard

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-045, TICKET-046
Status: Done

## Goal

Walk a new user from "just installed" to "first dictation works" with a guided, OS-aware wizard. The wizard collects Camera, Microphone, Accessibility/Input permissions, optional virtual mic install, optional Ollama setup, and triggers the model download. It uses the sidecar's `probe.run` to verify each step instead of relying on user self-report.

## System dependencies

- macOS: Camera, Microphone, Accessibility, Input Monitoring permissions (system prompts).
- Windows: Camera + Microphone privacy toggles.
- Optional: Ollama install, VB-Cable (Windows) / BlackHole (macOS).

## Python packages

None.

## Work

- React wizard under `desktop/renderer/src/onboarding/`:
  - Steps: Welcome, Camera, Microphone, Accessibility/Input, Models, Optional (Ollama, virtual mic), Done.
  - Each step has its own component, copy is OS-detected from `process.platform`.
  - Progress is persisted; if user quits mid-onboarding, they resume on next launch.
- Permission probes:
  - Camera/microphone: call `probe.run` on the sidecar; show pass/fail with retry.
  - Accessibility (macOS): use Electron's `systemPreferences.isTrustedAccessibilityClient(true)` to nudge the prompt.
  - Input Monitoring (macOS): same pattern with `getMediaAccessStatus`.
  - Windows privacy: deep-link to the right Settings page when the probe says "MISSING".
- Model download:
  - Calls `models.download_vsr` over the sidecar with progress notifications surfacing in a real progress bar.
  - Verifies hashes via existing `configs/vsr_weights.toml`; failure rolls back and asks the user to retry.
- Optional steps:
  - Ollama: detect via `probe.run`; if missing, link to `docs/INSTALL.md` Ollama section and offer a "skip for now" exit.
  - Virtual mic: link to `docs/INSTALL-VBCABLE.md` (Windows) or a future `INSTALL-BLACKHOLE.md` (macOS) per platform; this ticket does not bundle drivers.
- Settings on completion:
  - Mark `onboardingCompleted: true` in the settings store.
  - Default pipeline = `silent` (matches PoC framing) but switchable from settings.
- Tests:
  - Component tests for each step using mocked sidecar replies.
  - Persistence test for resume-after-quit.
- Update `docs/distribution_packaging/README.md` with a "First launch UX" section and screenshots once the wizard exists.

## Acceptance criteria

- [x] Fresh install on Windows triggers Camera + Microphone steps; local validation is through the Electron wizard/probe path.
- [x] Fresh install on macOS triggers Camera + Microphone + Accessibility + Input Monitoring steps; final OS prompt validation requires a macOS host.
- [x] Each permission step uses `probe.run` to verify status before allowing "Next".
- [x] Model download step shows real-time progress and hash-verifies the downloaded files through the Python sidecar downloader.
- [x] Quitting at any step and reopening resumes from that step.
- [x] On completion, the tray and settings reflect onboarded state.
- [x] Skipping optional steps (Ollama, virtual mic) lands the user on a working dictation surface; the cleanup pipeline degrades gracefully when Ollama is absent (existing behavior).
- [x] Unit tests for steps and persistence pass.

## Out of scope

- Auto-installing Ollama, VB-Cable, or BlackHole (out of policy + complexity).
- Sign-in / accounts (post-PoC product decision).
- Telemetry or install metrics (separate ticket if/when needed).

## Notes

- The hardest step on macOS is Accessibility - it is opaque to users; copy + screenshots are critical.
- Treat the wizard as the only place where we "explain ourselves"; deeper docs live elsewhere.
- A failed model download is the most likely first-launch crash mode; design the retry path explicitly.

## References

- `src/sabi/probe.py` - structured probe results consumed here.
- `docs/INSTALL.md` - existing install guidance the wizard links to.
- `project_roadmap.md` lines 279-289 - one-time setup flow.
