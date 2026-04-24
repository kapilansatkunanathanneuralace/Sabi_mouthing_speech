"""Audio-dictation pipeline entry point (TICKET-012).

Equivalent to ``python -m sabi dictate``; this script exists so you can
run it without installing the ``sabi`` console entry point. See
``docs/audio-dictate.md`` for CLI flags, JSONL schema, and latency-budget
caveats.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sabi.pipelines import load_audio_dictate_config, run_audio_dictate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--mode",
        default="",
        help="push-to-talk|push_to_talk|vad (empty = use config).",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-cpu", action="store_true")
    parser.add_argument(
        "--ptt-open-per-trigger",
        action="store_true",
        help="Open the microphone per PTT trigger instead of preopening on start.",
    )
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

    cfg = load_audio_dictate_config(args.config)
    overrides: dict[str, object] = {}
    if args.mode:
        normalized = args.mode.strip().lower().replace("-", "_")
        if normalized not in {"push_to_talk", "vad"}:
            parser.error(
                f"--mode must be 'push-to-talk' or 'vad', got {args.mode!r}"
            )
        overrides["trigger_mode"] = normalized
    if args.dry_run:
        overrides["dry_run"] = True
    if args.ptt_open_per_trigger:
        overrides["ptt_open_per_trigger"] = True
    if args.force_cpu:
        overrides["device_override"] = "cpu"
    if args.binding:
        overrides["hotkey"] = cfg.hotkey.model_copy(update={"binding": args.binding})
    if args.force_paste_binding:
        overrides["force_paste_binding"] = args.force_paste_binding
    if args.confidence_floor >= 0.0:
        overrides["confidence_floor"] = args.confidence_floor
    if args.force_paste_mode:
        overrides["force_paste_mode_ptt"] = args.force_paste_mode
        overrides["force_paste_mode_vad"] = args.force_paste_mode
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    return run_audio_dictate(cfg)


if __name__ == "__main__":
    sys.exit(main())
