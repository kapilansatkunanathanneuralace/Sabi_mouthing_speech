# TICKET-040 - Fused latency profile + optimization

Phase: 2 - Fusion & polish
Epic: Pipeline
Estimate: M
Depends on: TICKET-017, TICKET-030, TICKET-036
Status: Not started

## Goal

Investigate and reduce fused pipeline latency. The personal report showed roughly 12 s median total latency, with VSR and ROI taking multiple seconds. Before demoing or tuning accuracy further, identify whether the bottleneck is ROI processing, VSR inference, model warmup, cleanup timeout, or eval-only overhead.

## System dependencies

- Personal fused eval dataset.
- GPU if available for comparing CPU vs CUDA behavior.

## Python packages

None new.

## Work

- Add or improve per-stage latency diagnostics for fused eval and live fused dictate.
- Compare CPU vs CUDA device settings where available.
- Compare one-phrase eval, multi-phrase eval, and live `fused-dictate --ui tui --dry-run`.
- Identify whether ROI is re-processing too slowly or VSR inference dominates.
- Document practical speed wins, such as keeping camera/model warm, reducing frame count, batching choices, or skipping cleanup during latency smoke tests.
- Add tests only for pure reporting/formatting changes; do not require hardware in CI.

## Acceptance criteria

- [ ] A latency note identifies the top fused bottleneck from the personal report.
- [ ] The report distinguishes eval-only overhead from live pipeline latency where possible.
- [ ] Recommended speed changes are documented in `docs/FUSED_EVAL.md` or a dedicated latency note.
- [ ] Any implemented latency reporting changes are covered by tests.
- [ ] No hardware-dependent tests are added.

## Out of scope

- Rewriting Chaplin internals.
- Model quantization.
- Accuracy tuning.

## References

- `reports/poc-eval-fused-personal.md` - `total_p50_ms` around 12018 ms, VSR and ROI are large contributors.
- TICKET-030 - fused diagnostics.
- TICKET-036 - calibrated baseline.
