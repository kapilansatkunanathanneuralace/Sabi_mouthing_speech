# TICKET-016 - Audio-visual fusion module

Phase: 2 - Fusion & polish (injected ahead of meeting track per priority reorder)
Epic: Fusion
Estimate: M
Depends on: TICKET-005, TICKET-007
Status: Done

## Goal

Ship `sabi.fusion.combiner.FusionCombiner` - a pure, hardware-free function that takes the existing `ASRResult` (TICKET-007) and `VSRResult` (TICKET-005) and returns a `FusedResult(text, confidence, source_weights, per_word_origin, mode_used, latency_ms)`. Confidence-weighted, word-level merge with deterministic tiebreak rules and clean degraded-path behavior when either source is empty. This ticket realizes roadmap Tier 2 fusion (project_roadmap.md lines 30-39) at the **module** level only - parallel orchestration, capture, paste, and the fused pipeline are TICKET-017.

## System dependencies

None new. Pure-Python module that operates on existing dataclasses.

## Python packages

Already pinned by TICKET-005:

- `editdistance==0.8.1` - reused for word-level alignment scoring.

Optional add (preferred for cleaner alignment, weigh against bundle size):

- `rapidfuzz==3.9.6` - faster fuzzy alignment with explicit insert/delete/substitute spans. If `editdistance` proves sufficient (its API only returns the distance number, not the alignment), add `rapidfuzz` here; otherwise leave it out and implement a small Needleman-Wunsch-style word aligner in-tree. Prefer the pure in-tree aligner first to keep the dep graph stable.

## Work

- Create `src/sabi/fusion/__init__.py` exposing `FusionCombiner`, `FusedResult`, `FusionConfig`, `FusionMode`.
- Create `src/sabi/fusion/combiner.py`:
  - `FusionMode` literal: `"auto" | "audio_primary" | "vsr_primary"`.
  - `FusionConfig`:
    - `mode: FusionMode = "auto"`.
    - `asr_confidence_floor: float = 0.4` - matches TICKET-012 paste floor; below this in `auto`, ASR loses default authority for that word.
    - `vsr_confidence_floor: float = 0.35` - matches TICKET-011 paste floor.
    - `auto_switch_low_conf_ratio: float = 0.5` - in `auto`, if more than this fraction of ASR words are below the ASR floor, auto upweights VSR for tiebreaking globally.
    - `tie_epsilon: float = 0.02` - per-word confidence delta below which we treat the two sources as tied.
    - `tie_breaker: Literal["asr", "vsr"] = "asr"` - default tiebreak.
    - `min_alignment_ratio: float = 0.5` - if word-level alignment matches less than this share of the shorter sequence, fall through to the higher-overall-confidence source verbatim instead of stitching (avoids Frankenstein outputs when the two transcripts disagree wildly).
  - `FusedResult` dataclass:
    - `text: str` - final stitched text.
    - `confidence: float` - average of `per_word_confidence` after fusion, clamped to `[0, 1]`.
    - `source_weights: dict[str, float]` - `{"asr": w_a, "vsr": w_v}` summing to 1.0; the share of accepted words from each source.
    - `per_word_origin: list[Literal["asr", "vsr", "both"]]` - one entry per word in `text`. `"both"` is used when the two sources agreed on the same word at that aligned position (case-insensitive).
    - `per_word_confidence: list[float]` - the chosen source's confidence for each word.
    - `mode_used: FusionMode` - resolved mode after `"auto"` is collapsed.
    - `mode_reason: str` - free-form one-liner explaining why `mode_used` was selected (e.g. `"asr empty -> vsr_primary"`, `"asr 0.78 / vsr 0.41 -> audio_primary"`).
    - `latency_ms: float` - wall-clock of `combine()` itself; the model latencies stay on `ASRResult`/`VSRResult`.
