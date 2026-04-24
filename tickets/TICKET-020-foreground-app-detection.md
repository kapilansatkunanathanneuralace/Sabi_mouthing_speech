# TICKET-020 - Foreground app detection

Phase: 1 - ML PoC
Epic: Orchestration
Estimate: S
Depends on: TICKET-002
Status: Not started

## Goal

Ship `sabi.orchestration.focus.ForegroundWatcher` - a lightweight poller (or event-driven hook) that tells the rest of the system which app has focus right now, classified into `{"zoom", "teams", "meet", "slack", "browser", "editor", "other"}`. This powers the mode switcher (TICKET-021) and gives `CleanupContext.focused_app` a real value so the LLM cleanup prompt can eventually become app-aware (out of scope for PoC, wiring is not).

## System dependencies

- Windows only. Uses `user32.dll` (`GetForegroundWindow`, `GetWindowThreadProcessId`) and `psapi.dll` via ctypes. No admin privileges required for read-only foreground polling.
- For browser tab detection (Chrome/Edge), Windows UI Automation is available via `pywinauto` or raw UIA bindings, but it is brittle and slow - we keep browser classification at the process level only and do not try to read the tab URL. Meet-in-browser is therefore best-effort: we report `"browser"`, and the mode switcher treats that as ambiguous.

## Python packages

Add to `pyproject.toml`:

- `psutil==6.0.0` - cross-platform process lookup; we use it for the process-name resolution path so the same code compiles on non-Windows even if it only functions on Windows.
- `pywin32==306` - Win32 bindings used for `GetForegroundWindow` and window title retrieval. Already listed as a stretch dependency in TICKET-013; we adopt it here as a firm dependency for the meeting-mode track.

Already installed (TICKET-002):

- `pydantic`

## Work

- Create `src/sabi/orchestration/focus.py`.
- Define `FocusEvent` dataclass: `timestamp_ns`, `pid`, `process_name`, `exe_path`, `window_title`, `app_class` (`"zoom" | "teams" | "meet" | "slack" | "browser" | "editor" | "other"`), `is_browser` bool.
- Classification table, committed as a config file `configs/app_classes.toml` so new apps can be added without code changes:
  - `zoom.exe`, `cpthost.exe` -> `zoom`.
  - `Teams.exe`, `ms-teams.exe` -> `teams`.
  - `chrome.exe`, `msedge.exe`, `firefox.exe`, `brave.exe` -> `browser`; `is_browser=True`. The mode switcher treats "browser with a meeting-like window title" as "possibly meet/teams/zoom web" - heuristic only.
  - Window-title heuristics for browser classification (applied only when `is_browser=True`): titles containing `"Meet"`, `"Zoom Meeting"`, `"Microsoft Teams"` upgrade the event's `app_class` to the respective meeting tag with a lower-confidence flag. Do not invest in any DOM inspection.
  - `slack.exe` -> `slack`.
  - `Code.exe`, `Cursor.exe`, `pycharm64.exe`, `devenv.exe`, `sublime_text.exe` -> `editor`.
  - Everything else -> `other`.
- Implement `ForegroundWatcher`:
  - Poll loop (default 200 ms) reading `GetForegroundWindow` -> HWND -> PID -> process name + window title.
  - Caches the last `FocusEvent`; only emits to subscribers when `(pid, window_title)` changes, to keep downstream quiet.
  - Runs on its own daemon thread, started/stopped via context manager. On stop, `join(timeout=1 s)`.
  - Exposes a pub/sub-style `.subscribe(callback)` so TICKET-021 can register a handler.
- CLI: `python -m sabi focus-debug` prints `FocusEvent`s as the user tabs between windows. Useful sanity check.
- `tests/test_focus.py` monkeypatches the Win32 calls so no real windowing is required:
  - Asserts classifier mapping for each configured process name.
  - Asserts browser-title heuristic upgrades `app_class` correctly.
  - Asserts the watcher only emits on transitions, not every poll.
  - Asserts the watcher thread shuts down cleanly on context exit.

## Acceptance criteria

- [ ] `python -m sabi focus-debug` prints `FocusEvent`s with the correct `app_class` as the tester tabs between Zoom, Teams (desktop), Slack, a browser showing `meet.google.com`, and VS Code.
- [ ] Switching between two Slack windows does not spam events (no pid/title change).
- [ ] Browser with window title containing `"Google Meet"` reports `app_class="meet"` with a lower-confidence indicator.
- [ ] Poll interval default (200 ms) produces acceptable CPU usage (< 1 % on the reference laptop). Interval is config-driven.
- [ ] `ForegroundWatcher` used as a context manager cleans up its thread (verified by a test).
- [ ] Unit tests cover classifier rules and the transitions-only emit policy.

## Out of scope

- Reading browser tab URLs via UIA / DevTools protocol - too brittle and too slow for PoC.
- Detecting audio-call-in-progress state (Zoom "I am currently in a meeting") - not exposed by public APIs, and not needed; mode switcher only cares that Zoom is focused.
- Linux / Mac equivalents - Windows-only PoC.
- Using focus state to rewrite prompts per app - TICKET-008 / TICKET-019 already ship `focused_app` plumbing but explicitly defer app-aware prompting.

## Notes

- Keep the poll loop cheap. Calling `GetForegroundWindow` + title + process-name resolution is fast (< 1 ms) but still we guard against a 5 ms ceiling on the loop to avoid ballooning CPU when the user tabs rapidly.
- Window titles change a lot (typing in a text editor updates the title). The pid + title hash is fine as a change detector; pid alone misses tab-within-browser transitions.

## References

- Roadmap Flow 2 UX note (project_roadmap.md line 142) - "App detection: when Zoom/Meet/Teams is frontmost, default to meeting mode rather than dictation mode" is the direct motivator.
- Roadmap orchestration layer (project_roadmap.md lines 47-52) - "Mode switcher ... Per-app rules (auto-mode-switch when Zoom is focused, etc.)" is exactly what this feeds.
- Roadmap scene/screen context (project_roadmap.md lines 157-162) - later tiers extend this with "what app is the user in" for cleanup; we lay the groundwork here but do not implement those tiers.
