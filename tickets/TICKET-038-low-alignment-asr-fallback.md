# TICKET-038 - Low-alignment ASR fallback policy

Phase: 2 - Fusion & polish
Epic: Fusion
Estimate: M
Depends on: TICKET-016, TICKET-032, TICKET-037
Status: Not started

## Goal

Add a **configurable** policy for the **low-alignment verbatim branch only** (when
`aligned_ratio < min_alignment_ratio`), so we can prefer ASR in cases like personal
`alignment_below_threshold` → `vsr_primary` where VSR “wins” on headline confidence
but ASR text is often closer—**without** turning the whole product into
`mode=audio_primary` (which would largely defeat the purpose of fused / VSR-led
behavior).

TICKET-037 evidence (e.g. `reports/fusion-mode-ab-personal.md`) to keep in mind:

- On the personal dataset, **`auto` and `audio_primary` aggregates matched** (same
  mean WER/cleanup/latency shape), while **`vsr_primary` was catastrophic in aggregate**.
  So the fix is **not** “default the app to global `audio_primary`.”
- The actionable lever is the **early return** in `combine()` that picks one full
  transcript when alignment is too weak; high-alignment paths keep normal
  per-word fusion.

## System dependencies

None new.

## Python packages

None new.

## Work

- Add `FusionConfig.low_alignment_fallback` (exact name up to implementer) with a
  small closed set, e.g.
  `Literal["higher_confidence", "audio_primary", "vsr_primary"]`, default
  **`"higher_confidence"`** so shipping behavior is unchanged until configured.
- **Scope:** only the branch where `aligned_ratio < cfg.min_alignment_ratio` and both
  modalities are non-empty (the current `if _overall_confidence(asr) >= ...` /
  `else` verbatim choice). Do **not** replace normal `auto` mode resolution or
  per-word fusion when alignment is acceptable.
- **Explicit `cfg.mode`:** preserve today’s semantics for `mode="audio_primary"` and
  `mode="vsr_primary"` as the user-facing override. Recommended: apply the new
  fallback knob **only when `cfg.mode == "auto"`**, so forced modes stay predictable;
  document if you choose otherwise.
- **`"higher_confidence"`:** keep current behavior (verbatim side by overall ASR vs
  VSR confidence).
- **`"audio_primary"` / `"vsr_primary"`** (in this knob): force that verbatim side
  on low alignment **only**, for datasets where A/B shows a consistent win.
- **TICKET-032:** final `FusedResult.confidence` remains calibrated after the text
  choice; document honestly that this branch still uses **overall** ASR/VSR
  confidence for `"higher_confidence"` (no reference text at inference). Optional
  follow-up: add a cheap disagreement signal—only if it stays testable and small.
- Update unit tests in `tests/test_fusion.py` for each fallback value (policy
  wiring, not “WER improved” without a reference string in unit tests).
- Update `docs/fusion.md` (field + semantics + scope) and `docs/FUSED_EVAL.md`
  (one short paragraph: TICKET-037 showed `auto` ≈ `audio_primary` on aggregate;
  TICKET-038 is the low-alignment escape hatch, not a global audio takeover).
- If `configs/fusion.toml` exists, document the new key with the conservative default.

## Acceptance criteria

- [ ] `low_alignment_fallback` (or chosen name) exists on `FusionConfig`, default
  preserves current behavior.
- [ ] In `mode="auto"`, each fallback value deterministically picks ASR vs VSR
  verbatim on low alignment as specified; explicit `mode=` behavior unchanged and
  documented.
- [ ] Unit tests cover low-alignment + all fallback values (and existing
  high-alignment paths still pass).
- [ ] Docs state **when** (alignment below threshold) and **why** (verbatim vs
  stitch) the fallback runs, and that global `audio_primary` mode is not required
  for most personal runs where `auto` ≈ `audio_primary` on aggregate.
- [ ] After enabling a non-default fallback on a dev machine, a personal fused eval
  or A/B note shows **target phrases** (`alignment_below_threshold` rows that used
  to pick the wrong verbatim side) improved **or** the report explains confounds
  (e.g. cleanup, tiny dataset)—no requirement to “fix” phrases where all modes
  tie on the same bad `cleaned_wer`.

## Out of scope

- Changing default `FusionConfig.mode` to global `audio_primary` as the product
  strategy (that belongs in product/docs guidance, not this ticket’s default code
  change).
- Learned fusion, VSR fine-tuning, cleanup prompt changes.

## References

- TICKET-032 - fused confidence calibration (post-choice `FusedResult.confidence`).
- TICKET-037 - fusion mode A/B (`reports/fusion-mode-ab-personal.md`).
- `src/sabi/fusion/combiner.py` - low-alignment verbatim branch.
- `reports/poc-eval-fused-personal.md` - historical low-alignment / diagnostics context.
