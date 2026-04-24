# Audio dictation pipeline (TICKET-012)

`python -m sabi dictate` wires the microphone + VAD (TICKET-006),
faster-whisper ASR (TICKET-007), Ollama cleanup (TICKET-008), clipboard
paste (TICKET-009), and hotkey trigger (TICKET-010) into the audio
counterpart of `silent-dictate`. This doc covers both trigger modes
(PTT and VAD), the mode-specific force-paste policy, latency budget,
and the JSONL schema that TICKET-014 (eval) will merge with
`silent-dictate` output.

## Flow

Two trigger modes, selectable via `[pipeline].trigger_mode`:

- **push_to_talk** (default): hold the configured chord (default
  **Ctrl+Alt+Space**). The microphone is preopened on pipeline start
  and every PTT press captures a single utterance with
  `MicrophoneSource.push_to_talk_segment`. Release the chord to
  transcribe, clean, and paste.
- **vad**: press the chord once to activate VAD streaming, press
  again to deactivate. Between the two presses the background VAD
  consumer dequeues every detected utterance, runs ASR + cleanup +
  paste, and keeps going until you press again. The hotkey
  controller is auto-coerced to `mode="toggle"` for you.

In both modes the pipeline:

1. Emits `trigger_start` / `trigger_stop` (PTT) or `vad_activated` /
   `vad_deactivated` (VAD) to the JSONL log.
2. Runs ASR on the utterance, routes through Ollama cleanup
   (`source="asr"`), and applies the gates below.
3. If the utterance clears the gates, calls `paste_text` with the
   same `InjectConfig` used by `silent-dictate`.

## Gates

- **Silence / empty audio**: utterances with zero samples, or with
  `peak_dbfs <= asr.silence_peak_dbfs` (default -60 dBFS), or with
  `vad_coverage < vad_coverage_floor` (default 0.5) resolve to
  `decision=withheld_silence`. ASR is **not** invoked.
- **Empty ASR**: when `ASRResult.text` is empty after a non-silent
  utterance (usually Whisper hallucinating a blank), the decision is
  `withheld_empty`.
- **Confidence + force paste**: when `ASRResult.confidence <
  confidence_floor` (default 0.40) the cleaned text is held back per
  the active `force_paste_mode_*` setting.

The force-paste gate is mode-specific:

| `trigger_mode`  | default           | rationale |
| --------------- | ----------------- | --------- |
| `push_to_talk`  | `listener`        | Mirrors `silent-dictate` exactly. Low-confidence utterances wait `force_paste_window_ms` (default 1.5 s); press the force-paste chord (default **F12**) within the window to paste anyway. |
| `vad`           | `always`          | VAD cannot reliably pause between utterances, so low-confidence segments paste by default. Set `force_paste_mode_vad = "never"` to silently discard them, or `"listener"` to race the timer against the next utterance. |

Both fields accept `listener | always | never`. The F12 listener is
only started when the **active** mode (determined by `trigger_mode`)
is `listener`; `always` and `never` skip the second HotkeyController.

## CLI

```powershell
python -m sabi dictate [--config PATH]
                       [--mode push-to-talk|vad]
                       [--dry-run]
                       [--force-cpu]
                       [--ptt-open-per-trigger]
                       [--binding CHORD]
                       [--force-paste-binding CHORD]
                       [--confidence-floor FLOAT]
                       [--force-paste listener|always|never]
```

- `--mode` overrides `[pipeline].trigger_mode`. The hyphen form
  (`push-to-talk`) is accepted; the config file uses `push_to_talk`.
- `--dry-run` prints the cleaned text to stdout instead of pasting
  (also flips `InjectConfig.dry_run` so Ctrl+V never fires).
- `--force-cpu` pins faster-whisper onto CPU (int8). Useful for
  smoke-testing on machines without CUDA or when the GPU is busy.
- `--ptt-open-per-trigger` reopens the microphone on every PTT press
  (mirrors `silent-dictate`'s per-trigger webcam lifecycle; LED / OS
  mic indicator flicks on only during the trigger). Default is
  preopen on `__enter__` for snappier latency.
- `--binding` overrides the primary chord; must **not** equal
  `--force-paste-binding`.
- `--force-paste` is a convenience flag that writes *both*
  `force_paste_mode_ptt` and `force_paste_mode_vad` (so a single tap
  flips the active gate regardless of `trigger_mode`).

`scripts/audio_dictate.py` is an argparse shim with the same flags
for machines where the `sabi` console entry point is not installed.

## Latency contract

Every utterance logs a row to `reports/latency-log.md` via
`append_latency_row("TICKET-012", ..., "pipeline", total_ms, 1, notes)`.
The accompanying JSONL line carries the full `latencies` dict:

