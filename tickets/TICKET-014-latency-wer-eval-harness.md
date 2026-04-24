# TICKET-014 - Latency + WER eval harness

Phase: 1 - ML PoC
Epic: Eval
Estimate: L
Depends on: TICKET-011, TICKET-012
Status: Not started

## Goal

Ship an **offline** evaluation harness that replays a small fixed set of mouthed video clips and spoken audio clips through both pipelines, produces a markdown report with per-stage latency percentiles and WER vs ground truth, and writes it to `reports/poc-eval-<date>.md`. This is how we know if a change helped or hurt; it is not a live UX tool.

## System dependencies

- Dataset artifacts under `data/eval/` - **not checked in** (too large, and likely to contain user faces/voices). Each contestant's local `data/eval/` holds:
  - `phrases.jsonl` - one line per phrase, with `id`, `text`, `video_path`, `audio_path`, optional tags.
  - `video/<id>.mp4` - short clips of a person mouthing the phrase at the camera (silent or audible, does not matter for the silent pipeline since it only sees video).
  - `audio/<id>.wav` - 16 kHz mono of the phrase spoken aloud.
- A minimum viable set for first eval: ~20 phrases drawn from the Harvard sentence list so results are comparable across developers. Sample list tracked in `data/eval/phrases.sample.jsonl` (committed with empty paths for repo bootstrap).
- `ffmpeg` (standalone binary) for media conversion. Documented in `docs/INSTALL.md`.

## Python packages

New additions to `pyproject.toml`:

- `jiwer==3.0.4` - canonical WER computation.
- `pandas==2.2.2` - quick aggregation of per-utterance metrics before rendering.
- `tabulate==0.9.0` - clean markdown tables from pandas dataframes.

All three are evaluation-only; mark them under `[project.optional-dependencies].eval` and require opt-in install `pip install -e .[eval]`.

## Work

- Create `src/sabi/eval/harness.py`.
- Define `EvalConfig` (dataset path, runs per phrase (default 3 for variance), warm up (default 1), pipelines to run (`["silent", "audio"]`), output directory).
- Implement two offline entry points that do not require camera/mic hardware:
  - `SilentOfflineRunner(video_path) -> UtteranceProcessed`: reads the mp4 via `opencv-python`, feeds frames directly into the `LipROIDetector` -> `VSRModel` -> `TextCleaner`, bypassing `WebcamSource` and `HotkeyController`. Reuses the existing `SilentDictatePipeline` with mocked capture and trigger, so exactly the same code path that runs live is exercised offline.
  - `AudioOfflineRunner(wav_path) -> UtteranceProcessed`: loads the wav, constructs an `Utterance`, feeds through `ASRModel` -> `TextCleaner`. Paste is always `dry_run=True` in eval so clipboard is never touched.
- Harness loop:
  - For each phrase, for each configured pipeline, runs the configured number of iterations, captures `UtteranceProcessed` events.
  - Computes per-phrase WER against ground truth via `jiwer.wer`, both for raw model output and post-cleanup text (two columns - otherwise we cannot tell if cleanup is helping).
  - Aggregates per stage: p50, p90, p95, p99, max latencies.
- Renders `reports/poc-eval-<date>.md` with:
  - Header: git sha, hardware summary (from `python -m sabi probe` output), Ollama model tag, VSR weights sha, ASR model size, total run time.
  - Summary table: per-pipeline WER (raw + cleaned), total-latency percentiles.
  - Per-stage breakdown table.
  - Phrase-level table linking to clip ids with individual WER values.
  - Short "known failure modes" section seeded from any utterance that aborted (no-face, low-confidence).
- CLI: `python -m sabi eval --dataset data/eval --runs 3 --out reports/poc-eval-2026-04-24.md`.
- Append a single row per eval run to `reports/latency-log.md` (p50 / p95 per stage per pipeline, one row per pipeline).
- Write `tests/test_eval_harness.py` that uses tiny synthetic media (a generated 1-second silent mp4 and a 1-second sine-wave wav), stubbed VSR/ASR/cleanup, and asserts: report file is created, contains the expected sections, WER columns are populated, latency columns are populated.

## Acceptance criteria

- [ ] `python -m sabi eval --dataset data/eval/sample --out reports/poc-eval-test.md` on a freshly populated sample dataset produces a readable markdown report with WER and latency tables.
- [ ] `data/eval/phrases.sample.jsonl` is committed with 20 Harvard sentences and empty media paths so a new dev can drop in their recordings and run eval.
- [ ] Per-stage percentile math is correct, verified by a unit test feeding known latency arrays through the aggregator.
- [ ] The harness runs fully offline - no webcam, mic, or hotkey accessed.
- [ ] `reports/poc-eval-<date>.md` is git-ignored by default (only `reports/latency-log.md` is committed).
- [ ] Running with Ollama off still completes; the report shows `cleanup: bypassed` and the cleaned-WER column equals the raw-WER column.
- [ ] `pip install -e .[eval]` installs jiwer/pandas/tabulate; the base install still works without them (harness import wrapped in a try/except that prints a helpful message).

## Out of scope

- Live eval that drives the actual webcam and microphone - the offline runners are the eval contract for this PoC. Live eval is brittle, slow, and hard to attribute.
- Automated regression gates / CI - we do not have CI for this PoC; the report is consumed by a human.
- Training or fine-tuning on eval failures - that informs Phase 2 but is not implemented here.
- Confusion matrices, phoneme error rate, multi-language metrics - add only if the basic WER + latency report is not enough to decide next steps.

## Notes

- Every phrase must be replayed identically across runs so latency variance is the model's, not the harness's. No frame skipping, no random seeds in the pipeline components.
- Keep the Harvard sentences, not a weird hand-picked set, so external comparisons against published VSR numbers are at least informative.

## References

- Roadmap risks, latency budget (project_roadmap.md lines 222-223) - "Every ms matters - measure end-to-end from day one." This ticket is how we fulfill that promise.
- Roadmap Phase 1 Week 2 (project_roadmap.md line 175) - the internal demo the Week 2 milestone calls for depends on this harness's output to tell us whether the PoC is credible.
