"""Silent-dictation pipeline entry point (TICKET-011).

Equivalent to ``python -m sabi silent-dictate``; this script exists so
you can run it without installing the ``sabi`` console entry point.
See ``docs/silent-dictate.md`` for CLI flags, JSONL schema, and
latency-budget caveats.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sabi.pipelines import load_silent_dictate_config, run_silent_dictate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-cpu", action="store_true")
    parser.add_argument("--keep-camera-open", action="store_true")
    parser.add_argument("--binding", default="")
    parser.add_argument("--force-paste-binding", default="")
    parser.add_argument("--confidence-floor", type=float, default=-1.0)
    parser.add_argument(
        "--force-paste",
        choices=("listener", "always", "never"),
        default="",
        dest="force_paste_mode",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_silent_dictate_config(args.config)
    overrides: dict[str, object] = {}
    if args.dry_run:
        overrides["dry_run"] = True
    if args.keep_camera_open:
        overrides["keep_camera_open"] = True
    if args.force_cpu:
        overrides["device_override"] = "cpu"
    if args.binding:
        overrides["hotkey"] = cfg.hotkey.model_copy(update={"binding": args.binding})
    if args.force_paste_binding:
        overrides["force_paste_binding"] = args.force_paste_binding
    if args.confidence_floor >= 0.0:
        overrides["confidence_floor"] = args.confidence_floor
    if args.force_paste_mode:
        overrides["force_paste_mode"] = args.force_paste_mode
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    return run_silent_dictate(cfg)


if __name__ == "__main__":
    sys.exit(main())
