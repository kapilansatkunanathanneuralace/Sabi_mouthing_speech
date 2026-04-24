# Paste injection (TICKET-009)

`sabi.output.inject.paste_text` is the last step of both dictation
pipelines. It copies the cleaned text to the clipboard, sends `Ctrl+V`
into the focused window, and restores the user's prior clipboard on a
background thread so clipboard managers (Windows history, OneDrive,
Ditto, etc.) do not silently accumulate dictated snippets.

## Windows gotchas observed during PoC development

- **Slack Desktop debounces clipboard writes.** If `Ctrl+V` is fired in
  the same millisecond as `pyperclip.copy`, Slack occasionally pastes
  the *previous* clipboard entry. A `paste_delay_ms` of **15 ms** is the
  smallest value that was reliable across Slack, Discord, VS Code,
  Notepad, Chrome, and Word. Do not drop below that without re-testing
  the full app matrix; revisit under TICKET-014 latency work.
- **`OpenClipboard` contention.** `pyperclip` talks to the Win32
  clipboard directly. When another app (Teams, OneDrive clipboard sync)
  holds the clipboard for a few ms, `pyperclip.copy` raises
  `PyperclipWindowsException`. `paste_text` retries once after 50 ms;
  on the second failure it returns `InjectResult(error="clipboard_locked")`
  without firing `Ctrl+V` so nothing garbage gets pasted.
- **Focus stealing.** Alt+Tab, UAC prompts, and virtual-desktop
  switches between the clipboard write and the hotkey press will route
  `Ctrl+V` to the wrong window. The pipeline (TICKET-010 / TICKET-011)
  is responsible for freezing focus right before calling `paste_text`;
  this module does not re-verify focus.
- **Do not use `pyautogui.write()`.** It types character-by-character,
  drops many emoji / non-BMP codepoints on Windows, and is an order of
  magnitude slower than clipboard + `Ctrl+V`.

## Config reference

```python
from sabi.output import InjectConfig, paste_text

cfg = InjectConfig(
    paste_delay_ms=15,     # clipboard write -> Ctrl+V gap
    restore_delay_ms=400,  # delay before prior clipboard is restored
    dry_run=False,         # True = copy-only, skip Ctrl+V (tests, eval harness)
)
result = paste_text("hello world", cfg)
```

`InjectResult` fields:

| field | meaning |
| --- | --- |
| `text`, `length` | Echoed input. |
| `latency_ms` | `perf_counter` wall-clock for capture + copy + delay + hotkey (restore thread excluded). |
| `clipboard_restored_at_ns` | `time.monotonic_ns()` when the background thread finished restoring the prior clipboard. `0` if restore has not completed yet or was skipped (e.g. `clipboard_locked`). |
| `restore_done` | `threading.Event` that the restore thread sets; `None` on the `clipboard_locked` error path. Tests use `restore_done.wait(...)` to avoid polling. |
| `error` | `"clipboard_locked"` when both `pyperclip.copy` attempts raised; otherwise `None`. |

## Smoke test

```powershell
python -m sabi paste-test "hello world"
```

The CLI prints a 3 s countdown, gives you time to focus the target
window, then pastes. Appends one row to `reports/latency-log.md` under
`stage = inject`. Use `--dry-run` to copy-only without firing `Ctrl+V`,
useful for verifying the clipboard round-trip without focus games.

## Prompt versioning

Not applicable - this module is mechanical. See
[`docs/cleanup-prompt.md`](cleanup-prompt.md) for the LLM cleanup step,
which lives immediately upstream of paste injection.
