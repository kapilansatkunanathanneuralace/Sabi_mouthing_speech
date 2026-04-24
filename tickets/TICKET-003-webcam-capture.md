# TICKET-003 - Webcam capture module

Phase: 1 - ML PoC
Epic: Capture
Estimate: M
Depends on: TICKET-002
Status: Not started

## Goal

Ship `sabi.capture.webcam` - a background-threaded webcam reader that produces RGB frames at a target 25 fps, drops old frames under backpressure, and exposes both a pull API (`get_latest()`) and an iterator API (`frames()`) for downstream consumers (lip ROI detector in TICKET-004, pipeline in TICKET-011). This isolates OpenCV I/O from everything else so the VSR path is not blocked on camera stalls.

## System dependencies

- A webcam visible to Windows at index 0 (or configurable).
- Windows Privacy > Camera must be enabled for desktop apps. Documented in `docs/INSTALL.md`.

## Python packages

Already installed in TICKET-002:

- `opencv-python`
- `numpy`
- `rich` (for the debug viewer overlay text)

No new additions.

## Work

- Create `src/sabi/capture/__init__.py` and `src/sabi/capture/webcam.py`.
- Define a pydantic `WebcamConfig` (device index, target fps, requested width/height, mirror flag, buffer size).
- Implement `WebcamSource`:
  - Opens `cv2.VideoCapture` with DSHOW backend on Windows (`cv2.CAP_DSHOW`) to avoid the slow default MSMF open.
  - Requests 25 fps, 1280x720 (or config value), converts BGR -> RGB on the capture thread.
  - Runs a background `threading.Thread` that writes into a bounded `collections.deque(maxlen=buffer_size)` - old frames are discarded, not queued up.
  - `get_latest(timeout=...)` returns the most recent `(timestamp_ns, frame_rgb)` tuple or raises on timeout.
  - `frames()` is a generator yielding `(timestamp_ns, frame_rgb)` pairs; if the consumer is slow, it skips to latest rather than backing up.
  - Context-manager protocol (`__enter__` / `__exit__`) that opens the device and joins the thread cleanly.
- Track and expose a `FrameStats` object: captured count, dropped count, measured fps (EWMA over last 2 s), last frame timestamp. The overlay UI will read these in TICKET-013.
- Write `scripts/webcam_viewer.py` (dev-only): opens the source, shows an OpenCV window with FPS + dropped-frame count burned in via `cv2.putText`. Press `q` to quit. This doubles as a debug tool and as a fixture check.
- Add a CLI shortcut: `python -m sabi cam-preview` invokes the script.

## Acceptance criteria

- [ ] `python -m sabi cam-preview` opens a window showing the live camera within 1 s on a reference laptop.
- [ ] Measured fps printed in the overlay stays within +/- 2 fps of the 25 fps target under no load.
- [ ] Stopping the consumer thread for 1 s does not raise in the capture thread - dropped-frame counter increments instead.
- [ ] `WebcamSource` used as a context manager releases the device (verified by successfully reopening in the same process).
- [ ] Unit test `tests/test_webcam_source.py` uses a monkeypatched fake `cv2.VideoCapture` to assert: ring-buffer drops oldest, `get_latest()` returns newest, thread joins on `__exit__`.
- [ ] With the camera disabled in Windows privacy settings, `WebcamSource.__enter__` raises a `WebcamUnavailableError` with a clear remediation message.

## Out of scope

- Face / lip detection - TICKET-004.
- Multi-camera selection UI - the device index is config-driven for now.
- Recording to disk - the eval harness (TICKET-014) handles saved clips separately.
- HDR / exposure tuning - we accept default auto-exposure.

## Notes

- Use `cv2.CAP_PROP_BUFFERSIZE = 1` after opening to keep the driver queue short; this measurably cuts end-to-end lip-read latency.
- On Windows with DSHOW, calling `VideoCapture.set(cv2.CAP_PROP_FRAME_WIDTH, ...)` before `.set(cv2.CAP_PROP_FPS, 25)` is the order that actually sticks.

## References

- Roadmap input layer (project_roadmap.md lines 13-18) - defines 25 fps webcam + 256 px full-frame constraints this module honors.
- Roadmap Flow 1 step 2 (project_roadmap.md line 83) - "Webcam streams lip crop at 25 fps" is the budget line this ticket owns.
