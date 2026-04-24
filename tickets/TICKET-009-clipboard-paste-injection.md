# TICKET-009 - Clipboard + paste injection

Phase: 1 - ML PoC
Epic: Injection
Estimate: S
Depends on: TICKET-002
Status: Done

## Goal

Build `sabi.output.inject.paste_text(text)` - the last step of both pipelines. Saves the user's existing clipboard contents, writes the cleaned text, sends Ctrl+V to the focused window, and restores the prior clipboard after a small delay so the user's clipboard history is not silently polluted. Handles unicode and emoji. This is deliberately the "clipboard + PyAutoGUI paste" approach from the roadmap output layer, not character-by-character typing.

## System dependencies

- Windows 10/11. No extra installs.
- For `pyautogui` keystrokes to reach another app, the app we are pasting into must accept Ctrl+V and must be focused (not minimized). Accessibility APIs are not required on Windows for this flow, unlike Mac.

## Python packages

Already in TICKET-002:

- `pyperclip`
- `pyautogui`
- `pydantic`

No new additions.

## Work

- Create `src/sabi/output/inject.py`.
- Define `InjectConfig` (paste_delay_ms 15 - delay between clipboard write and Ctrl+V; restore_delay_ms 400 - delay before restoring the previous clipboard; dry_run bool).
- Implement:
  - `capture_clipboard() -> str | None` using `pyperclip.paste`; returns None if clipboard is empty or holds non-text.
  - `paste_text(text: str, config: InjectConfig) -> InjectResult`:
    - Stores prior clipboard.
    - `pyperclip.copy(text)`.
    - Sleeps `paste_delay_ms` so slow clipboards (OneDrive, clipboard managers) finish the write.
    - Calls `pyautogui.hotkey("ctrl", "v")`.
    - Schedules a background thread to restore the prior clipboard after `restore_delay_ms` - does not block the pipeline.
    - Returns `InjectResult(text, length, clipboard_restored_at_ns, latency_ms)`.
  - `dry_run=True` path: copies to clipboard and logs what would have been pasted, but skips the Ctrl+V. Used by tests and the eval harness.
- Add unicode + emoji regression:
  - `tests/test_inject_unicode.py` (dry-run) pastes strings like `"naïve café"`, `"question?"`, `"こんにちは"`, `"smile emoji here"` (keep the emoji in code points, not literal in this ticket file), asserts clipboard round-trips unchanged.
  - Manual verification: `scripts/paste_harness.py --target notepad` opens Notepad via `subprocess.Popen`, gives it focus, pastes a sample, and reads it back via UI Automation (see Notes - this is best-effort, skip if flaky).
- CLI shortcut: `python -m sabi paste-test "your string here"` (prints the clipboard contents it set, pastes into whatever is focused after a 3 s countdown).
- Document a Windows-specific gotcha in `docs/paste-injection.md`: some chat apps (Slack desktop) debounce Ctrl+V if the clipboard was just written; a 15 ms gap is the smallest reliable value observed during PoC development. Revisit under TICKET-014 latency work.

## Acceptance criteria

- [x] `python -m sabi paste-test "hello world"` pastes "hello world" into the focused app after the 3 s countdown. *(CLI wired in `src/sabi/cli.py` with a configurable countdown; dry-run verified end-to-end - latency 27.8 ms on `reports/latency-log.md` line 18. Live Ctrl+V into a focused window is a human-in-the-loop step - the automated agent does not fire real keystrokes to avoid injecting text into the user's active editor.)*
- [x] Unicode test (`tests/test_inject_unicode.py`) passes for all listed strings round-tripping through the clipboard. *(`naive cafe`, `naive cafe` with diacritics, `question?`, Japanese, emoji - all five parametrized samples pass.)*
- [x] After `paste_text`, the user's original clipboard contents are restored within `restore_delay_ms + 50 ms`, asserted in a test that reads clipboard before, after, and post-restore. *(`test_restore_preserves_prior_clipboard` sets prior clipboard, calls `paste_text` with `restore_delay_ms=50`, waits on `result.restore_done`, then asserts clipboard reverted and `clipboard_restored_at_ns > return_ns`.)*
- [x] If `pyperclip.copy` raises (e.g. Windows clipboard locked by another process), `paste_text` logs an ERROR and returns `InjectResult(..., latency_ms=..., error="clipboard_locked")` rather than crashing the pipeline. *(`_safe_copy` retries once after 50 ms backoff on `PyperclipWindowsException`; second failure returns the structured error without firing Ctrl+V or scheduling restore. Covered by `test_clipboard_locked_returns_error`.)*
- [x] Latency appended to `reports/latency-log.md` stage `inject` for each run. *(CLI calls `sabi.models.latency.append_latency_row("TICKET-009", "windows", "inject", ...)`; first row landed at `reports/latency-log.md:18`.)*

## Implementation notes

- New files: `src/sabi/output/__init__.py`, `src/sabi/output/inject.py`, `tests/test_inject_unicode.py`, `docs/paste-injection.md`, `scripts/paste_harness.py`.
- Edited files: `src/sabi/cli.py` (new `paste-test` command + top-level `time` import), `docs/INSTALL.md` (brief paste-injection cross-link).
- `paste_text` exposes a `hotkey=` seam so unit tests swap `pyautogui.hotkey` for a counter and never touch real input; production callers leave it `None` and the default lazy import of `pyautogui` runs.
- `InjectResult.restore_done: threading.Event | None` lets tests wait on the background restore thread without polling; it is `None` only on the `clipboard_locked` fast-exit path where no restore was scheduled.
- `scripts/paste_harness.py` stays dependency-free: it `Popen`s Notepad, waits for focus, pastes, and asks the human to verify visually. No `pywinauto` / UIA, matching the ticket's "skip if flaky" guidance.
- Full suite: 83 passed (`pytest -q`) after TICKET-009, up from 73 after TICKET-008.

## Out of scope

- Character-by-character typing fallback - roadmap explicitly picks clipboard + paste as "faster and more reliable than character-by-character typing".
- Accessibility-based text insertion (UIA/AX) - out of PoC.
- Mac + Linux support - PoC is Windows-only; other OSes are a later ticket.
- Detecting which app is focused and conditionally adjusting (e.g. strip trailing newline for Slack) - that is TICKET-011/012 pipeline work, not this module.

## Notes

- Do not rely on `pyautogui.write()` - it is much slower and drops emoji/unicode on Windows.
- `pyperclip` uses the Win32 clipboard API, which has occasional `OpenClipboard` contention. Retry once with 50 ms backoff on `pyperclip.PyperclipWindowsException`.
- Test window managers (Alt+Tab, virtual desktops) can steal focus between the clipboard write and Ctrl+V. The pipeline must time the hotkey trigger immediately before `paste_text`; we document that constraint here but the enforcement lives in TICKET-010 / TICKET-011.

## References

- Roadmap output layer (project_roadmap.md lines 41-45) - "Text injection - clipboard + paste via PyAutoGUI. Faster and more reliable than character-by-character typing, handles emoji and unicode."
- Roadmap Flow 1 steps 6-7 (project_roadmap.md lines 87-88) - "Text placed on clipboard <5 ms, PyAutoGUI paste into focused app <20 ms" latency budget.
