# TICKET-037 - Fusion mode A/B eval

Phase: 2 - Fusion & polish
Epic: Eval
Estimate: M
Depends on: TICKET-016, TICKET-020, TICKET-030, TICKET-036
Status: Done

## Goal

Add a repeatable A/B eval path for fusion modes: `auto`, `audio_primary`, and `vsr_primary`. The current personal report suggests `vsr_primary` low-alignment choices caused severe failures, so we need measured evidence before changing defaults.

## System dependencies

- Personal fused eval dataset under `data/eval/fused`.

## Python packages

None new.

## Work

- Add a CLI option or command to run fused eval across fusion modes, e.g. `python -m sabi eval-fusion-modes --dataset data/eval/fused --modes auto,audio_primary,vsr_primary`.
- Reuse the existing offline fused runner and `FusionConfig(mode=...)`.
- Produce one markdown report comparing WER, confidence, latency, and high-confidence/high-WER counts by mode.
- Include per-phrase winner/loser details for severe failures.
- Add tests using fake fused runners or deterministic synthetic records.
- Document the workflow in `docs/FUSED_EVAL.md`.

## Acceptance criteria

- [x] A command can compare `auto`, `audio_primary`, and `vsr_primary` on one dataset.
- [x] The report shows aggregate WER and latency by mode.
- [x] The report identifies which mode wins per phrase or at least flags severe mode regressions.
- [x] Tests cover mode comparison output.
- [x] Docs explain how to use the A/B output before changing fusion defaults.

## Out of scope

- Changing the default fusion policy. TICKET-038 owns that.
- Training ASR/VSR.

## References

- `reports/poc-eval-fused-personal.md` - low-alignment `vsr_primary` severe failures.
- TICKET-031 - tuning recommendations.
- TICKET-036 - calibrated baseline.