- Implement `FusionCombiner.combine(asr: ASRResult | None, vsr: VSRResult | None, config: FusionConfig | None = None) -> FusedResult`:
  - Empty/missing source short-circuits:
    - `asr is None or asr.text == ""` and `vsr` non-empty -> return VSR text verbatim with `mode_used="vsr_primary"`, `source_weights={"asr": 0.0, "vsr": 1.0}`, `mode_reason="asr empty"`.
    - Symmetric for VSR empty.
    - Both empty -> `FusedResult(text="", confidence=0.0, source_weights={"asr": 0.0, "vsr": 0.0}, ...)` with `mode_reason="both empty"`. Caller decides whether to paste/abort.
  - Mode resolution (when both sources non-empty):
    - `"audio_primary"` and `"vsr_primary"` are honored as-is.
    - `"auto"` resolves to `"audio_primary"` unless **either** (a) `asr.confidence < asr_confidence_floor` and `vsr.confidence >= vsr_confidence_floor`, or (b) the share of below-floor ASR per-word confidences exceeds `auto_switch_low_conf_ratio`. In those cases, resolve to `"vsr_primary"`.
  - Word-level alignment:
    - Tokenize both texts via simple whitespace + lowercase normalization for the alignment step (originals preserved for reconstruction).
    - Implement `_align(a_tokens, v_tokens)` returning a list of `(a_idx | None, v_idx | None)` pairs via Needleman-Wunsch with match score `+1`, mismatch `-1`, gap `-1`. Keep the scorer in-tree (no extra deps) to keep the dep graph stable.
    - Compute `aligned_ratio = matched_pairs / min(len(a_tokens), len(v_tokens))`.
    - If `aligned_ratio < min_alignment_ratio`, skip stitching and return the higher-overall-confidence source verbatim with `mode_reason="alignment_below_threshold"`.
  - Per-word selection:
    - For an aligned `(a_idx, v_idx)` pair where both tokens equal (case-insensitive): origin `"both"`, confidence `max(a_conf, v_conf)`, surface form from the `mode_used` primary source so casing/punctuation stays consistent within the sentence.
    - For an aligned pair with disagreeing tokens: choose by per-word confidence. If `|a_conf - v_conf| < tie_epsilon`, fall back to `tie_breaker`. In `audio_primary`/`vsr_primary` modes the primary source still wins ties.
    - For an unaligned token (insert/delete in alignment): keep it only if it comes from `mode_used`'s primary source; drop the other side. This prefers conservative output over Frankenstein stitches.
  - Confidence aggregation:
    - `per_word_confidence` collects each chosen word's confidence.
    - `confidence = mean(per_word_confidence)` clamped to `[0, 1]`. `0.0` for empty result.
  - Latency: stopwatch around the alignment + selection block (excluding empty short-circuits, which return effectively zero ms).
- Add `FusionCombiner` thin wrapper class with:
  - `__init__(self, config: FusionConfig | None = None)` - stores config; the class instance is reusable across utterances (no per-utterance construction cost).
  - `combine(...)` method delegating to the module-level function for testability.
- CLI: `python -m sabi fusion-smoke "<asr_json>" "<vsr_json>"` reads two JSON files matching the `ASRResult`/`VSRResult` schemas, runs the combiner with default config, and pretty-prints the `FusedResult`. Useful for inspecting fusion behavior without touching webcam/mic. Falls back to `--asr-text "..."` / `--vsr-text "..."` shortcuts that synthesize a minimal `ASRResult`/`VSRResult` with uniform per-word confidences (taken from `--asr-conf` / `--vsr-conf` flags, defaults `0.7` / `0.5`).
- Add `configs/fusion.toml` with the defaults above plus a commented `mode = "auto"` block. Both TICKET-017's pipeline and the smoke command read from this config.
- `tests/test_fusion.py`:
  - Stubbed `ASRResult` / `VSRResult` factories (no model load).
  - Golden cases:
    - Identical sentences -> `per_word_origin = ["both", "both", ...]`, `source_weights={"asr": 0.5, "vsr": 0.5}` (counts halves of "both"), final text matches both inputs.
    - Disagreement on one word with ASR more confident -> ASR wins, origin marks that index `"asr"`.
    - Disagreement on one word with VSR more confident in `vsr_primary` -> VSR wins.
    - Empty ASR -> returns VSR verbatim with `mode_used="vsr_primary"`, `mode_reason="asr empty"`.
    - Both empty -> `text=""`, `confidence=0.0`.
    - `aligned_ratio` below threshold -> stitching skipped, higher-overall-confidence source returned verbatim with `mode_reason="alignment_below_threshold"`.
    - Tie within `tie_epsilon` -> respects `tie_breaker` config.
    - Latency field is monotonically positive (sanity check, not a hard threshold).
