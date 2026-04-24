# TICKET-004 - Lip / mouth ROI detector

Phase: 1 - ML PoC
Epic: Capture
Estimate: M
Depends on: TICKET-003
Status: Not started

## Goal

Given a stream of RGB frames from `WebcamSource`, emit a stream of `96x96` grayscale mouth crops aligned to the Auto-AVSR training distribution (so Chaplin's predictions are not garbage because of our crop conventions). On frames where no face is detected, emit `None` - the pipeline uses that to "fail silently rather than emit garbage text" as called out in the roadmap.

## System dependencies

- None beyond what TICKET-002 installs. MediaPipe ships its own face landmarker model inside the wheel; no separate download.

## Python packages

Already installed in TICKET-002:

- `mediapipe`
- `opencv-python`
- `numpy`

No additions.

## Work

- Create `src/sabi/capture/lip_roi.py`.
- Define `LipROIConfig` (target size default 96, target fps 25, smoothing alpha for bbox EWMA, grayscale output flag, max missing-face streak before emitting a hard `None` sentinel).
- Implement `LipROIDetector`:
  - Wraps `mediapipe.solutions.face_mesh.FaceMesh` in `refine_landmarks=True, max_num_faces=1, min_detection_confidence=0.5, min_tracking_confidence=0.5` mode so we get the inner-mouth landmarks (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291 for outer lips; 78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308 for inner - full list documented in the file).
  - Converts RGB -> OpenCV's internal format via the mediapipe Image adapter.
  - Computes the tight lip bounding box from landmarks, expands by 40% on each side (Auto-AVSR convention), aligns to the mouth-center line.
  - EWMA-smooths the bbox center and size across frames to stop jitter-driven crops from shifting every frame.
  - Resizes crop to 96x96, converts to grayscale (keeps option for RGB if Chaplin variant requires it).
  - Returns a `LipFrame` dataclass: `timestamp_ns`, `crop` (numpy uint8), `confidence` (mediapipe detection score), `face_present` (bool).
- Provide a `.process_stream(iterator)` generator wrapping `WebcamSource.frames()`.
- When more than `max_missing_streak` frames in a row have no face, log once at WARNING ("camera no longer sees a face") and emit a single `None` - downstream code treats that as "abort this utterance".
- Write `scripts/lip_roi_debug.py` that opens the webcam + detector and shows the original frame with the lip bbox overlaid plus a 96x96 crop preview in the corner.
- CLI shortcut: `python -m sabi lip-preview`.

## Acceptance criteria

- [ ] `python -m sabi lip-preview` renders the live lip crop next to the raw frame at close to 25 fps on the reference laptop (acceptable floor: 20 fps).
- [ ] With the user deliberately looking away, the detector emits `None` within `max_missing_streak` frames and recovers once the face returns.
- [ ] `scripts/lip_roi_debug.py` saves a single labeled crop frame to `data/samples/lip_sample.png` on `s` keypress (used by TICKET-005's integration smoke test).
- [ ] Unit test `tests/test_lip_roi.py` feeds in a small fixture image with a known face (or a synthetic one via mediapipe's test assets) and asserts the returned crop is exactly 96x96, uint8, contiguous.
- [ ] Bounding-box jitter (std-dev of center position across 60 static frames) is lower than the raw un-smoothed version by at least 50% - assert in a test using a fixed recorded video under `data/fixtures/`.

## Out of scope

- Multi-face handling - PoC assumes one user in frame.
- Lighting normalization / histogram equalization - we'll evaluate need in TICKET-014.
- Full face-mesh output or gaze estimation - Tier 4 roadmap item, not PoC.
- Swapping mediapipe for a different landmarker - not needed unless eval flags accuracy.

## Notes

- Auto-AVSR's LRS3 preprocessing uses a 96x96 mouth crop in grayscale with a specific mean/std normalization. The preprocessing spec this detector targets is documented inline in `lip_roi.py` so that TICKET-005's wrapper can apply the final normalization in one place without ambiguity.
- MediaPipe's face mesh is CPU-only but runs in a few ms per frame on modern laptops; no GPU dependency here.

## References

- Roadmap Flow 1 steps 2-3 (project_roadmap.md lines 83-84) - webcam 25 fps + "Lip detection isolates mouth region ~10 ms" budget.
- Roadmap UX note (project_roadmap.md line 93) - "If camera can't see the mouth (occluded, looking away), fail silently rather than emit garbage text" is implemented here.
- Auto-AVSR lip preprocessing convention (upstream repo referenced from TICKET-005).
