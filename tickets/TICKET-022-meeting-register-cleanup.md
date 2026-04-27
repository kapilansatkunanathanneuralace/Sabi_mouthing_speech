# TICKET-022 - Meeting-register cleanup prompt

Phase: 1 - ML PoC
Epic: Cleanup
Estimate: S
Depends on: TICKET-008
Status: Not started

## Goal

Add a `"meeting"` register to `TextCleaner` (TICKET-008) so the meeting pipeline gets a prompt tuned for **spoken-to-be-heard** text, not written-for-a-chat text. Meeting output has to sound natural when Kokoro reads it aloud - stripping every filler and forcing terminal punctuation that the model never intended produces clipped, robotic speech. This ticket is about prompt design and wiring, not about the cleanup infrastructure.

## System dependencies

None new. Relies on the Ollama setup from TICKET-008.

## Python packages

None new.

## Work

- Add `src/sabi/cleanup/prompts/meeting.txt`. Prompt responsibilities:
  - Preserve spoken flow - do not collapse natural pauses, do not remove thinking fillers unless clearly an artifact of the upstream model's failure (e.g., an isolated "uh" that the user obviously did not mouth, as indicated by confidence hints).
  - Still fix casing and insert commas / periods where they affect intonation, because Kokoro's prosody uses punctuation heavily.
  - Do not expand contractions. "I'm" stays "I'm", not "I am".
  - Do not add information the user did not produce.
  - Output plain sentence text, no markdown, no quotes.
- Wire the register into the existing `TextCleaner` API:
  - `CleanupContext.register_hint` is already defined in TICKET-008 with values `"dictation" | "meeting" | "chat"`. This ticket flips the code path so `"meeting"` loads `prompts/meeting.txt` instead of the dictation prompt.
  - If TICKET-018 has already shipped, the prompt-resolution table is keyed `(prompt_version, register) -> path`; this ticket adds a `(version, "meeting")` row for whichever prompt versions exist (initially just `("v1", "meeting")` pointing at `prompts/meeting.txt`). If TICKET-018 has not shipped yet, keep a simpler `_REGISTER_TO_PROMPT_PATH: dict[str, Path]` and let TICKET-018 generalize it later. Either way, adding registers stays a one-line change.
  - Add a `meeting_max_output_tokens` override (default 384) because meeting sentences can be a bit longer than chat-style dictation.
- Extend `tests/test_cleanup.py` with cases:
  - `register_hint="meeting"` loads the meeting prompt (assert via the mock transport receiving the expected system-prompt fingerprint).
  - A mouthed phrase with natural fillers ("so, what I'm thinking is we could ship by friday, yeah") passes through with fillers preserved (assert the mock-returned text is untouched by pre/post-processing beyond whitespace).
  - An obvious upstream artifact ("[[unclear]] so I was saying") is removed by prompt instruction (testable via a fixture response from the mock, not by running the real model).
- Add prompt-level A/B doc `docs/cleanup-prompt.md` already created in TICKET-008 - extend with a "Meeting register" section explaining the specific trade-offs and how to measure regression when changing the prompt. The A/B harness will live in TICKET-027's listening-test eval.

## Acceptance criteria

- [ ] `TextCleaner.cleanup(raw, CleanupContext(register_hint="meeting", ...))` loads `prompts/meeting.txt` and calls Ollama with it.
- [ ] `python -m sabi cleanup-smoke --register meeting "so yeah I'm thinking we ship friday"` returns a plausibly spoken-style cleaned string (contractions preserved, punctuation light) in under 400 ms on the reference laptop.
- [ ] Dictation register behavior is unchanged - TICKET-008 tests still pass.
- [ ] Unit tests assert register -> prompt routing and that the meeting prompt's system-prompt fingerprint is present on the outgoing request.
- [ ] `docs/cleanup-prompt.md` has a "Meeting register" section describing the trade-offs and A/B plan.

## Out of scope

- Prompt tuning per meeting platform (Zoom vs Teams vs Meet) - not useful for PoC; the differences between call platforms are audio, not semantic.
- Persona / tone selection (formal vs casual vs technical) - future work; PoC ships one meeting register.
- Auto-learning from user corrections - Phase 3 personalization, explicit roadmap item.
- Full app-aware tone switching (Slack vs Docs vs code) - TICKET-008 already flags this as deferred.
- Prompt-version A/B for the meeting register - TICKET-018 owns the prompt-version axis for the dictation register; extending it to the meeting register lands as a follow-up after this ticket and TICKET-018 are both in.

## Notes

- Keep the meeting prompt short, like the dictation prompt. Every prompt token costs latency, and meeting mode is the most latency-sensitive flow in the PoC.
- The cleanup call is still free to be bypassed with `bypass_on_error=True` - Ollama down must not break the meeting pipeline. Raw VSR text going into Kokoro will sound rough but will still make sound.

## References

- Roadmap Flow 2 step 4 (project_roadmap.md line 130) - "LLM cleanup (meeting register, not chat) 50-150 ms" is exactly what this ticket implements.
- Roadmap Flow 1 vs Flow 2 contrast (project_roadmap.md lines 58-144) - shows the two flows need different post-processing styles.
- Roadmap UX notes for Flow 2 (project_roadmap.md lines 138-142) - frames why natural speech preservation matters.
