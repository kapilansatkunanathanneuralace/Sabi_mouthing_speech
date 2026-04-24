# TICKET-008 - Ollama 3B LLM cleanup

Phase: 1 - ML PoC
Epic: Cleanup
Estimate: M
Depends on: TICKET-002
Status: Not started

## Goal

Add a `TextCleaner.cleanup(raw_text, context) -> CleanedText(text, edits, latency_ms)` pass backed by a locally hosted Ollama 3B model. Handles filler removal, punctuation, sentence casing, and light de-duplication of stuttered words. If Ollama is not reachable, the pipeline must still work - `TextCleaner` returns the raw text unchanged and logs a WARNING exactly once per process.

## System dependencies

- **Ollama** installed locally (Windows installer from https://ollama.com/download). Documented in `docs/INSTALL.md`.
- A 3B model pulled locally, default `llama3.2:3b-instruct-q4_K_M`. The specific model tag is recorded in `configs/cleanup.toml` and pulled via `ollama pull` in the install doc.
- ~3 GB disk for the quantized model.

## Python packages

Already in TICKET-002:

- `httpx`
- `pydantic`
- `rich` (for the smoke script output)

No new additions. We talk to Ollama via its HTTP API (`/api/generate` or `/api/chat`); no extra client SDK.

## Work

- Create `src/sabi/cleanup/ollama.py`.
- Define `CleanupConfig` (base_url `http://127.0.0.1:11434`, model name, timeout_ms 800, max_output_tokens 256, temperature 0.2, bypass_on_error `True`).
- Define `CleanedText` dataclass (`text`, `edits` (optional list of (span, replacement) tuples or None if the model does not return structured diffs), `latency_ms`, `used_fallback` bool).
- Implement `TextCleaner`:
  - `.is_available()` pings `/api/tags` and caches result for 5 s. Called once at pipeline startup so the first real utterance is not charged for the probe.
  - `.cleanup(raw_text: str, context: CleanupContext) -> CleanedText`:
    - If `not is_available()` and `bypass_on_error`, returns `CleanedText(text=raw_text, used_fallback=True)` in under 1 ms, logs WARNING once.
    - Else posts to `/api/chat` with a system prompt (stored in `src/sabi/cleanup/prompts/default.txt`) and a user message containing raw text + context JSON.
    - Captures wall-clock latency; if it exceeds `timeout_ms`, cancels and returns the raw text with `used_fallback=True`.
  - `CleanupContext` dataclass: `source` (`"asr" | "vsr"`), `focused_app` (optional string, populated by TICKET-011/012 when available), `register_hint` (`"dictation" | "meeting" | "chat"` - for the PoC we only use "dictation").
- Prompt v1 (committed under `prompts/default.txt`): instructs the model to:
  - Preserve the user's intended meaning verbatim - do not add content.
  - Remove filler words ("um", "uh", "like" when not the verb, "you know").
  - Insert sentence-ending punctuation and proper casing.
  - Collapse repeated stuttered words ("I I I think" -> "I think").
  - Return only the cleaned text, no commentary.
- CLI: `python -m sabi cleanup-smoke "um i think it might like work"` prints the cleaned string and the latency, or shows the bypass warning if Ollama is not running.
- `tests/test_cleanup.py` uses `httpx.MockTransport` to stub Ollama and verify:
  - Happy path returns `CleanedText` with `used_fallback=False`.
  - Connection refused returns `used_fallback=True` with raw text preserved.
  - Timeout path (slow mock) returns `used_fallback=True` and does not block beyond `timeout_ms + 50`.
- Write a short `docs/cleanup-prompt.md` explaining prompt versioning and how to A/B prompts against the eval set (TICKET-014 reuses this).

## Acceptance criteria

- [ ] With Ollama running, `python -m sabi cleanup-smoke "um i think it might like work"` returns a plausibly cleaned string ("I think it might work." or similar) in under 400 ms on reference hardware.
- [ ] With Ollama stopped, the same command prints the raw input unchanged, logs the WARNING once, and exits 0.
- [ ] Repeated calls during a single run do not log the WARNING more than once - state is stored on the `TextCleaner` instance.
- [ ] `is_available()` does not block the pipeline longer than its HTTP timeout even when the Ollama server hangs (test uses a mock that never responds).
- [ ] Latency is appended to `reports/latency-log.md` stage `cleanup`.

## Out of scope

- Upgrading to a 7B or hosted model - explicit roadmap upgrade path, not PoC.
- App-aware tone switching (Slack vs Docs vs code comments) - the `CleanupContext.focused_app` field is plumbed but the PoC prompt ignores it. A follow-up ticket owns app-aware tone.
- Streaming token output - we read the full response before paste because we only inject once. Streaming is a UI ticket, not cleanup.
- Per-user adaptation / LoRA - Phase 3 roadmap item.

## Notes

- Keep the prompt short. Every token costs latency; 300-400 ms is an aggressive budget and large system prompts alone can eat half of it on CPU-only Ollama.
- Always validate the model output length is under a small multiple of the input length. A model that hallucinates a paragraph should be discarded and raw text returned instead.

## References

- Roadmap core models table (project_roadmap.md line 26) - "LLM cleanup: Ollama 3B local" is the MVP target.
- Roadmap Flow 1 step 5 (project_roadmap.md line 86) - "LLM cleanup (filler, punctuation, casing) 50-150 ms" is the latency envelope this ticket aims for.
- Roadmap UX note (project_roadmap.md line 95) - "App-aware cleanup: tone for Slack vs. Docs vs. code comments is different" motivates the `CleanupContext` stub that a later ticket will fill in.
