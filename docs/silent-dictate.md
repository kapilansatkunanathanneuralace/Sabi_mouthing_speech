# Silent dictation pipeline (TICKET-011)

`python -m sabi silent-dictate` wires the webcam (TICKET-003), lip ROI
(TICKET-004), Chaplin VSR (TICKET-005), Ollama cleanup (TICKET-008),
clipboard paste (TICKET-009), and hotkey trigger (TICKET-010) into a
single PoC you can demo on the dev laptop. This doc covers the
end-to-end flow, tunables, latency budget, and the JSONL schema that
TICKET-014 (eval) will consume.

## Flow

1. Hold the configured chord (default **Ctrl+Alt+Space**). The pipeline
   opens the webcam only after the hotkey fires, so the camera LED
   stays off while you are idle.
2. Frames flow through `LipROIDetector` into an in-memory buffer; the
   face-present ratio and per-ROI latency are tracked for gating.
3. Release the chord. Capture stops, VSR runs on the captured crops,
   then Ollama cleanup polishes the text (filler removal / punctuation
   / casing).
4. If the result clears the gates, `paste_text` (TICKET-009) fires
   Ctrl+V into the focused window and restores the prior clipboard on
   a background thread.

## Gates

- **Empty capture**: `frame_count == 0` -> `decision=withheld_empty`,
  no paste.
- **Occlusion**: if fewer than `occlusion_threshold` (default 60 %) of
  captured frames contain a detected face, paste is withheld and the
  pipeline logs `ERROR: camera could not see your mouth; nothing
  pasted`.
- **Confidence + force paste**: when `VSRResult.confidence <
  confidence_floor` (default 0.35), the cleaned text is stashed for
  `force_paste_window_ms` (default 1.5 s). Press the
  `force_paste_binding` (default **F12**) within the window to paste
  anyway. The force-paste controller is a second
  `HotkeyController` instance listening on its own chord, so it never
  collides with the primary trigger.
  - `force_paste_mode = "always"` - ignore the floor and always paste.
  - `force_paste_mode = "never"` - never wait for F12; always discard
    low-confidence utterances.
  - `force_paste_mode = "listener"` (default) - wait for the F12 tap.

## CLI

```powershell
python -m sabi silent-dictate [--config PATH]
                              [--dry-run]
                              [--force-cpu]
                              [--keep-camera-open]
                              [--binding CHORD]
                              [--force-paste-binding CHORD]
                              [--confidence-floor FLOAT]
                              [--force-paste listener|always|never]
```

- `--dry-run` prints the cleaned text to stdout instead of pasting
  (also flips `InjectConfig.dry_run` so Ctrl+V never fires).
- `--force-cpu` forces VSR to CPU for smoke tests on machines without
  CUDA.
- `--keep-camera-open` keeps the webcam hot between utterances
  (`capture_open_ms == 0`); trades privacy (LED stays on) for
  per-trigger latency.
- `--binding` overrides the primary chord; must **not** equal
  `--force-paste-binding`.

`scripts/silent_dictate.py` is an argparse shim with the same flags
for machines where the `sabi` console entry point is not installed.

## Latency contract

Every utterance logs a row to `reports/latency-log.md` via
`append_latency_row("TICKET-011", ..., "pipeline", total_ms, 1, notes)`.
The accompanying JSONL line carries the full `latencies` dict:

| key               | meaning |
| ----------------- | ------- |
| `capture_open_ms` | `WebcamSource.__enter__` + first-frame block. Separate from the 500 ms per-utterance budget because Windows DirectShow first-open runs 500-1500 ms. Zero when `keep_camera_open=true`. |
| `capture_ms`      | wall time between first and last captured frame (not total trigger hold; excludes the ROI queue). |
| `roi_ms`          | cumulative `LipROIDetector.process_frame` time during capture. |
| `vsr_ms`          | `VSRModel.predict` latency (from `VSRResult.latency_ms`). |
| `cleanup_ms`      | `TextCleaner.cleanup` latency; 0 when Ollama bypasses. |
| `inject_ms`       | `paste_text` latency. |
| `total_ms`        | `on_trigger_stop` to paste-decision, perf-counter based. |

The roadmap 300-400 ms budget applies to `capture_ms + roi_ms + vsr_ms
+ cleanup_ms + inject_ms`. `capture_open_ms` is reported separately so
the Windows open cost is visible but not attributed to VSR.

## JSONL schema (`reports/silent_dictate_YYYYMMDD.jsonl`)

One JSON object per line, append-only. The date is derived from the
event's start (`time.monotonic()` based); an utterance that spans
midnight stays in the file it started in.

| `event_type`          | fields |
| --------------------- | ------ |
| `trigger_start`       | `utterance_id`, `ts_ns`, `trigger_id`, `mode`, `reason` |
| `trigger_stop`        | `utterance_id`, `ts_ns`, `trigger_id`, `frame_count`, `face_present`, `face_missing` |
| `force_paste_hit`     | `utterance_id`, `ts_ns`, `trigger_id`, `text_final` |
| `utterance_processed` | full `UtteranceProcessed` dump: `text_raw`, `text_final`, `confidence`, `used_fallback`, `decision`, `latencies`, `frame_count`, `face_present_ratio`, `error` |
| `pipeline_error`      | `utterance_id`, `ts_ns`, `reason` (used when the webcam fails to open, etc.) |

Exactly one `utterance_processed` is emitted per utterance. With
`force_paste_mode="listener"`, a low-confidence utterance emits
`force_paste_hit` *before* `utterance_processed` (`decision=force_pasted`).

## Overlay hook (TICKET-013 preview)

`SilentDictatePipeline.subscribe(callback)` registers a function that
receives every `UtteranceProcessed`. TICKET-013's overlay will
subscribe here to render the status (recording / withheld / pasted).
Subscribers run on the dispatch worker thread - do not block inside
them.

## Caveats

- Opening a DirectShow camera per trigger is 500-1500 ms on Windows.
  The CLI logs this as `capture_open_ms`; if it dominates your
  latency, enable `keep_camera_open=true` in `configs/silent_dictate.toml`
  (or pass `--keep-camera-open`). Privacy trade-off: the camera LED
  stays on for the whole session.
- Ollama cold start is ~1-3 s on first utterance because the 2 GB
  llama3.2 model loads into VRAM. The pipeline correctly bypasses and
  returns raw VSR text, but the first utterance will show
  `used_fallback=true`. Warm the model once at startup
  (`ollama run llama3.2:3b-instruct-q4_K_M < NUL`) if you want
  cleanup to hit on the very first press.
- The `keyboard` library cannot register two `add_hotkey` callbacks
  on the same chord (TICKET-010 notes); `SilentDictateConfig` rejects
  configs where `hotkey.binding == force_paste_binding` so you get a
  clear error instead of silent callback loss.
- `paste_text` uses `pyautogui.hotkey("ctrl", "v")`. Slack Desktop
  needs `paste_delay_ms >= 15` (see `docs/paste-injection.md`); the
  pipeline's default `InjectConfig` already matches.
