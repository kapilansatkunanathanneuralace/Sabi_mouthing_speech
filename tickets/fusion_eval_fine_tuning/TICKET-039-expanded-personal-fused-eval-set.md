# TICKET-039 - Expanded personal fused eval set

Phase: 2 - Fusion & polish
Epic: Eval
Estimate: M
Depends on: TICKET-019, TICKET-020, TICKET-036
Status: Not started

## Goal

Grow the personal fused eval dataset beyond the initial 20 Harvard phrases so tuning decisions are less fragile. The target is at least 100 usable phrase takes across varied lighting, speaking rates, and recording sessions.

## System dependencies

- Webcam and microphone setup from TICKET-019.
- Enough disk space for additional MP4/WAV takes.

## Python packages

None new.

## Work

- Define a 100+ phrase collection plan with tags for session, lighting, and speaking rate.
- Use `collect-fused-eval` to record additional phrases.
- Use `fused-eval-check` after each batch.
- Keep a held-out subset for future comparisons.
- Update `docs/FUSED_EVAL.md` with a practical collection checklist.
- Generate a new baseline report after collection.

## Acceptance criteria

- [ ] `data/eval/fused/phrases.jsonl` has at least 100 valid rows, or the ticket documents why collection stopped earlier.
- [ ] Dataset validation passes with `fused-eval-check`.
- [ ] Rows include useful tags for session/capture conditions.
- [ ] A new eval report is generated on the expanded set.
- [ ] Docs explain the recommended recording variety and held-out split guidance.

## Out of scope

- Training on the dataset.
- Exporting adaptation data.
- Automatic data quality scoring beyond existing validation.

## References

- TICKET-019 - data collection tool.
- TICKET-020 - personal eval runbook.
- TICKET-033 - fine-tuning research says 20 phrases is eval-only.
