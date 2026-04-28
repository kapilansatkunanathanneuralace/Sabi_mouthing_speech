# TICKET-025 - Foreground app detection

Phase: 1 - ML PoC
Epic: Orchestration
Estimate: S
Depends on: TICKET-002
Status: Not started

## Goal

Ship `sabi.orchestration.focus.ForegroundWatcher`, a lightweight poller that reports which app has focus, classified into meeting apps, chat/editor apps, browser, and other. This powers the mode switcher and gives cleanup a real `focused_app` value.

## System dependencies

- Windows only. Uses Win32 foreground-window APIs.
- Browser tab detection is heuristic only.

## Python packages

Add to `pyproject.toml`:

- `psutil`
- `pywin32`

## Work

- Create `src/sabi/orchestration/focus.py`.
- Define `FocusEvent`.
- Add `configs/app_classes.toml`.
- Implement `ForegroundWatcher` with transition-only pub/sub.
- Add `python -m sabi focus-debug`.
- Add `tests/test_focus.py` with Win32 calls monkeypatched.

## Acceptance criteria

- [ ] `python -m sabi focus-debug` prints correct app classes when tabbing between Zoom, Teams, Slack, browser, and editor.
- [ ] Switching between unchanged windows does not spam events.
- [ ] Browser title heuristics can classify Google Meet.
- [ ] Default poll interval keeps CPU under 1 percent on the reference laptop.
- [ ] Context-manager cleanup stops the watcher thread.
- [ ] Unit tests cover classifier rules and transition-only emission.

## Out of scope

- Reading browser tab URLs.
- Detecting whether a meeting call is active.
- Linux / Mac equivalents.
- Prompt rewriting per focused app.

## Notes

- Keep polling cheap and config-driven.
- PID plus title is enough for PoC transition detection.

## References

- Roadmap Flow 2 UX note (project_roadmap.md line 142).
- Roadmap orchestration layer (project_roadmap.md lines 47-52).
- Roadmap scene/screen context (project_roadmap.md lines 157-162).
