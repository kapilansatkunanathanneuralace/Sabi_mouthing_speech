"""Rich console live dBFS meter + VAD state indicator (TICKET-006)."""

from __future__ import annotations

import math
import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

from sabi.capture.microphone import MicConfig, MicrophoneSource


def _meter_bar(peak_dbfs: float, floor_db: float = -60.0, width: int = 40) -> str:
    if math.isinf(peak_dbfs) or peak_dbfs <= floor_db:
        frac = 0.0
    else:
        frac = max(0.0, min(1.0, (peak_dbfs - floor_db) / -floor_db))
    filled = int(frac * width)
    return "#" * filled + "-" * (width - filled)


def _render(src: MicrophoneSource) -> Text:
    peak_dbfs, speaking = src.current_meter()
    st = src.stats
    text = Text()
    text.append(f"backend={src.backend}  ", style="dim")
    text.append(
        f"captured={st.frames_captured} dropped={st.frames_dropped} "
        f"utterances={st.utterances_emitted}\n",
        style="dim",
    )
    text.append("meter ")
    text.append(_meter_bar(peak_dbfs), style=("bold red" if speaking else "green"))
    if math.isinf(peak_dbfs):
        text.append("   -inf dBFS ", style="bold")
    else:
        text.append(f" {peak_dbfs:6.1f} dBFS ", style="bold")
    if speaking:
        text.append(" [SPEECH]", style="bold red")
    else:
        text.append(" [quiet] ", style="dim")
    return text


def run_mic_preview(config: MicConfig | None = None) -> None:
    """Open the microphone and render a live meter until Ctrl+C."""
    cfg = config or MicConfig()
    console = Console()
    with MicrophoneSource(cfg) as src:
        console.print(
            f"mic-preview running (backend={src.backend}); press Ctrl+C to stop.",
        )
        try:
            with Live(_render(src), console=console, refresh_per_second=20) as live:
                while True:
                    time.sleep(0.05)
                    live.update(_render(src))
        except KeyboardInterrupt:
            console.print("[dim]Stopped.[/dim]")
