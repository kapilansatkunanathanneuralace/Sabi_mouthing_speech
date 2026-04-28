# TICKET-023 - Virtual mic audio sink routing

Phase: 1 - ML PoC
Epic: Output
Estimate: M
Depends on: TICKET-021, TICKET-022
Status: Not started

## Goal

Ship `sabi.output.virtual_mic.VirtualMicSink`, a thin audio writer that consumes `TTSFrame`s from TICKET-022 and plays them into the VB-Cable virtual input device resolved in TICKET-021. Zoom / Teams / Meet, configured to use `CABLE Output` as their microphone, then hear the synthesized voice.

## System dependencies

- VB-Cable installed and detected per TICKET-021.
- Windows default audio subsystem.

## Python packages

Already installed:

- `sounddevice`
- `numpy`

New optional dependency:

- `soxr` for high-quality resampling, with fallback if absent.

## Work

- Create `src/sabi/output/virtual_mic.py`.
- Define `VirtualMicConfig`.
- Implement `VirtualMicSink`:
  - Opens a `sounddevice.OutputStream` targeting the VB-Cable input device.
  - Consumes `TTSFrame`s from a small thread-safe queue.
  - Resamples TTS output to the device rate.
  - Provides `.play_stream()`, `.mute(on: bool)`, and `.drop_queued()`.
- Add `python -m sabi vmic-smoke` to play and capture a 1-second test tone.
- Add `tests/test_virtual_mic_sink.py` with fake `sounddevice.OutputStream`.

## Acceptance criteria

- [ ] `python -m sabi vmic-smoke` plays a 1-second 440 Hz sine through VB-Cable and captures `reports/vmic_smoke.wav`.
- [ ] Synth-to-device handoff latency is logged with target < 30 ms.
- [ ] `.mute(True)` flips within 1 ms and output goes silent within one audio block.
- [ ] Resampling produces a clean 440 Hz smoke clip.
- [ ] Without VB-Cable installed, startup raises `VirtualMicNotInstalledError` pointing to `docs/INSTALL-VBCABLE.md`.
- [ ] Unit tests pass without real audio hardware.

## Out of scope

- Speaker sidetone.
- ASIO or low-latency driver support.
- Multi-channel audio.
- Loopback capture / meeting recording beyond the smoke test.

## Notes

- Match whatever sample rate the VB-Cable device reports.
- Keep the internal queue small to avoid perceptible lag.

## References

- Roadmap Flow 2 step 6 (project_roadmap.md line 132).
- Roadmap output layer (project_roadmap.md lines 41-44).
- Roadmap Flow 2 UX note (project_roadmap.md line 140).
