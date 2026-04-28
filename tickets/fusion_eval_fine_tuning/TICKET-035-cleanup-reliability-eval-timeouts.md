# TICKET-035 - Cleanup reliability for eval timeouts

Phase: 2 - Fusion & polish
Epic: Cleanup
Estimate: S
Depends on: TICKET-018, TICKET-020, TICKET-030
Status: Done

## Goal

Fix the fused eval cleanup fallback pattern seen in `reports/poc-eval-fused-personal.md`, where every row fell back with `http_error: ReadTimeout`. Eval reports should distinguish real cleanup quality from Ollama availability/timeout failures.

## System dependencies

- Local Ollama running with `llama3.2:3b-instruct-q4_K_M` or the configured cleanup model.

## Python packages

None new.

## Work

- Add eval-specific cleanup timeout configuration or CLI override, e.g. `python -m sabi eval --cleanup-timeout-ms 5000`.
- Add an optional cleanup warm-up/probe before timed eval runs so the first request does not poison every row.
- Make cleanup fallback counts visible in the eval summary.
- Update `docs/FUSED_EVAL.md` with the recommended Ollama preflight and timeout guidance.
- Add tests that simulate cleanup timeout/fallback and verify the report calls it out clearly.

## Acceptance criteria

- [x] Eval can be run with a longer cleanup timeout without editing config files.
- [x] Eval reports show cleanup fallback count/rate in summary or diagnostics.
- [x] Docs explain how to tell "cleanup failed to run" from "cleanup made text worse".
- [x] Tests cover fallback-heavy eval output.

## Out of scope

- Changing prompt wording.
- Training or fine-tuning cleanup models.
- Replacing Ollama.

## References

- `reports/poc-eval-fused-personal.md` - all rows showed `cleanup_fallback=yes`.
- TICKET-018 - cleanup prompt v2.
- TICKET-030 - fused diagnostics.
