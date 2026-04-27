# TICKET-020 - Personal fused eval runbook + baseline

Phase: 2 - Fusion & polish
Epic: Eval
Estimate: S
Depends on: TICKET-017, TICKET-019
Status: Done

## Goal

Create the repeatable "run it for myself" workflow after TICKET-019 collects a personal fused eval dataset. This ticket produces commands, docs, and checks for running fused eval on `data/eval/fused`, interpreting the report, and deciding what config/code to tune next. It must make clear that no model training happens automatically: the dataset measures the current pipeline.

## System dependencies

- Completed fused eval dataset from TICKET-019.
- Working fused dictation runtime dependencies: webcam, microphone, VSR, ASR, cleanup, and eval extras.

## Python packages

No new packages. Uses TICKET-014 eval extras:

- `jiwer`
- `pandas`
- `tabulate`

## Work

- Add `docs/FUSED_EVAL.md`:
  - How to confirm `data/eval/fused/phrases.jsonl` has non-empty media paths.
  - How to run `python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --out reports/poc-eval-fused-personal.md`.
  - How to optionally compare cleanup prompts with `--cleanup-prompt v1,v2`.
  - How to read WER, latency p50/p95, confidence, and failure modes.
  - What results mean for the live pipeline and what they do **not** mean.
- Add `python -m sabi fused-eval-check`:
  - Validates dataset media paths before running the expensive eval.
  - Prints counts for phrases, videos, wavs, missing files, invalid audio, and unreadable videos.
  - Prints the exact eval command to run.
- Add a small reusable dataset validator in `src/sabi/eval/fused_dataset.py`.
- Add tests for valid and invalid fused dataset folders.
- Add a short section to `docs/INFRA_CHEAT_SHEET.md` explaining that this is eval data, not automatic model training.

## Acceptance criteria

- [x] `python -m sabi fused-eval-check --dataset data/eval/fused` reports phrase count, valid media count, and actionable errors for missing/invalid files.
- [x] `docs/FUSED_EVAL.md` gives the exact commands for collecting, validating, evaluating, and reading the report.
- [x] Running the documented eval command on a filled dataset writes `reports/poc-eval-fused-personal.md`.
- [x] The report includes fused WER, per-stage latency, and phrase-level failures.
- [x] The docs clearly state that no training/fine-tuning happens automatically and no extra command is needed for "training to take effect".
- [x] Unit tests cover dataset validation success and failure cases.

## Out of scope

- Fine-tuning ASR, VSR, or fusion weights on the collected data.
- Auto-updating thresholds based on the report. Tuning remains a human decision after reading the metrics.
- Building the collection recorder itself. TICKET-019 owns data capture.
- Meeting-mode eval. That remains in the meeting tickets.

## Notes

- Treat this as a personal benchmark loop: collect data, evaluate, inspect, tune manually, evaluate again.
- Keep output reports under `reports/`, which is already the project convention for generated artifacts.

## References

- TICKET-014 - eval harness.
- TICKET-017 - fused pipeline.
- TICKET-019 - fused eval dataset collection tool.
