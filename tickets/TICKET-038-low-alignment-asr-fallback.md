# TICKET-038 - Low-alignment ASR fallback policy

Phase: 2 - Fusion & polish
Epic: Fusion
Estimate: M
Depends on: TICKET-016, TICKET-032, TICKET-037
Status: Not started

## Goal

Update the fusion low-alignment policy if A/B evidence confirms ASR is safer than VSR for the personal dataset. In the current report, severe failures like `harvard_001`, `harvard_002`, `harvard_012`, `harvard_017`, `harvard_018`, and `harvard_020` used `vsr_primary` after `alignment_below_threshold` even though ASR was often closer.

## System dependencies

None new.

## Python packages

None new.

## Work

- Use TICKET-037 output to decide whether low-alignment should prefer ASR by default.
- Add a `FusionConfig` option for low-alignment fallback policy, such as `low_alignment_fallback = "higher_confidence" | "audio_primary" | "vsr_primary"`.
- Default conservatively based on measured results.
- Preserve existing explicit `mode=audio_primary` / `mode=vsr_primary` behavior where appropriate.
- Update unit tests for low-alignment ASR and VSR cases.
- Update `docs/fusion.md` and `docs/FUSED_EVAL.md`.

## Acceptance criteria

- [ ] Low-alignment fallback policy is configurable.
- [ ] Unit tests prove the selected policy avoids known `vsr_primary` severe failures.
- [ ] The policy uses calibrated confidence from TICKET-032.
- [ ] Docs describe when and why the fallback chooses ASR vs VSR.
- [ ] A personal eval rerun shows severe low-alignment failures reduced or clearly explains why not.

## Out of scope

- Learned fusion.
- VSR fine-tuning.
- Prompt cleanup changes.

## References

- TICKET-032 - confidence calibration.
- TICKET-037 - fusion mode A/B evidence.
- `reports/poc-eval-fused-personal.md` - low-alignment severe failures.
