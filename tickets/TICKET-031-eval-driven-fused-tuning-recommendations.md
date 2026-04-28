# TICKET-031 - Eval-driven fused tuning recommendations

Phase: 2 - Fusion & polish
Epic: Eval
Estimate: M
Depends on: TICKET-020, TICKET-030
Status: Done

## Goal

Add a lightweight analysis command that reads a fused eval report or fused eval records and recommends manual tuning actions. This is not training. It should turn personal eval results into practical next steps like "audio looks strong, try `audio_primary`", "VSR failures correlate with low face ratio", or "cleanup is making WER worse; compare v1/v2".

## System dependencies

None new.

## Python packages

None new. Use the existing eval extras if tabular rendering is useful.

## Work

- Add `python -m sabi fused-tuning-suggest --report reports/poc-eval-fused-personal.md` or an equivalent command that consumes structured eval output if TICKET-030 adds it.
- Compute recommendation signals:
  - Per-phrase WER buckets: perfect, minor, severe.
  - ASR vs VSR disagreement from TICKET-030 diagnostics.
  - High confidence but high WER.
  - Cleanup worsens WER or fallback is common.
  - Latency dominated by ROI/VSR/cleanup.
  - Capture quality hints from face ratio, VAD coverage, and peak dBFS.
- Print recommendations grouped by likely action:
  - Capture improvements.
  - Fusion config candidates.
  - Confidence floor candidates.
  - Cleanup prompt / Ollama checks.
  - Model fine-tuning candidates.
- Add a small generated markdown output option under `reports/`, e.g. `reports/fused-tuning-suggestions.md`.
- Document the recommendation workflow in `docs/FUSED_EVAL.md`.
- Add tests with small fixture reports/records for each recommendation type.

## Acceptance criteria

- [x] Running the recommendation command on a fused eval report prints at least one human-readable recommendation category.
- [x] High-confidence/high-WER phrases produce a confidence-calibration recommendation.
- [x] Cleanup fallback-heavy reports produce an Ollama/cleanup recommendation.
- [x] ASR-good/VSR-bad patterns produce capture/VSR recommendations.
- [x] VSR-good/ASR-bad patterns produce microphone/ASR recommendations.
- [x] The docs clearly state recommendations are manual and do not retrain models.
- [x] Unit tests cover the major recommendation branches.

## Out of scope

- Automatically editing config files.
- Fine-tuning models.
- Guaranteeing recommendations are optimal; this is a diagnostic assistant, not an optimizer.

## Notes

- Prefer conservative language. The command should say "likely" and show evidence.
- Keep the recommendation logic deterministic so report changes are reviewable.

## References

- TICKET-020 - personal fused eval.
- TICKET-030 - diagnostics needed for useful recommendations.
