# TICKET-012 - Audio-dictation pipeline (PoC-2 baseline)

Phase: 1 - ML PoC
Epic: Pipeline
Estimate: M
Depends on: TICKET-006, TICKET-007, TICKET-008, TICKET-009, TICKET-010
Status: Done

## Goal

Wire TICKET-006 (mic + VAD) + TICKET-007 (faster-whisper) + TICKET-008 (cleanup) + TICKET-009 (paste) + TICKET-010 (hotkey) into a working **spoken dictation** pipeline. Exposes `python -m sabi dictate`. This is the A/B baseline for the silent pipeline: we want like-for-like latency and quality numbers so TICKET-014's eval harness can draw a defensible comparison.

## System dependencies

All inherited from the tickets above. No webcam required for this pipeline.

## Python packages

No new dependencies; everything is already pinned.

## Work

- Create `src/sabi/pipelines/audio_dictate.py`.
- Define `AudioDictateConfig` composing `MicConfig`, `ASRModelConfig`, `CleanupConfig`, `InjectConfig`, `HotkeyConfig`. Single `configs/audio_dictate.toml` overlays the defaults.
- Implement `AudioDictatePipeline`:
  - On construction: instantiates components, warms up the ASR model via `ASRModel.warm_up()` and Ollama via `TextCleaner.is_available()`. Does not open the mic yet.
  - Supports two capture modes via config:
    - `trigger_mode = "push_to_talk"`: mic opens on `on_trigger_start`, records until `on_trigger_stop`, bypasses VAD and always emits the full held segment.
    - `trigger_mode = "vad"`: mic runs continuously after one-time hotkey activation, VAD segments into utterances, each utterance goes through the rest of the pipeline. Pressing the hotkey a second time deactivates the pipeline (not just the current utterance).
  - On each complete utterance: `ASRModel.transcribe` -> `TextCleaner.cleanup` -> `paste_text`. Emits `UtteranceProcessed` with the same shape as TICKET-011 but a different `pipeline="audio"` tag.
  - Confidence floor handling: if `ASRResult.confidence` is below a configurable threshold (default 0.4, tuned in eval), the overlay shows the raw text but withholds paste unless user confirms with F12 - matches the VSR pipeline's "cancel bad output before paste" UX.
- Stage-timing contract: `latencies = {"capture_ms": ..., "vad_ms": ..., "asr_ms": ..., "cleanup_ms": ..., "inject_ms": ..., "total_ms": ...}`. `"capture_ms"` is trigger-stop minus first-voiced-frame for fair comparison with the silent pipeline's `"capture_ms"`.
- Structured log at `reports/audio_dictate_<date>.jsonl`; TICKET-014 merges this with the silent log.
- CLI: `python -m sabi dictate` runs until Ctrl+C. `--mode push-to-talk|vad` overrides trigger mode. `--dry-run` routes through the paste dry-run path. `--force-cpu` makes faster-whisper run CPU-only.
- Unit test `tests/test_audio_dictate.py` uses stub components (fake `MicrophoneSource` yielding a canned `Utterance`, stub `ASRModel` returning canned `ASRResult`, stub `TextCleaner`, dry-run paste) to verify wiring, latency plumbing, and confidence-floor withholding.

## Acceptance criteria

- [x] `python -m sabi dictate` starts and binds the hotkey without crashing after `python -m sabi probe` passes (end-to-end `__enter__`/`__exit__` exercised by `test_ptt_happy_path_pastes_and_logs`; `--help` wired via the real Typer command).
- [x] Pressing and holding the hotkey while speaking a short phrase produces pasted text within 500 ms of release on the reference laptop (CUDA) / under 800 ms CPU-only (pipeline wired and latency plumbing asserted; real-hardware smoke run is operator-side via `reports/latency-log.md`).
- [x] In VAD mode, speaking three short phrases back-to-back produces three separate pasted outputs, each correctly segmented (`test_vad_three_utterances_all_pasted`).
- [x] With Ollama off, output falls back to raw ASR and pastes unchanged (`test_ptt_ollama_fallback_still_pastes`).
- [x] `reports/audio_dictate_<date>.jsonl` records one JSON object per utterance (`_JsonlWriter`, asserted in the happy-path and VAD tests).
- [x] On confidence below the threshold, the default behavior (withhold paste pending F12) is observable in the overlay and log, and can be disabled via config (tests `test_ptt_low_confidence_listener_withholds_after_timeout`, `test_ptt_force_paste_hit_triggers_paste`, `test_ptt_force_paste_always_mode_ignores_floor`; per-mode fields `force_paste_mode_ptt` / `force_paste_mode_vad`).
- [x] Unit test passes with all hardware mocked (`tests/test_audio_dictate.py`, 16 tests, all deps injected).
- [x] Latency rows written to `reports/latency-log.md` with `ticket=TICKET-012` for every smoke run (`_finalize` -> `append_latency_row("TICKET-012", ...)`).

## Out of scope

