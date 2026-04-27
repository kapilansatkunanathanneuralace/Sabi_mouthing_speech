# TICKET-017 - Fused dictation pipeline (PoC-3)

Phase: 2 - Fusion & polish (injected ahead of meeting track per priority reorder)
Epic: Pipeline
Estimate: L
Depends on: TICKET-016, TICKET-005, TICKET-007, TICKET-008, TICKET-009, TICKET-010, TICKET-011, TICKET-012
Status: Done

## Goal

Wire TICKET-003 (webcam) + TICKET-004 (lip ROI) + TICKET-005 (VSR) + TICKET-006 (mic + VAD) + TICKET-007 (ASR) + TICKET-016 (fusion combiner) + TICKET-008 (cleanup) + TICKET-009 (paste) + TICKET-010 (hotkey) into a third dictation pipeline that runs **VSR and ASR in parallel** and pastes the **fused** output. Exposes `python -m sabi fused-dictate`. Uses the same DI seam (`_Deps`) and JSONL conventions as TICKET-011 / TICKET-012 so the eval harness (TICKET-014) can treat the three pipelines interchangeably.

## System dependencies

All inherited from the upstream tickets: working webcam, working mic, CUDA strongly recommended (we run two model forwards per utterance, so GPU vs CPU matters double here), Ollama optional but recommended.

## Python packages

No new dependencies. `concurrent.futures` is stdlib; everything else (`torch`, `faster-whisper`, `mediapipe`, `opencv-python`, etc.) is already pinned by TICKET-002 / TICKET-005 / TICKET-007.

## Work

- Create `src/sabi/pipelines/fused_dictate.py`.
- Define `FusedDictateConfig` composing `WebcamConfig`, `LipROIConfig`, `VSRModelConfig`, `MicConfig`, `ASRModelConfig`, `FusionConfig` (TICKET-016), `CleanupConfig`, `InjectConfig`, `HotkeyConfig`. Single `configs/fused_dictate.toml` overlays the defaults.
- Add a top-level `[pipeline]` section in the TOML for pipeline-only knobs:
  - `parallel = true` - run VSR and ASR concurrently (default). When `false`, run VSR then ASR serially - useful for low-VRAM debugging.
  - `paste_floor_confidence = 0.4` - floor on the **fused** confidence below which paste is withheld pending F12 (mirrors TICKET-011/012).
  - `force_paste_binding = "f12"` and `force_paste_mode_fused = "listener"` - same three-mode semantics as TICKET-012.
  - `keep_camera_open = false` and `keep_mic_open = true` - matches TICKET-011's per-trigger camera lifecycle and TICKET-012's preopen mic lifecycle by default. Both are flippable.
- Implement `FusedDictatePipeline`:
  - On construction (`__enter__`): instantiates each component, calls `VSRModel.warm_up()`, `ASRModel.warm_up()`, `TextCleaner.is_available()`, registers hotkey callbacks. Camera stays closed; mic preopens by default.
  - `_Deps` dataclass mirrors the silent / audio pipelines so `tests/test_fused_dictate.py` can inject fakes for every IO module without touching real hardware.
  - `on_trigger_start(TriggerEvent)`:
    - Opens `WebcamSource` (per-trigger by default; `keep_camera_open=true` skips reopen).
    - Spawns a webcam worker thread that pulls frames -> `LipROIDetector` -> in-memory frame buffer.
    - Begins mic capture - either calls `MicrophoneSource.push_to_talk_segment(start_event, end_event)` on a worker thread (PTT mode is the only supported trigger mode for fused-dictate v1; VAD is deferred since concurrent video buffering plus VAD-segmented audio adds significant complexity, see Out of scope).
    - Records `trigger_start_ns`.
  - `on_trigger_stop(TriggerEvent)`:
    - Signals end_event for both capture threads, joins them.
    - Submits VSR + ASR work to a `concurrent.futures.ThreadPoolExecutor(max_workers=2)`:
      - `vsr_future = pool.submit(vsr.predict, lip_buffer)`
      - `asr_future = pool.submit(asr.transcribe, mic_utterance)`
    - Waits on both with `concurrent.futures.wait([vsr_future, asr_future], return_when=ALL_COMPLETED, timeout=pipeline.predict_timeout_ms / 1000)`.
    - Captures wall-clock per branch by stamping inside the worker (each future returns `(result, branch_latency_ms)`); `vsr_ms` / `asr_ms` are wall-clock from submit-to-result, captured outside the worker as a sanity check.
    - Calls `FusionCombiner.combine(asr_result, vsr_result)` -> `FusedResult`.
    - Feeds `FusedResult.text` into `TextCleaner.cleanup(..., CleanupContext(source="fused", focused_app=None, register_hint="dictation"))` -> `CleanedText`.
    - Calls `paste_text(cleaned.text)` (with the dry-run flag honored).
    - Emits a structured `UtteranceProcessed` event with `pipeline="fused"` and the `latencies` dict below.
  - Degraded paths (logged in `mode_reason` on the `FusedResult` and in the JSONL):
    - VSR aborts (no face / lip ROI returns `None` for >= 60% of frames): pass `vsr_result=None` to fusion; combiner returns ASR verbatim with `mode_used="audio_primary"`, `mode_reason="vsr no-face"`. Pipeline still pastes.
    - Mic returns silence (peak dBFS below `mic.silence_dbfs`): pass `asr_result=None`; combiner returns VSR verbatim with `mode_reason="asr silent"`. Pipeline still pastes.
    - Both empty (no face AND silence): abort paste with `pipeline_error: "neither modality captured input"`, same fail-silent rule as TICKET-011.
    - Confidence floor (`pipeline.paste_floor_confidence`) checks `FusedResult.confidence`. Below floor + `force_paste_mode_fused="listener"` -> withhold paste pending F12 within 1.5 s, exactly like TICKET-012.
