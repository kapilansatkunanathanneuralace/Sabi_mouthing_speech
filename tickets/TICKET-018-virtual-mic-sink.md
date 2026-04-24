# TICKET-018 - Virtual mic audio sink routing

Phase: 1 - ML PoC
Epic: Output
Estimate: M
Depends on: TICKET-016, TICKET-017
Status: Not started

## Goal

Ship `sabi.output.virtual_mic.VirtualMicSink` - a thin audio writer that consumes `TTSFrame`s from TICKET-017 and plays them into the VB-Cable virtual input device resolved in TICKET-016. Zoom / Teams / Meet, configured to use `CABLE Output` as their microphone, then hear the synthesized voice. Resamples if needed (Kokoro at 24 kHz, VB-Cable commonly 48 kHz). Exposes a mute bit TICKET-023 can flip in under 1 ms without touching the TTS engine.

## System dependencies

- VB-Cable installed and detected per TICKET-016.
- Windows default audio subsystem; no ASIO required for PoC.

## Python packages

Already installed in TICKET-002:

- `sounddevice`
- `numpy`

New (optional high-quality resampling):

- `soxr==0.5.0` - fast, high-quality resampler. Falls back to a `scipy.signal.resample_poly` or pure-numpy polyphase filter if absent; we keep `soxr` optional so contributors without a C compiler can still run the PoC.

Add to `pyproject.toml` dependencies, with a comment noting the fallback.

## Work

- Create `src/sabi/output/virtual_mic.py`.
- Define `VirtualMicConfig`: resolved input device index (from TICKET-016), output sample rate (auto-detected from the device, typically 48000), block_ms 20, latency preference `"low"`, channels 1, start_muted False.
- Implement `VirtualMicSink`:
  - Context-manager that opens a `sounddevice.OutputStream` targeting the VB-Cable input device.
  - Background consumer thread pulls `TTSFrame`s from an internal thread-safe queue and hands their samples to the stream via callback (preferred) or blocking `write()` (fallback if the callback pattern proves flaky with VB-Cable on Windows).
  - Resamples from the TTS engine rate to the device rate once per `speak()` session; results cached in a float32 buffer to avoid per-frame allocations.
  - `.play_stream(tts_stream: TTSStream) -> PlayResult`:
    - Returns quickly - the caller gets back a `PlayResult` object with `handle`, `started_at_ns`, and an awaitable `.join(timeout=...)` to wait for the stream to finish draining.
    - Captures wall-clock from first-frame-received to first-frame-written-to-device, separate from the TTS TTFB that TICKET-017 measures.
  - `.mute(on: bool)`: flips an `atomic bool`; the consumer thread writes zeros instead of samples while muted. Must complete in under 1 ms - no queue manipulation, no stream reopen.
  - `.drop_queued()`: clears the internal queue without stopping the stream - used by TICKET-023 if the user hits mute mid-utterance to prevent buffered audio from leaking out on unmute.
- Write `scripts/virtual_mic_smoke.py`: builds a 1-second 440 Hz sine, wraps it in synthetic `TTSFrame`s, writes to the sink. User can listen via `Listen to this device` on CABLE Output to verify. Also records a simultaneous capture from `CABLE Output` to `reports/vmic_smoke.wav` to prove round-trip.
- CLI shortcut: `python -m sabi vmic-smoke`.
- `tests/test_virtual_mic_sink.py` uses a fake `sounddevice.OutputStream` that writes samples into a numpy buffer in memory to verify: resampling produces expected length, mute fills zeros, drop_queued empties correctly, lifecycle closes cleanly. No real audio hardware touched.

## Acceptance criteria

- [ ] `python -m sabi vmic-smoke` plays a 1-second 440 Hz sine through VB-Cable; `reports/vmic_smoke.wav` captured from `CABLE Output` shows a clear sine wave with < 1 % RMS noise floor.
- [ ] Synth -> device handoff latency (first TTSFrame into queue -> first frame written to OutputStream) logged per run, target < 30 ms.
- [ ] `.mute(True)` flips on within 1 ms of the call; captured `CABLE Output` audio goes to silence in under 20 ms (one block).
- [ ] Resampling 24 kHz Kokoro frames to 48 kHz device rate produces no audible artifacts on the smoke clip; spectrum peaks at 440 Hz as expected.
- [ ] Without VB-Cable installed, `VirtualMicSink.__enter__` raises `VirtualMicNotInstalledError` (reused from TICKET-016) with a remediation message pointing to `docs/INSTALL-VBCABLE.md`.
- [ ] Unit tests pass without any real audio hardware.

## Out of scope

- Parallel output to a speaker so the user can self-monitor - users who want sidetone turn on Windows "Listen to this device". Not a PoC feature.
- ASIO or low-latency driver support - VB-Cable + WASAPI is good enough for PoC budgets.
- Multi-channel spatial audio - mono only.
- Loopback capture / meeting recording - not our problem.

## Notes

- VB-Cable's default sample rate is 48 kHz; if the user has changed it in Windows Sound Control Panel to 44.1 kHz we match whatever the device reports - do not force 48 kHz.
- Keep a small internal queue (a few blocks). Larger buffers add perceptible lag, which users will hear as "I can't talk normally" in a call.

## References

- Roadmap Flow 2 step 6 (project_roadmap.md line 132) - "Audio routed to virtual mic < 20 ms" is the latency budget this ticket owns.
- Roadmap output layer (project_roadmap.md lines 41-44) - defines virtual mic as the meeting output.
- Roadmap Flow 2 UX note (project_roadmap.md line 140) - "Mute/unmute toggle must be instant - never block the meeting mic behind the pipeline." The `mute()` contract here is what TICKET-023 depends on.
