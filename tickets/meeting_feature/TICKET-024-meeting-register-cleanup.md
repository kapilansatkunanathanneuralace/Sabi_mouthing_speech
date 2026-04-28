# TICKET-024 - Meeting-register cleanup prompt

Phase: 1 - ML PoC
Epic: Cleanup
Estimate: S
Depends on: TICKET-008, TICKET-018
Status: Not started

## Goal

Add a `"meeting"` register to `TextCleaner` so the meeting pipeline gets a prompt tuned for spoken-to-be-heard text, not written dictation. Meeting output has to sound natural when Kokoro reads it aloud, while still preserving the user's meaning.

## System dependencies

None new. Relies on Ollama setup from TICKET-008.

## Python packages

None new.

## Work

- Add `src/sabi/cleanup/prompts/v1_meeting.txt`.
- Wire the prompt resolver so `(version, "meeting")` resolves correctly.
- Add a `meeting_max_output_tokens` override if needed.
- Extend `tests/test_cleanup.py` for meeting prompt routing and prompt fingerprint assertions.
- Extend `docs/cleanup-prompt.md` with a "Meeting register" section.

## Acceptance criteria

- [ ] `TextCleaner.cleanup(raw, CleanupContext(register_hint="meeting", ...))` loads the meeting prompt.
- [ ] `python -m sabi cleanup-smoke --register meeting "so yeah I'm thinking we ship friday"` returns plausible spoken-style cleanup.
- [ ] Dictation register behavior is unchanged.
- [ ] Unit tests assert register-to-prompt routing.
- [ ] `docs/cleanup-prompt.md` explains the meeting-register trade-offs.

## Out of scope

- Prompt tuning per meeting platform.
- Persona / tone selection.
- Auto-learning from corrections.
- Full app-aware tone switching.
- Full meeting-register A/B beyond basic prompt wiring.

## Notes

- Keep the meeting prompt short because meeting mode is latency-sensitive.
- Ollama fallback behavior remains the same: raw text is better than breaking the pipeline.

## References

- Roadmap Flow 2 step 4 (project_roadmap.md line 130).
- Roadmap Flow 1 vs Flow 2 contrast (project_roadmap.md lines 58-144).
- Roadmap UX notes for Flow 2 (project_roadmap.md lines 138-142).