- Stage-timing contract:
  - `latencies = {"capture_ms", "roi_ms", "vsr_ms", "asr_ms", "fusion_ms", "cleanup_ms", "inject_ms", "warmup_ms", "capture_open_ms", "mic_open_ms", "total_ms"}`.
  - `capture_ms` is `trigger_stop_ns - trigger_start_ns`.
  - `vsr_ms` and `asr_ms` are each branch's wall-clock around the model call (parallel, so `total_ms`'s ML window is approximately `max(vsr_ms, asr_ms)`).
  - `fusion_ms` is the combiner's `latency_ms` from TICKET-016's `FusedResult`.
  - `total_ms` is `paste_completed_ns - trigger_stop_ns`.
- JSONL schema: `reports/fused_dictate_<date>.jsonl`. Same envelope as silent/audio dictate plus a nested `fusion` block:
  - `fusion.mode_used`, `fusion.mode_reason`, `fusion.source_weights`, `fusion.per_word_origin`, `fusion.confidence`, `fusion.aligned_ratio` (if exposed - TICKET-016 may want to add this to `FusedResult`; coordinate before merge).
  - `asr.confidence`, `asr.text` (raw, pre-fusion), `asr.latency_ms`.
  - `vsr.confidence`, `vsr.text` (raw, pre-fusion), `vsr.latency_ms`.
- Latency log: `_finalize` calls `append_latency_row("TICKET-017", ...)` once per processed utterance with the `latencies` dict.
- CLI: register `python -m sabi fused-dictate` in `src/sabi/cli.py` with the same flag surface as `silent-dictate` plus `--mode auto|audio_primary|vsr_primary` (overrides `[fusion].mode`) and `--no-parallel` (forces serial VSR-then-ASR).
- Update [`src/sabi/eval/harness.py`](src/sabi/eval/harness.py) (specified in TICKET-014) to add a `FusedOfflineRunner(video_path, audio_path)` so the eval harness can replay clip + wav pairs through the fused pipeline. If TICKET-014 is not yet implemented when this ticket is picked up, leave a clearly-marked TODO + interface stub in the same module so TICKET-014 only needs to wire it in.
- Tests in `tests/test_fused_dictate.py`:
  - `FakeWebcam`, `FakeROI`, `FakeVSR`, `FakeMic`, `FakeASR`, `FakeCombiner` (passes through canned `FusedResult`), `FakeCleaner`, `FakePaste`, `FakeHotkey`.
  - Cases:
    - Happy path (both sources non-empty, both confident): pastes the fused text, emits `decision="pasted"`, `pipeline="fused"`, all 11 latency keys present.
    - VSR aborts (FakeROI returns `None` for 80% of frames): pastes ASR verbatim, `fusion.mode_reason="vsr no-face"`.
    - ASR silent (FakeMic yields zero-amp samples): pastes VSR verbatim, `fusion.mode_reason="asr silent"`.
    - Both empty: pipeline emits `pipeline_error`, no paste.
    - Below confidence floor with default `listener` mode: paste withheld, `force_paste_hit` event after F12.
    - `--no-parallel` config: asserts ASR runs after VSR via call-order observation on the fakes; total_ms approximately equals vsr_ms + asr_ms within 10 ms.
    - Ollama bypass: cleaned text equals fused text, `used_fallback=True`, paste still happens.
    - JSONL schema: every row includes the nested `fusion`, `asr`, `vsr` blocks with the documented fields.

