# TICKET-030 - Fused eval report diagnostics

Phase: 2 - Fusion & polish
Epic: Eval
Estimate: M
Depends on: TICKET-017, TICKET-020
Status: Not started

## Goal

Make fused eval reports explain *why* phrases failed, not just which phrases failed. Extend the markdown report for `--pipeline fused` so each phrase includes ASR text, VSR text, fusion mode/reason, source weights, per-word origin, modality confidence, face-present ratio, audio peak, and cleanup fallback reason. This is the prerequisite for any serious tuning or training work.

## System dependencies

None new. Uses the personal fused eval dataset from TICKET-019 and the eval flow from TICKET-020.

## Python packages

None new.

## Work

- Extend `src/sabi/eval/harness.py` report rendering for fused records:
  - Add ASR text, VSR text, fusion mode/reason, source weights, and per-word origin columns.
  - Add modality diagnostics: ASR confidence, VSR confidence, face-present ratio, VAD coverage, audio peak dBFS.
  - Add cleanup diagnostics: prompt version, fallback status, and fallback reason where available.
- Add a compact "Fused Diagnostics" section below phrase results so the main phrase table does not become unreadable.
- Highlight suspicious cases:
  - `confidence >= 0.95` and `cleaned_wer >= 0.5`.
  - ASR/VSR disagreement with high fused confidence.
  - Cleanup fallback or bypass.
  - Low face-present ratio or low audio peak.
- Update `docs/FUSED_EVAL.md` with how to read the new diagnostics.
- Add tests using fake fused runner output that assert the report contains ASR/VSR/fusion diagnostic fields.

## Acceptance criteria

- [ ] `python -m sabi eval --dataset data/eval/fused --pipeline fused --runs 1 --out reports/poc-eval-fused-personal.md` includes a "Fused Diagnostics" section.
- [ ] The report shows ASR text, VSR text, fusion mode/reason, source weights, per-word origin, ASR confidence, VSR confidence, face ratio, VAD coverage, and peak dBFS for fused rows.
- [ ] The report flags high-confidence/high-WER fused failures.
- [ ] Cleanup fallback/bypass is visible with prompt version and reason when available.
- [ ] `docs/FUSED_EVAL.md` explains how to use the diagnostics to decide whether audio, video, fusion, or cleanup is the likely failure point.
- [ ] Unit tests cover the new report section with deterministic fake fused records.

## Out of scope

- Automatically recommending config changes. TICKET-031 owns recommendations.
- Changing fusion confidence math. TICKET-032 owns confidence calibration.
- Fine-tuning or exporting training data. TICKET-033 and TICKET-034 own that track.

## Notes

- Keep the report human-readable. Long per-word origin lists can be truncated with an explicit marker.
- Do not add heavy plotting or notebook dependencies; markdown is enough.

## References

- TICKET-017 - fused dictation pipeline.
- TICKET-020 - personal fused eval runbook.
- `reports/poc-eval-fused-personal.md` - current report shows WER but not enough root-cause detail.
