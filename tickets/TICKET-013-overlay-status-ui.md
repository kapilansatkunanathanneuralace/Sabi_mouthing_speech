# TICKET-013 - Minimal overlay / status UI

Phase: 1 - ML PoC
Epic: UX
Estimate: M
Depends on: TICKET-011, TICKET-012
Status: Not started

## Goal

Give the user a live view of what the pipelines are doing without stealing focus from the app they are pasting into. Ship a `rich`-based terminal UI (TUI) first, because it is cheap and reliable. An optional always-on-top transparent overlay window (Tkinter) is listed as a stretch goal but only if time allows and the TUI covers eval and demo needs. Implements the roadmap's "cancel bad output before paste" affordance.

## System dependencies

- None beyond what TICKET-002 / TICKET-009 installed.
- If the stretch overlay is attempted: Windows 10/11 ships Tkinter with the reference Python installer; no extra system deps.

## Python packages

Already in TICKET-002:

- `rich`

Stretch only (add to `pyproject.toml` only if the stretch path is pursued; otherwise leave out):

- `pywin32==306` - used to make the Tkinter overlay toolwindow / transparent / always-on-top.

## Work

- Create `src/sabi/ui/status_tui.py`.
- Implement `StatusTUI` using `rich.live.Live` rendering a layout with:
  - Header line: current pipeline (`silent` | `audio`), current mode (`idle` | `recording` | `decoding` | `cleaning` | `pasting`), hotkey binding, Ollama status, CUDA status.
  - Main panel: last N utterances (default 5), each row showing raw text, cleaned text, confidence, and total latency.
  - Footer: rolling per-stage latency (p50 / p95 over the last 20 utterances).
- Subscribe to both pipelines via the `UtteranceProcessed` event bus. The TUI listens; pipelines do not know it exists - loose coupling.
- On an utterance whose confidence is below the pipeline's floor, the row is styled as "pending" and shows a hint: `"[F12 to paste anyway, any other key to discard]"`. Actual keypress routing lives in the pipeline (TICKET-011/012) but the prompt is rendered here.
- Render the live clipboard-restore window: when paste happens, the footer shows `"original clipboard will be restored in <ms>"` to make the behavior transparent.
- Wire the TUI into both CLIs: `python -m sabi silent-dictate --ui tui` and `python -m sabi dictate --ui tui` (default). Passing `--ui none` runs headless for the eval harness.
- `tests/test_status_tui.py` uses `rich.console.Console` with `record=True` to render a handful of synthetic events and snapshot-test the rendered text (via simple string contains assertions, not pixel diff).
- **Stretch**: `src/sabi/ui/overlay.py` provides a minimal Tkinter toplevel that mirrors the header/main/footer into a floating window. Must set `-topmost` and `-transparentcolor` via pywin32 on Windows, and must never accept focus (`WS_EX_NOACTIVATE`). Activated with `--ui overlay`. Skip entirely if scope is tight.

## Acceptance criteria

- [ ] `python -m sabi silent-dictate --ui tui` (and the audio variant) renders the TUI and updates on every pipeline event.
- [ ] Pressing the hotkey visibly changes the header mode indicator within 50 ms of the trigger event.
- [ ] With Ollama stopped, the header shows a red `Ollama: offline (raw output)` message; with Ollama running it shows `Ollama: ok` and the current model.
- [ ] Utterances below the confidence floor are styled pending and show the "F12 to paste" hint.
- [ ] Rolling p50 / p95 footer values match the values written to `reports/latency-log.md` for the same session.
- [ ] `--ui none` runs both pipelines with no TUI output beyond normal log lines (used by TICKET-014).
- [ ] Unit tests render the TUI with stub events and assert the expected text is present.

## Out of scope

- Full always-on-top transparent overlay window (stretch) - ship the TUI first; the overlay is a bonus.
- Click-through / draggable overlay behavior - not required for PoC.
- Cross-platform overlay - Windows-only, and only if the stretch is attempted.
- System tray icon - not needed for PoC.

## Notes

- The TUI must never be the source of truth - structured logs (TICKET-011/012) are. This UI is a human-readable mirror.
- Do not render anything on the main thread blocking the pipeline - the `rich.Live` instance ticks at 10 Hz on its own thread and pulls from a thread-safe queue the pipelines push into.

## References

- Roadmap output layer (project_roadmap.md lines 41-46) - "Overlay UI - transparent floating window for live transcript / confidence / mode indicator." Stretch work here.
- Roadmap Flow 1 UX note (project_roadmap.md line 94) - "Live overlay shows transcript as it's being predicted so the user can cancel bad output before paste" - TUI hint text implements the cancel affordance.