## Acceptance criteria

- [x] `python -m sabi fused-dictate --help` renders the full flag surface without crashing on a machine that passes `python -m sabi probe`.
- [x] Holding the hotkey while mouthing **and** speaking a short phrase ("hello world") into camera + mic produces pasted text in the focused app within 600 ms on the reference GPU laptop (looser than the dictation-only 500 ms because we pay both ML stacks).
- [x] With Ollama stopped, the pipeline still pastes - cleanup falls back per TICKET-008.
- [x] With the camera occluded but mic working, the pipeline pastes the ASR transcript and the JSONL records `fusion.mode_reason="vsr no-face"`.
- [x] With the user mouthing silently (camera working, mic silent), the pipeline pastes the VSR transcript and the JSONL records `fusion.mode_reason="asr silent"`.
- [x] With both modalities empty, no paste happens and the JSONL records a `pipeline_error` row.
- [x] `reports/fused_dictate_<date>.jsonl` accumulates one JSON object per processed utterance with the full `latencies` dict and the nested `fusion` / `asr` / `vsr` blocks.
- [x] `reports/latency-log.md` gets one row per smoke run with `ticket=TICKET-017`.
- [x] All cases in `tests/test_fused_dictate.py` pass with hardware mocked; full suite stays under the existing 10 s ceiling.
- [x] When TICKET-014 lands, `python -m sabi eval --pipelines fused` produces a per-phrase WER + latency table for the fused pipeline.

## Out of scope

- VAD-mode trigger for fused dictation - PoC supports PTT only. Adding VAD requires a unified buffering model for video + segmented audio, which is its own ticket if the eval harness shows VAD is meaningfully better than PTT.
- Streaming partial hypotheses to the overlay - TICKET-013 mirrors completed utterances; streaming partials remain a Phase 2+ optimization tracked outside this ticket.
- Per-word streaming fusion - the combiner is one-shot per utterance.
- Voice cloning / TTS / virtual mic / meeting mode - this is a dictation pipeline, not a meeting pipeline.
- App-aware fusion-mode overrides - `CleanupContext.focused_app` is plumbed but unused; defer to after the foreground watcher (renumbered TICKET-023) ships.

## Notes

- The PTT model is non-negotiable for v1: VSR needs a clean utterance boundary, and gluing VAD-segmented audio onto webcam frame ranges adds a class of edge cases (utterance straddling silence boundaries) that we do not need to solve for the PoC.
- Run VSR and ASR on the **same** GPU when CUDA is available. Both models are small enough to coexist; if VRAM becomes a problem on lower-end cards, the `--no-parallel` flag is the escape hatch.
- Keep the camera lifecycle parallel to TICKET-011 (per-trigger by default, privacy-safe LED behavior). The mic lifecycle parallels TICKET-012 (preopen by default to avoid first-utterance open cost). Both knobs are config-driven and tested.

## References

- Roadmap fusion layer (project_roadmap.md lines 30-39) - decision matrix the pipeline implements via `FusionCombiner`.
- Roadmap Phase 2 (project_roadmap.md lines 179-184) - "Audio-visual fusion live (confidence-weighted ASR + VSR)" is the deliverable.
- TICKET-011 (`tickets/TICKET-011-silent-dictation-pipeline.md`) - silent pipeline this one mirrors structurally.
- TICKET-012 (`tickets/TICKET-012-audio-dictation-pipeline.md`) - audio pipeline this one mirrors structurally.
- TICKET-016 (`tickets/TICKET-016-fusion-module.md`) - the combiner this pipeline orchestrates around.