- Audio-visual fusion with the silent pipeline - deferred to Phase 2 (roadmap Tier 2). This ticket stays pure-audio.
- Streaming ASR partials - ASR still returns complete utterances. Tightening latency to roadmap targets is a Phase 2 task.
- App-aware cleanup - `CleanupContext.focused_app` is plumbed but not used by the PoC prompt.
- Meeting mode (TTS out) - Flow 2 of the roadmap, explicitly out of PoC scope.

## Notes

- Keep `AudioDictatePipeline` and `SilentDictatePipeline` structurally parallel so the eval harness can treat them interchangeably: same `UtteranceProcessed` shape, same JSONL schema, same latency-log format. If a field is not applicable to one pipeline, it is present with value `null` rather than missing.
- faster-whisper's `int8_float16` compute type shaves meaningful time off ASR on GPU machines; if a CUDA machine comes out slower than CPU int8 in eval, that mode was silently not selected - assert the chosen compute type in the log.

## References

- Roadmap core models table (project_roadmap.md lines 22-28) - "ASR: faster-whisper small (INT8)" + "LLM cleanup: Ollama 3B local" is the audio stack this pipeline wires.
- Roadmap Phase 1 Week 2 (project_roadmap.md line 175) - "Dictation + silent speech both functional. Full internal demo." - this ticket is the dictation half.
- Roadmap Flow 1 UX note (project_roadmap.md line 94) - "Live overlay shows transcript as it's being predicted so the user can cancel bad output before paste" - the confidence-floor behavior is the first pass at this policy.

## Implementation notes (post-merge)

- Pipeline lives in `src/sabi/pipelines/audio_dictate.py`, structurally parallel to `src/sabi/pipelines/silent_dictate.py`. Both modules expose `_Deps` dataclasses for hardware injection; the test suite builds fake mic / ASR / cleaner / paste / hotkey instances and drives the flow without touching real hardware.
- `UtteranceProcessed` carries `pipeline="audio"` plus `trigger_mode`, `duration_ms`, `vad_coverage`, and `peak_dbfs` so TICKET-014 can merge silent + audio JSONL streams without losing provenance.
- Microphone lifecycle: preopened on `__enter__` by default (`mic_open_ms` is logged once on the first utterance). `--ptt-open-per-trigger` flips to a per-press open that mirrors silent-dictate's camera lifecycle; VAD mode always preopens because the consumer thread needs the stream to be live.
- Two hotkey flows:
  - PTT: `HotkeyController(mode="push_to_talk")`. `on_trigger_start` opens the mic (when per-trigger), spawns a capture thread that runs `MicrophoneSource.push_to_talk_segment` between a `start_event` + `end_event` pair, and starts a safety `threading.Timer(mic.max_utterance_ms)` so a stuck hotkey cannot block the segment forever. `on_trigger_stop` sets `end_event`, joins the capture thread, and spawns the dispatch worker.
  - VAD: `HotkeyController(mode="toggle")`. `__enter__` launches `_vad_consumer_loop` which continuously pulls from `mic.next_utterance(timeout=0.1)`; utterances are discarded while `_vad_active` is clear and dispatched while it is set. `on_trigger_start` sets the flag and emits `vad_activated`; `on_trigger_stop` clears it and emits `vad_deactivated`.
- Validator auto-coerces `hotkey.mode` to match `trigger_mode` (PTT -> `push_to_talk`, VAD -> `toggle`) and rejects configs where `hotkey.binding` equals `force_paste_binding`. `load_audio_dictate_config` reconstructs through `model_validate` so the validator re-runs after TOML overlays.
- Force-paste is mode-specific: `force_paste_mode_ptt` defaults to `listener` (matches silent-dictate), `force_paste_mode_vad` defaults to `always` because the VAD stream cannot cleanly pause. The F12 HotkeyController is only started when the active mode equals `listener`; `always` and `never` skip the second controller entirely. A single `--force-paste` CLI flag flips both fields so operators do not have to remember the active mode.
- Latency keys: `mic_open_ms`, `warmup_ms`, `capture_ms`, `vad_ms`, `asr_ms`, `cleanup_ms`, `inject_ms`, `total_ms`. `vad_ms` is reported as `0.0` today because the TICKET-006 backend does not surface per-frame VAD cost; the docstring flags this as a roadmap item.
- JSONL events: `trigger_start` / `trigger_stop` (PTT), `vad_activated` / `vad_deactivated` (VAD), `force_paste_hit`, `utterance_processed`, `pipeline_error`. The date-rollover uses `start_ts_ns`, matching silent-dictate.
- Dispatch runs on daemon `threading.Thread`s spawned per utterance; `close()` is idempotent and cancels any pending force-paste timer, joins active dispatch + capture threads with a 2 s cap, and then tears down the hotkey controllers, mic, cleaner, and ASR context managers.
- Tests (`tests/test_audio_dictate.py`): 16 cases covering PTT happy path, Ollama fallback, silent + empty-ASR gates, low-confidence withheld + force-paste hit + `force_paste_mode="always"`, VAD triple-utterance, dry-run, latency plumbing, TOML overlay (including `trigger_mode`-driven `hotkey.mode` coercion), validator rejection of duplicate bindings, and the mic preopen vs per-trigger lifecycle.
- Full suite: `python -m pytest` - 122 passed (includes the existing TICKET-006..011 tests).
