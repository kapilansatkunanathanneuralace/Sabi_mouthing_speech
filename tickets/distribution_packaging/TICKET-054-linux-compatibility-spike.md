# TICKET-054 - Linux compatibility spike

Phase: 3 - Distribution & Packaging
Epic: Packaging
Estimate: M
Depends on: TICKET-053
Status: Not started

## Goal

Once Windows and macOS packaging is stable, research what it takes to ship Linux. This is a spike, not an implementation: the output is a written assessment, not a working installer. We answer "is this worth doing now?" before committing to it as a real product surface.

## System dependencies

- Ubuntu 22.04 / 24.04 LTS test VM.
- Optional: Fedora and Arch VMs for breadth.

## Python packages

None.

## Work

- Investigate packaging options:
  - electron-builder Linux targets: AppImage, deb, rpm, pacman.
  - Snap / Flatpak as alternatives, with their sandboxing implications.
- Investigate platform mismatches:
  - Global shortcuts on X11 vs Wayland - what actually works in 2026?
  - Camera/microphone permission prompts - browsers fake this; Electron does not.
  - Text injection: `xdotool`, `ydotool`, AT-SPI for Wayland; failure modes per compositor.
  - Virtual mic: PulseAudio null-sink vs PipeWire loopback; documentation lift.
  - Torch wheels: CUDA on Linux is the easy case; ROCm + Apple-style MPS does not apply.
- Investigate hardware notes:
  - Camera backends in OpenCV (V4L2) and MediaPipe interactions.
  - sounddevice + ALSA/PulseAudio/PipeWire stacks.
- Distribution and signing:
  - AppImage signing patterns (gpg, AppImageUpdate).
  - Trust story without an official "Linux notary".
- Auto-update on Linux:
  - electron-updater AppImageUpdater path.
  - Distro repos vs direct-download; pick one for v1.
- Output deliverables:
  - `docs/distribution_packaging/LINUX_SPIKE.md` containing: target distros + DEs, gaps vs Windows/macOS, recommended path (or "not now" with reasons), rough estimate to implement.
  - A 1-page summary at the top so PM can decide without reading the full doc.

## Acceptance criteria

- [ ] `docs/distribution_packaging/LINUX_SPIKE.md` exists with a 1-page summary + full assessment.
- [ ] The doc explicitly answers: "If we ship Linux v1 today, what works, what is broken, and how long to fix?"
- [ ] At least one Linux test session (AppImage on Ubuntu 24.04) is recorded with screenshots/logs of what actually happens.
- [ ] The doc lists the Linux-specific tickets that would need to be opened if we chose to ship; numbering is suggestive only (no actual tickets created here).
- [ ] PM can read the summary and pick "go", "delay", or "no" without follow-up questions.

## Out of scope

- Actually shipping a Linux installer.
- Reworking input/output adapters for Wayland (separate tickets if we proceed).
- Maintaining Linux QA infrastructure.

## Notes

- Linux audio routing has improved with PipeWire but still requires real testing.
- Wayland global shortcuts remain a moving target in 2026; treat any "easy" claim with suspicion.
- The decision matters more than the code in this ticket - keep the writeup short and decision-oriented.

## References

- `project_roadmap.md` line 222 - Linux deferral note.
- TICKET-053 - QA practices the Linux track would inherit if greenlit.