- Document the public API in a new `docs/fusion.md` covering `FusionConfig`, `FusedResult` schema, mode-resolution rules, and a worked example matched to one of the golden test cases.

## Acceptance criteria

- [x] `from sabi.fusion import FusionCombiner, FusedResult, FusionConfig` works after a clean install.
- [x] `python -m sabi fusion-smoke --asr-text "ship by friday" --vsr-text "ship by friday" --asr-conf 0.9 --vsr-conf 0.5` prints a `FusedResult` with `text="ship by friday"`, `per_word_origin=["both", "both", "both"]`, `source_weights={"asr": 0.5, "vsr": 0.5}`, `mode_used="audio_primary"`.
- [x] `python -m sabi fusion-smoke --asr-text "" --vsr-text "hello world" --vsr-conf 0.6` prints VSR text verbatim with `mode_used="vsr_primary"`, `mode_reason="asr empty"`.
- [x] All eight golden test cases in `tests/test_fusion.py` pass; the suite runs in under 200 ms (no model loads).
- [x] `combine()` never raises on any combination of empty / non-empty inputs covered by the test matrix - the ticket adds a Hypothesis-style fuzz test (or hand-written random combinations) generating 100 random (text, conf) pairs and asserts no exceptions, no NaN/Inf in `confidence`, and `len(per_word_origin) == len(text.split())`.
- [x] `latency_ms` is recorded on every non-empty `FusedResult` and bounded under 5 ms for inputs up to 32 words on the reference laptop (pure-Python alignment).
- [x] `docs/fusion.md` exists and describes mode resolution, `FusedResult` schema, and one worked example.

## Out of scope

- Running the actual ASR / VSR models or any capture - that is TICKET-017.
- Parallel ASR + VSR execution / threading - TICKET-017's pipeline owns the parallelism.
- Cleanup integration - the fused pipeline still feeds `FusedResult.text` into `TextCleaner`; the combiner does not call cleanup.
- Per-app fusion-mode overrides via foreground app classification - that lands later, after TICKET-023 (foreground app, was 020) ships.
- Streaming fusion (combining partial hypotheses incrementally) - one-shot fusion only for PoC.

## Notes

- Keep the combiner allocation-light. The fused pipeline calls `combine()` once per utterance; if we ever extend to streaming, the combiner must stay pure-Python and dep-free.
- Do not log inside `combine()` - the caller pipeline already logs the fused result via its JSONL writer; double-logging only adds latency.
- The roadmap calls out fusion as "the single biggest accuracy lever" (project_roadmap.md line 38). Treat the alignment + selection rules as a knob set the pipeline can tune; do not bake any hardcoded heuristics that the eval harness cannot move.

## References

- Roadmap fusion layer (project_roadmap.md lines 30-39) - the four-bullet decision matrix this combiner implements.
- Roadmap Phase 2 (project_roadmap.md lines 179-184) - "Audio-visual fusion live (confidence-weighted ASR + VSR)" is the literal Phase 2 deliverable this ticket starts.
- `src/sabi/models/asr.py` (TICKET-007) - `ASRResult` shape consumed by the combiner.
- `src/sabi/models/vsr.py` (TICKET-005) - `VSRResult` shape consumed by the combiner.
