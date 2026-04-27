# TICKET-019 - Virtual mic install integration (VB-Cable)

Phase: 1 - ML PoC
Epic: Infra
Estimate: S
Depends on: TICKET-002
Status: Not started

## Goal

Make VB-Cable a known, detected, and documented prerequisite of the meeting-mode path. Extend `scripts/probe_env.py` so it reports whether a VB-Cable-compatible virtual audio device is present under the names we expect, and write `docs/INSTALL-VBCABLE.md` with the one-time user-facing steps from the roadmap's "one-time setup" block. No auto-install - we do not ship the driver, we tell the user exactly how to install it and verify it.

## System dependencies

- **VB-Audio Virtual Cable** (free, donationware) from https://vb-audio.com/Cable/. The standard version is sufficient for PoC; we do not need `VB-Audio Matrix` or the Banana / Voicemeeter products.
- On Windows 10/11 the installer requires a reboot for the driver to register.
- No Mac/Linux analogue shipped in this PoC - explicitly out of scope (see references).

## Python packages

Already installed in TICKET-002:

- `sounddevice` - used to enumerate devices and verify VB-Cable is present by name.
- `rich` - for the probe output.

No additions.

## Work

- Write `docs/INSTALL-VBCABLE.md`:
  - Step-by-step link to the VB-Audio download page, checksum from the vendor's page (document the expected sha256 snapshot so drift is visible).
  - Installer instructions (right-click > run as admin, reboot).
  - How to verify the device exists: Settings > Sound > Input should show `CABLE Output (VB-Audio Virtual Cable)` and Sound > Output should show `CABLE Input (VB-Audio Virtual Cable)`.
  - How to wire it for meetings: in Zoom / Teams / Meet audio settings, set microphone to `CABLE Output`.
  - Troubleshooting: privacy toggles, 44.1 vs 48 kHz sample-rate mismatches, default-communication-device override, enabling the device after a Windows feature update.
- Extend `scripts/probe_env.py` with a `check_vbcable()` function:
  - Enumerates `sounddevice.query_devices()`.
  - Looks for both `CABLE Input (VB-Audio Virtual Cable)` (output side) and `CABLE Output (VB-Audio Virtual Cable)` (input side) by substring.
  - Reports `PASS` / `MISSING` and the resolved device indices.
  - Absence is a **WARNING**, not a failure, because dictation-only users do not need VB-Cable. The meeting pipeline (TICKET-025) raises a hard error at startup if it cannot find the device; the probe only surfaces the state.
- Store resolved device names in `configs/virtual_mic.toml` so TICKET-021 has a single source of truth. Ship defaults plus a commented override block for users who rename the device.
- Add a thin helper `sabi.output.virtual_mic.resolve_devices() -> VBCableDevices` that reads the config, calls `sounddevice.query_devices()`, and raises `VirtualMicNotInstalledError` with remediation text. TICKET-021 reuses this.
- Add `tests/test_virtual_mic_probe.py` that monkeypatches `sounddevice.query_devices()` with a fake device list containing and not containing VB-Cable to verify both branches of the detection.

## Acceptance criteria

- [ ] `python -m sabi probe` on a machine with VB-Cable installed reports `PASS` with both input and output device indices.
- [ ] On a machine without VB-Cable, the probe prints a yellow WARNING pointing at `docs/INSTALL-VBCABLE.md` and still exits 0.
- [ ] `docs/INSTALL-VBCABLE.md` contains the official download URL, verification steps, and Zoom / Teams / Meet config pointers.
- [ ] `sabi.output.virtual_mic.resolve_devices()` returns the correct `VBCableDevices(input_index, output_index)` on a probed machine and raises `VirtualMicNotInstalledError` with an actionable message otherwise.
- [ ] Unit tests cover both the present and missing branches with monkeypatched device lists.

## Out of scope

- Auto-downloading or silently installing VB-Cable - licensing + admin-privilege concerns, and the user needs a reboot regardless.
- Mac BlackHole integration - the roadmap lists BlackHole for Mac but the PoC is Windows-only.
- Linux PulseAudio virtual sink - the roadmap's risk section calls this out explicitly as "no clean analog" (project_roadmap.md line 224); deferred.
- Switching the user's system default microphone to VB-Cable - we never touch system defaults; we only output into the CABLE Input device. The user sets Zoom / Teams / Meet to use CABLE Output.

## Notes

- Name matching is substring-based because vendor updates sometimes append `(2)` or a version qualifier. Document the exact match rules so TICKET-021 can rely on them.
- Keep the device index cache short-lived. Windows can renumber devices after sleep/wake or after a USB audio device is plugged in; resolve on pipeline start, not once at import time.

## References

- Roadmap Flow 2 one-time setup (project_roadmap.md lines 117-123) - the three user-facing steps this ticket documents and validates.
- Roadmap output layer (project_roadmap.md lines 41-44) - "BlackHole (Mac) or VB-Cable (Windows) virtual mic. Routes into Zoom/Meet/Teams as your voice" is the feature this ticket enables.
- Roadmap risks (project_roadmap.md line 224) - "Cross-platform audio routing. BlackHole is Mac-only, VB-Cable is Windows, Linux has no clean analog" frames our PoC scope.
