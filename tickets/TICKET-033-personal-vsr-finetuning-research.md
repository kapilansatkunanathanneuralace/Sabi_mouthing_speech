# TICKET-033 - Personal VSR fine-tuning research spike

Phase: 3 - Personalization research
Epic: VSR
Estimate: M
Depends on: TICKET-019, TICKET-020, TICKET-030
Status: Done

## Goal

Determine whether true personal fine-tuning is feasible for the Chaplin / Auto-AVSR VSR stack using the collected personal fused dataset. This is a research spike, not implementation of training. The output should be a clear recommendation: fine-tune VSR, fine-tune something else, collect more data, or avoid fine-tuning for now.

## System dependencies

- GPU strongly preferred for any realistic fine-tuning experiment.
- Existing Chaplin / Auto-AVSR dependencies from TICKET-005.
- Personal fused dataset from TICKET-019.

## Python packages

No new packages unless the upstream training path requires them. Any proposed additions must be documented, not silently installed.

## Work

- Inspect `third_party/chaplin` and the Auto-AVSR training scripts/checkpoint format.
- Identify expected training data format:
  - Video preprocessing requirements.
  - Text transcript format.
  - Vocabulary/tokenizer requirements.
  - Train/validation split.
  - Minimum useful dataset size.
- Estimate hardware and runtime requirements for:
  - Full fine-tuning.
  - Adapter/LoRA-style tuning if available.
  - Last-layer or language-model adaptation if available.
- Run a tiny dry-run experiment only if upstream scripts support it safely and without large downloads.
- Document risks:
  - Overfitting to 20 phrases.
  - Catastrophic forgetting.
  - GPU memory limits.
  - Evaluation leakage if train/eval split is not separated.
- Produce `docs/PERSONAL_VSR_FINETUNING.md` with a go/no-go recommendation and next implementation ticket if feasible.

## Acceptance criteria

- [x] `docs/PERSONAL_VSR_FINETUNING.md` explains whether Chaplin/Auto-AVSR fine-tuning is feasible in this repo.
- [x] The document lists required data format, dataset size estimate, GPU/runtime expectations, and risks.
- [x] The document recommends one of: proceed with fine-tuning, collect more data first, only tune fusion/config, or defer.
- [x] If a tiny dry-run was possible, the command and outcome are documented.
- [x] No training dependencies are added unless explicitly justified and documented.

## Out of scope

- Implementing the actual fine-tuning pipeline.
- Claiming personal data improves the model without evidence.
- Training on the same eval set without a held-out split.

## Notes

- A "no-go" result is acceptable if the evidence says true fine-tuning is not practical yet.
- This ticket should protect the project from pretending evaluation data is training data.

## References

- TICKET-005 - Chaplin / Auto-AVSR wrapper.
- TICKET-019 - personal media collection.
- TICKET-020 - personal fused eval.
- TICKET-030 - diagnostics to decide whether VSR is the actual failure point.