| key           | meaning |
| ------------- | ------- |
| `mic_open_ms` | `MicrophoneSource.__enter__` latency. Reported once on the first utterance after pipeline start (preopen) or on every utterance when `ptt_open_per_trigger=true`; otherwise `0.0`. Parallel to silent-dictate's `capture_open_ms`. |
| `warmup_ms`   | `ASRModel.warm_up` latency. Only non-zero on the first utterance of a session. |
| `capture_ms`  | Wall time of the captured utterance (`(end_ts_ns - start_ts_ns) / 1e6`). PTT: trigger hold duration. VAD: VAD-segmented speech duration. |
| `vad_ms`      | Cumulative VAD decision time. The TICKET-006 backend does not expose per-frame VAD cost yet, so this is reported as `0.0` pending that instrumentation. |
| `asr_ms`      | `ASRResult.latency_ms` (faster-whisper decode). |
| `cleanup_ms`  | `TextCleaner.cleanup` latency; 0 when Ollama bypasses. |
| `inject_ms`   | `paste_text` latency. |
| `total_ms`    | Dispatch-thread perf-counter delta from the moment the utterance is dequeued to paste-decision complete. |

The roadmap 500 ms CUDA / 800 ms CPU budget applies to
`capture_ms + asr_ms + cleanup_ms + inject_ms`. `mic_open_ms` and
`warmup_ms` are reported separately so the first-utterance outliers
stay visible without distorting the steady-state budget.

## JSONL schema (`reports/audio_dictate_YYYYMMDD.jsonl`)

One JSON object per line, append-only.

| `event_type`          | fields |
| --------------------- | ------ |
| `trigger_start`       | `utterance_id`, `ts_ns`, `trigger_id`, `mode`, `reason` (PTT only) |
| `trigger_stop`        | `utterance_id`, `ts_ns`, `trigger_id`, `duration_ms`, `vad_coverage`, `peak_dbfs` (PTT only) |
| `vad_activated`       | `ts_ns`, `trigger_id`, `reason` (VAD only) |
| `vad_deactivated`     | `ts_ns`, `trigger_id`, `reason` (VAD only) |
| `force_paste_hit`     | `utterance_id`, `ts_ns`, `trigger_id`, `text_final` |
| `utterance_processed` | full `UtteranceProcessed` dump: `pipeline="audio"`, `trigger_mode`, `text_raw`, `text_final`, `confidence`, `used_fallback`, `decision`, `latencies`, `duration_ms`, `vad_coverage`, `peak_dbfs`, `error` |
| `pipeline_error`      | `utterance_id`, `ts_ns`, `reason` (used when the microphone fails to open, etc.) |

The `pipeline="audio"` tag on `utterance_processed` lets TICKET-014
interleave the silent + audio JSONL streams without losing
provenance.

## Overlay hook (TICKET-013 preview)

`AudioDictatePipeline.subscribe(callback)` registers a function that
receives every `UtteranceProcessed`. TICKET-013's overlay will
subscribe here to render the status (recording / withheld / pasted).
Subscribers run on the dispatch worker thread - do not block inside
them.

## Caveats

- **faster-whisper cold start**: the first `transcribe` call can take
  1-3 s even after `warm_up()` when the model is freshly downloaded
  (faster-whisper validates the .bin and allocates CUDA workspace).
  `warmup_ms` is reported separately so it does not pollute the
  per-utterance budget.
- **Ollama cold start**: first utterance will show `used_fallback=true`
  while `llama3.2:3b` loads into VRAM. Warm it with
  `ollama run llama3.2:3b-instruct-q4_K_M < NUL` at startup to skip
  the fallback on the very first press.
- **VAD cannot pause**: with `force_paste_mode_vad="listener"`, the
  force-paste window (1.5 s default) races the next VAD segment. If
  a second utterance lands before the timer fires, the first one is
  still withheld and `force_paste_hit` can only rescue the *most
  recent* pending utterance. Use `"always"` (default) for a
  stream-friendly UX or `"never"` if you want hard gating.
- **Shared `force_paste_binding`**: the `keyboard` library cannot
  register the same chord across two `HotkeyController`s. Running
  `silent-dictate` and `dictate` simultaneously requires distinct
  `force_paste_binding` values.
- **`--ptt-open-per-trigger`**: opens PortAudio per press. On some
  USB headsets the first open takes 200-500 ms, which will dominate
  `capture_ms + asr_ms` on short phrases. Preopen is faster but leaves
  the OS microphone indicator lit for the entire session.
- **`mic.max_utterance_ms` safety cap**: PTT sets a `threading.Timer`
  for `mic.max_utterance_ms` (default 15 s) so a stuck hotkey never
  blocks `push_to_talk_segment` forever. The timer is cancelled on
  `on_trigger_stop`.
- **VAD paste ordering**: each VAD utterance dispatches on its own
  daemon thread, so paste order can shuffle when ASR latency varies
  across back-to-back utterances. Under normal speech cadence (>0.5 s
  gap) this is not observable; a stricter FIFO policy is out of scope
  for the PoC and revisited in TICKET-014.
