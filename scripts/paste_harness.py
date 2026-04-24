"""Manual paste harness (TICKET-009).

Opens Notepad, waits for the window to take focus, then calls
:func:`sabi.output.paste_text`. Because the ticket flags programmatic
UIA readback as "best-effort, skip if flaky", this harness deliberately
stays simple: it pastes, prints what should be visible in Notepad, and
lets the human confirm visually. No ``pywinauto`` / COM dependency.

Usage::

    python scripts/paste_harness.py --text "naive cafe" --focus-delay 1.5

Notepad is Windows-only; on other OSes the script exits with a helpful
message.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from sabi.output import InjectConfig, paste_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="Sabi paste harness test \U0001F642 naive cafe")
    parser.add_argument(
        "--focus-delay",
        type=float,
        default=1.5,
        help="Seconds to wait after launching Notepad so it can take focus.",
    )
    parser.add_argument("--paste-delay-ms", type=int, default=15)
    parser.add_argument("--restore-delay-ms", type=int, default=400)
    args = parser.parse_args()

    if sys.platform != "win32":
        print("paste_harness: Windows only (Notepad launch). Use sabi paste-test instead.")
        return 0

    print("launching Notepad...")
    proc = subprocess.Popen(["notepad.exe"])
    try:
        time.sleep(args.focus_delay)
        result = paste_text(
            args.text,
            InjectConfig(
                paste_delay_ms=args.paste_delay_ms,
                restore_delay_ms=args.restore_delay_ms,
            ),
        )
        print(f"pasted {result.length} chars in {result.latency_ms:.1f} ms")
        print(f"expected text in Notepad: {args.text!r}")
        if result.error:
            print(f"ERROR: {result.error}")
            return 1
        print("check Notepad window visually, then close it to finish.")
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
