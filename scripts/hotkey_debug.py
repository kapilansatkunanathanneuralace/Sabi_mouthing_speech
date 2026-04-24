"""Manual hotkey debugger (TICKET-010).

Prints ``[TRIGGER START]`` / ``[TRIGGER STOP]`` timestamps as you press,
hold, and release the configured hotkey. Useful to confirm the
``keyboard`` hook is reachable (e.g. corporate AV not blocking it) and
that the ``min_hold_ms`` / ``cooldown_ms`` gates behave as expected.

Equivalent to ``python -m sabi hotkey-debug``; this script exists so you
can run it without installing the ``sabi`` entry point.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sabi.input import load_hotkey_config, run_hotkey_debug


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--mode", choices=("push_to_talk", "toggle"))
    parser.add_argument("--binding")
    parser.add_argument("--min-hold-ms", type=int)
    parser.add_argument("--cooldown-ms", type=int)
    args = parser.parse_args()

    cfg = load_hotkey_config(args.config)
    overrides: dict[str, object] = {}
    if args.mode:
        overrides["mode"] = args.mode
    if args.binding:
        overrides["binding"] = args.binding
    if args.min_hold_ms is not None:
        overrides["min_hold_ms"] = args.min_hold_ms
    if args.cooldown_ms is not None:
        overrides["cooldown_ms"] = args.cooldown_ms
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    return run_hotkey_debug(cfg)


if __name__ == "__main__":
    sys.exit(main())
