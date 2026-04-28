# TICKET-021 - Virtual mic install integration (VB-Cable)

Phase: 1 - ML PoC
Epic: Infra
Estimate: S
Depends on: TICKET-002
Status: Not started

## Goal

Make VB-Cable a known, detected, and documented prerequisite of the meeting-mode path. Extend `scripts/probe_env.py` so it reports whether a VB-Cable-compatible virtual audio device is present under the names we expect, and write `docs/INSTALL-VBCABLE.md` with the one-time user-facing steps from the roadmap's "one-time setup" block. No auto-install - we do not ship the driver, we tell the user exactly how to install it and verify it.

## System dependencies

- **VB-Audio Virtual Cable** (free, donationware) from https://vb-audio.com/Cable/. The standard version is sufficient for PoC.
- On Windows 10/11 the installer requires a reboot for the driver to register.
- No Mac/Linux analogue shipped in this PoC.

## Python packages

Already installed in TICKET-002:

- `sounddevice` - used to enumerate devices and verify VB-Cable is present by name.
- `rich` - for the probe output.

No additions.

## Work

- Write `docs/INSTALL-VBCABLE.md` with download, install, reboot, verification, and Zoom / Teams / Meet setup steps.
- Extend `scripts/probe_env.py` with `check_vbcable()`:
  - Enumerates `sounddevice.query_devices()`.
  - Looks for `CABLE Input (VB-Audio Virtual Cable)` and `CABLE Output (VB-Audio Virtual Cable)` by substring.
  - Reports `PASS` / `MISSING` and resolved device indices.
  - Missing VB-Cable is a warning, not a probe failure, because dictation-only users do not need it.
- Store resolved device-name defaults in `configs/virtual_mic.toml` so TICKET-023 has one source of truth.
- Add `sabi.output.virtual_mic.resolve_devices() -> VBCableDevices`.
- Add `tests/test_virtual_mic_probe.py` covering present and missing device lists.

## Acceptance criteria

- [ ] `python -m sabi probe` on a machine with VB-Cable installed reports `PASS` with both input and output device indices.
- [ ] On a machine without VB-Cable, the probe prints a yellow warning pointing at `docs/INSTALL-VBCABLE.md` and still exits 0.
- [ ] `docs/INSTALL-VBCABLE.md` contains the official download URL, verification steps, and meeting-client config pointers.
- [ ] `sabi.output.virtual_mic.resolve_devices()` returns `VBCableDevices(input_index, output_index)` or raises `VirtualMicNotInstalledError` with remediation.
- [ ] Unit tests cover present and missing branches with monkeypatched device lists.

## Out of scope

- Auto-downloading or silently installing VB-Cable.
- Mac BlackHole integration.
- Linux PulseAudio virtual sink.
- Switching the user's system default microphone.

## Notes

- Name matching is substring-based because vendor updates sometimes append `(2)` or a version qualifier.
- Resolve device indices on pipeline start; Windows can renumber devices after sleep/wake.

## References

- Roadmap Flow 2 one-time setup (project_roadmap.md lines 117-123).
- Roadmap output layer (project_roadmap.md lines 41-44).
- Roadmap risks (project_roadmap.md line 224).
