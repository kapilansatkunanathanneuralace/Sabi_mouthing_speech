# TICKET-018 - LLM cleanup polish (prompt v2 + eval-driven A/B)

Phase: 2 - Fusion & polish (injected ahead of meeting track per priority reorder)
Epic: Cleanup
Estimate: M
Depends on: TICKET-008, TICKET-014
Status: Done

## Goal

Iterate on the cleanup prompt now that we have **measured** failure data from the eval harness (TICKET-014) and the dogfood "Known failure modes" list seeded in `docs/DEMO.md` (TICKET-015). Ship a `v2_dictation` prompt that strengthens filler removal, stutter de-duplication, and hesitation collapse without expanding scope into hallucination territory. Add a **prompt-version axis** to `CleanupConfig` and to the eval harness so v1 vs v2 can be A/B'd on the same dataset, reported as side-by-side WER + latency columns. Default does **not** flip to v2 in this ticket - that switch lands as a follow-up only after the eval shows non-regressing WER on the reference set.

## System dependencies

None new. Relies on the Ollama setup from TICKET-008 and the eval harness shipped by TICKET-014.

## Python packages

None new. Eval extras (`jiwer`, `pandas`, `tabulate`) are already pinned via TICKET-014's `[project.optional-dependencies].eval`.

## Work

- Migrate the existing prompt asset to a versioned naming scheme (no behavior change for the default flow):
  - Move `src/sabi/cleanup/prompts/default.txt` (TICKET-008) -> `src/sabi/cleanup/prompts/v1_dictation.txt`. Keep the file content identical.
  - Update `TextCleaner` to resolve prompts via a `(prompt_version, register) -> path` table, defaulting to `("v1", "dictation")`. The registers axis is separate (lives in TICKET-022, was 019); this ticket only owns the **versions** axis for the dictation register and leaves the meeting register untouched.
  - Resolution table lives in a small `src/sabi/cleanup/prompts/__init__.py` (or `prompts.py`) module: `_PROMPT_PATHS: dict[tuple[str, str], Path]`. New entries are one-line additions.
- Add `src/sabi/cleanup/prompts/v2_dictation.txt`. v2 strengthens beyond v1's behaviors (TICKET-008 lines 41-46 spec) without expanding scope:
  - Stronger filler list curated from the Harvard-sentence eval set + dogfood data: `um`, `uh`, `er`, `ah`, `mm`, `like` (only when not a verb), `you know`, `i mean`, `kind of`, `sort of`, `basically`, `literally` (when used as filler).
  - Stutter / repetition de-dup: `"I I I think"` -> `"I think"`; `"and and and"` -> `"and"`; `"the the"` -> `"the"`.
  - Hesitation collapse: `"uh i mean um"` -> empty (drop entire hesitation runs); `"so um yeah"` -> `"so yeah"`.
  - Preserves intent verbatim - explicit "do not paraphrase" line. Preserves user's own emphasis words ("really", "very", "actually" when used as adverbs, not fillers).
  - Honors the existing hallucination guard from TICKET-008 line 68 (`max_growth_factor`); v2 prompt must not produce expansions that trip the guard on normal inputs.
- Wire the prompt-version axis into `CleanupConfig` and `TextCleaner`:
  - Add `CleanupConfig.prompt_version: Literal["v1", "v2"] = "v1"` (default unchanged).
  - `TextCleaner._load_prompt(register: str, version: str) -> str` reads via the resolution table, caches in-process per `(version, register)` key.
  - `TextCleaner.cleanup(...)` reads `config.prompt_version` and uses it for the lookup. `CleanupContext.register_hint` continues to drive the register axis.
- Surface the version flag at the CLI boundary on every dictation pipeline:
  - `python -m sabi cleanup-smoke --prompt-version v2 "raw text"` runs v2 prompt and prints latency + cleaned text.
  - `python -m sabi silent-dictate --cleanup-prompt v2`, `python -m sabi dictate --cleanup-prompt v2`, `python -m sabi fused-dictate --cleanup-prompt v2` all flip `config.cleanup.prompt_version` for the run.
  - Each pipeline's TOML default in `configs/silent_dictate.toml` / `configs/audio_dictate.toml` / `configs/fused_dictate.toml` exposes a `[cleanup] prompt_version = "v1"` line with a comment pointing at this ticket.
- Extend the eval harness (`src/sabi/eval/harness.py`) with prompt-version A/B:
  - New CLI flag: `--cleanup-prompt v1` (single) or `--cleanup-prompt v1,v2` (A/B). Default stays `v1` to keep TICKET-014's semantics intact when this flag is omitted.
  - When two versions are passed, the harness loops the dataset once per version per pipeline; per-phrase rows now carry `prompt_version`, and the markdown report grows two new columns: `cleaned_wer_v1`, `cleaned_wer_v2`, plus a delta column `wer_delta_v2_minus_v1` (negative = v2 wins).
  - Summary table adds rows `cleanup-v1` and `cleanup-v2` with p50/p95 latency and aggregate WER. Also a "prompt comparison" section near the top of the report with a one-paragraph automated verdict: "v2 reduces WER by X% on Y of Z phrases; latency change +/- N ms" (templated, not generated text - just numbers in a fixed string).
  - JSONL output gains a `prompt_version` field per phrase row so downstream analysis can re-aggregate without re-running.
