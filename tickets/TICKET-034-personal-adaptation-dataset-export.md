# TICKET-034 - Personal adaptation dataset export

Phase: 3 - Personalization research
Epic: Eval
Estimate: M
Depends on: TICKET-019, TICKET-020, TICKET-033
Status: Not started

## Goal

If TICKET-033 concludes that personal fine-tuning is feasible, add an export tool that converts `data/eval/fused` into the training/adaptation format required by the chosen path. The export must create separate train/validation splits so we do not train and evaluate on the same phrases.

## System dependencies

- Personal fused dataset from TICKET-019.
- Fine-tuning target/format decision from TICKET-033.

## Python packages

No new packages unless TICKET-033 identifies a required exporter dependency.

## Work

- Add `python -m sabi export-personal-adaptation --dataset data/eval/fused --out data/adaptation/personal`.
- Validate source media before export using the TICKET-020 validator.
- Produce train/validation manifests:
  - Stable phrase ids.
  - Text transcript.
  - Video path.
  - Audio path if the selected training path needs it.
  - Split label.
- Add deterministic split controls:
  - `--val-ratio`.
  - `--seed`.
  - Optional `--holdout-tag`.
- Copy or link media into the export directory depending on what the chosen training path expects.
- Write `metadata.json` with source dataset path, export timestamp, split counts, and tool version/git SHA where available.
- Document the export format in `docs/PERSONAL_VSR_FINETUNING.md` or a new `docs/PERSONAL_ADAPTATION_EXPORT.md`.
- Add tests for valid export, invalid source dataset, deterministic splitting, and manifest contents.

## Acceptance criteria

- [ ] `python -m sabi export-personal-adaptation --help` documents dataset, output, split, and seed options.
- [ ] Running the exporter on a valid fused dataset creates train and validation manifests with no overlapping phrase ids.
- [ ] Export refuses datasets that fail `fused-eval-check`.
- [ ] Export output records enough metadata to reproduce the split.
- [ ] Docs explain the exported format and how it relates to the fine-tuning decision from TICKET-033.
- [ ] Unit tests cover export success, invalid input, and deterministic splitting.

## Out of scope

- Running training.
- Choosing the fine-tuning method. TICKET-033 owns that decision.
- Uploading private media to any external service.
- Automatically replacing production model weights.

## Notes

- Keep privacy front and center: exported media still contains the user's face and voice.
- If TICKET-033 says fine-tuning is not feasible, this ticket should be deferred or rewritten.

## References

- TICKET-019 - fused eval dataset collection.
- TICKET-020 - dataset validation and personal eval.
- TICKET-033 - fine-tuning feasibility decision.
