# TICKET-036 - Calibrated fused eval baseline

Phase: 2 - Fusion & polish
Epic: Eval
Estimate: S
Depends on: TICKET-020, TICKET-032, TICKET-035
Status: Done

## Goal

Re-run the personal fused eval after confidence calibration and cleanup reliability fixes, then save a clean baseline report and tuning suggestions. This gives us a trustworthy before/after point for the next fusion policy changes.

## System dependencies

- Personal fused eval dataset under `data/eval/fused`.
- Ollama available, or cleanup fallback intentionally disabled/documented for the run.

## Python packages

None new.

## Work

- Run `fused-eval-check` on `data/eval/fused`.
- Run fused eval with calibrated confidence and the cleanup timeout/preflight from TICKET-035.
- Generate `reports/poc-eval-fused-personal-calibrated.md`.
- Generate `reports/fused-tuning-suggestions-calibrated.md`.
- Compare against the previous `reports/poc-eval-fused-personal.md`.
- Document the observed changes in `docs/FUSED_EVAL.md` or a short report note.

## Acceptance criteria

- [x] A new calibrated fused eval report exists under `reports/`.
- [x] The new report uses calibrated confidence values from TICKET-032.
- [x] Cleanup fallback rate is known and documented.
- [x] A new tuning suggestions report is generated from the calibrated report.
- [x] The old and new baseline differences are summarized.

## Out of scope

- Changing fusion policy.
- Collecting new data.
- Training models.

## References

- TICKET-032 - confidence calibration.
- TICKET-035 - cleanup reliability.
- `reports/poc-eval-fused-personal.md` - previous baseline.
