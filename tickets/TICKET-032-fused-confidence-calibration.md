# TICKET-032 - Fused confidence calibration

Phase: 2 - Fusion & polish
Epic: Fusion
Estimate: M
Depends on: TICKET-016, TICKET-017, TICKET-020, TICKET-030
Status: Done

## Goal

Fix the fused pipeline's overconfident failures. The personal eval report showed several phrases with `confidence=1.00` and `WER=1.000`, which means current confidence should not be trusted for paste gating, recommendations, or later training decisions. This ticket calibrates fused confidence against eval outcomes and updates the confidence computation or gating policy accordingly.

## System dependencies

None new. Requires a personal fused eval dataset and diagnostic report.

## Python packages

None new.

## Work

- Audit `src/sabi/fusion/combiner.py` confidence computation and `src/sabi/pipelines/fused_dictate.py` paste gating.
- Add calibration analysis over fused eval records:
  - Bucket by confidence.
  - Compute average WER per bucket.
  - Identify high-confidence/high-WER cases.
- Update `FusionCombiner` confidence logic if the bug is local to fusion:
  - Penalize strong ASR/VSR disagreement.
  - Penalize missing modality.
  - Penalize low face-present ratio or low VAD coverage when available in pipeline/eval context.
  - Avoid reporting `1.00` unless both modalities agree and underlying confidences support it.
- If context is not available inside `FusionCombiner`, add a post-fusion confidence adjustment in the fused pipeline/eval runner.
- Add report fields showing calibrated confidence vs raw confidence if both are retained.
- Add tests covering:
  - Agreement yields high confidence.
  - Disagreement lowers confidence.
  - Missing modality lowers confidence.
  - High-confidence/high-WER fixtures are flagged by diagnostics.

## Acceptance criteria

- [x] Fused confidence no longer returns `1.00` for clear ASR/VSR disagreement in unit tests.
- [x] Personal fused eval report exposes confidence values that are meaningfully lower on known severe failures.
- [x] Paste gating can use the calibrated confidence without increasing false-positive paste risk.
- [x] Calibration behavior is documented in `docs/fusion.md` or `docs/FUSED_EVAL.md`.
- [x] Unit tests cover agreement, disagreement, and missing-modality confidence behavior.

## Out of scope

- Training a learned calibration model.
- Changing ASR or VSR model confidence internals.
- Fully solving accuracy. This only makes confidence more honest.

## Notes

- Keep calibration simple and inspectable. A heuristic is acceptable for PoC if it is tested and documented.
- Prefer lowering confidence on suspicious cases over inflating confidence on good cases.

## References

- TICKET-016 - fusion module.
- TICKET-017 - fused dictation pipeline.
- TICKET-030 - diagnostics that reveal high-confidence failures.