- Update `docs/cleanup-prompt.md`:
  - Add a "Prompt versioning" section explaining the `(version, register)` table, how to add a new version, and how to A/B via the eval harness.
  - Add a "v2 dictation prompt - design notes" subsection capturing the filler list, stutter rules, hesitation collapse rules, and the explicit non-goals (no paraphrasing, no expansion, no register switching - that is TICKET-022).
- Extend `tests/test_cleanup.py`:
  - Resolution-table coverage: `(prompt_version="v1", register="dictation")` and `(prompt_version="v2", register="dictation")` both resolve to existing files; an unknown `(version, register)` raises a clear error.
  - Outgoing request fingerprint: when `prompt_version="v2"`, the system-prompt sent to the Ollama mock contains a v2-specific marker substring (e.g. a unique line in `v2_dictation.txt`).
  - Hallucination guard still trips on a v2 mock-response that exceeds `max_growth_factor`.
  - The existing v1 tests pass unchanged (no behavior change when `prompt_version` is omitted / defaulted).
- Extend `tests/test_eval_harness.py` (TICKET-014's test file):
  - With stubbed cleanup returning canned different texts for v1 vs v2, assert the report contains both columns, the delta column, and the prompt-comparison section.
  - Latency math is correct per version.
- Document in `docs/cleanup-prompt.md` how to interpret the A/B output: "A negative `wer_delta_v2_minus_v1` on the aggregate row, with at most a +20 ms latency penalty, is the bar v2 must clear before the default flips."

## Acceptance criteria

- [x] `src/sabi/cleanup/prompts/v1_dictation.txt` exists with content identical to the old `default.txt`; `default.txt` is removed.
- [x] `src/sabi/cleanup/prompts/v2_dictation.txt` exists, is short (under 40 lines), and follows the design notes in `docs/cleanup-prompt.md`.
- [x] `python -m sabi cleanup-smoke --prompt-version v2 "um i i think we should ship like friday you know"` returns a plausibly cleaned string ("I think we should ship Friday." or similar) within the 400 ms budget on the reference laptop with Ollama warm.
- [x] `python -m sabi silent-dictate --cleanup-prompt v2`, `... dictate --cleanup-prompt v2`, `... fused-dictate --cleanup-prompt v2` all run end-to-end on the reference laptop and the JSONL row records `cleanup.prompt_version="v2"`.
- [x] `python -m sabi eval --cleanup-prompt v1,v2 --dataset data/eval/sample` produces a markdown report with `cleaned_wer_v1`, `cleaned_wer_v2`, and `wer_delta_v2_minus_v1` columns plus a "prompt comparison" verdict paragraph.
- [x] All existing TICKET-008 tests pass without modification, plus the new prompt-version cases in `tests/test_cleanup.py`.
- [x] `tests/test_eval_harness.py` covers the A/B path with stubbed cleanup.
- [x] `docs/cleanup-prompt.md` documents prompt versioning, the v2 design notes, and the A/B promotion bar.
- [x] No pipeline default flips to v2 in this ticket - the default stays `prompt_version="v1"`. A follow-up ticket flips defaults once the reference eval shows the bar above is met.

## Out of scope

- Flipping the default prompt version to v2 - explicitly a follow-up. We need eval evidence first; this ticket builds the evidence-collection apparatus, not the conclusion.
- Meeting register prompt - TICKET-022 (was 019) owns the meeting register entirely. Do not touch `prompts/meeting.txt` here, even though the resolution table grows to support it.
- App-aware tone routing (Slack vs Docs vs code) - explicitly deferred per TICKET-008's out-of-scope.
- Per-user adaptation / fine-tuning - Phase 3.
- Streaming token output - cleanup remains one-shot.
- Multi-prompt N-way comparisons in the eval harness - the v1/v2 binary is enough for PoC; generalizing to v1,v2,v3,... is a tiny diff but not needed yet.

## Notes

- Keep the v2 prompt short. Token count translates directly to first-token latency on the 3B model; v2 must not regress p95 cleanup latency by more than +20 ms over v1 on the reference set, or the eval gate fails.
- The roadmap calls Phase 2 cleanup "filler removal and LLM cleanup pass" (project_roadmap.md line 181). v2 is the literal implementation of that line; do not let scope creep this into a "rewrite cleanup" ticket.
- The eval harness rebuilds `TextCleaner` per phrase per version; warm-model behavior should be representative because each version processes ~20 phrases back-to-back. If first-call latency dominates, add a one-shot warm-up call per (version, run) similar to `ASRModel.warm_up()`.

## References

- Roadmap Phase 2 (project_roadmap.md line 181) - "Filler removal and LLM cleanup pass" is exactly what this ticket implements.
- Roadmap UX note Flow 1 step 5 (project_roadmap.md line 86) - "LLM cleanup (filler, punctuation, casing) 50-150 ms" is the latency envelope v2 must respect.
- TICKET-008 (`tickets/TICKET-008-ollama-cleanup.md`) - cleanup foundation; prompt v1 was shipped here.
- TICKET-014 (`tickets/TICKET-014-latency-wer-eval-harness.md`) - the harness this ticket extends.
- TICKET-015 (`tickets/TICKET-015-demo-runbook.md`) - "Known failure modes" section seeds the v2 design data.
- TICKET-022 (`tickets/TICKET-022-meeting-register-cleanup.md`, was 019) - meeting register lives there; left untouched here.
