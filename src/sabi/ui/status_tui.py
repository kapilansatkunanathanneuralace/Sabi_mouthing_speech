"""Rich terminal status UI for dictation pipelines (TICKET-013)."""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from statistics import median
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sabi.pipelines.events import PipelinePhase, PipelineStatusEvent

PENDING_HINT = "[F12 to paste anyway, any other key to discard]"


@dataclass(frozen=True)
class _UtteranceRow:
    pipeline: str
    raw: str
    cleaned: str
    confidence: float
    total_ms: float
    decision: str
    error: str | None


class StatusTUI:
    """Small Rich Live renderer fed by pipeline status + utterance callbacks."""

    def __init__(
        self,
        *,
        console: Console | None = None,
        max_utterances: int = 5,
        latency_window: int = 20,
        refresh_per_second: int = 10,
        clock_ns: Any = time.monotonic_ns,
    ) -> None:
        self.console = console or Console()
        self.max_utterances = max_utterances
        self.latency_window = latency_window
        self.refresh_per_second = refresh_per_second
        self._clock_ns = clock_ns
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._lock = threading.RLock()
        self._utterances: deque[_UtteranceRow] = deque(maxlen=max_utterances)
        self._latencies: deque[float] = deque(maxlen=latency_window)
        self._status = PipelineStatusEvent(
            pipeline="silent",
            mode="idle",
            created_at_ns=self._clock_ns(),
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._live: Live | None = None

    def start(self) -> "StatusTUI":
        """Start the background Live renderer."""

        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sabi-status-tui", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop the background renderer and flush queued events."""

        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None
        self.drain()

    def __enter__(self) -> "StatusTUI":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    def handle_status(self, event: PipelineStatusEvent) -> None:
        """Queue a live pipeline status update."""

        self._queue.put(("status", event))

    def handle_utterance(self, event: Any) -> None:
        """Queue a final utterance event from either pipeline."""

        self._queue.put(("utterance", event))

    def drain(self) -> None:
        """Apply all queued updates. Tests call this before rendering."""

        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == "status":
                self._apply_status(payload)
            else:
                self._apply_utterance(payload)

    def render(self) -> RenderableType:
        """Return the current Rich renderable."""

        self.drain()
        with self._lock:
            return Group(
                self._render_header(),
                self._render_utterances(),
                self._render_footer(),
            )

    def _run(self) -> None:
        with Live(
            self.render(),
            console=self.console,
            refresh_per_second=self.refresh_per_second,
            transient=False,
        ) as live:
            self._live = live
            while not self._stop.wait(1.0 / max(1, self.refresh_per_second)):
                live.update(self.render())
            live.update(self.render())
            self._live = None

    def _apply_status(self, event: PipelineStatusEvent) -> None:
        with self._lock:
            self._status = event

    def _apply_utterance(self, event: Any) -> None:
        pipeline = getattr(event, "pipeline", "silent")
        total_ms = float(getattr(event, "latencies", {}).get("total_ms", 0.0))
        row = _UtteranceRow(
            pipeline=pipeline,
            raw=str(getattr(event, "text_raw", "")),
            cleaned=str(getattr(event, "text_final", "")),
            confidence=float(getattr(event, "confidence", 0.0)),
            total_ms=total_ms,
            decision=str(getattr(event, "decision", "")),
            error=getattr(event, "error", None),
        )
        with self._lock:
            self._utterances.appendleft(row)
            if total_ms > 0.0:
                self._latencies.append(total_ms)
            pipeline = row.pipeline
            if pipeline not in {"silent", "audio", "fused"}:
                pipeline = self._status.pipeline
            self._status = PipelineStatusEvent(
                pipeline=pipeline,
                mode="idle",
                utterance_id=getattr(event, "utterance_id", None),
                hotkey_binding=self._status.hotkey_binding,
                force_paste_binding=self._status.force_paste_binding,
                ollama_ok=self._status.ollama_ok,
                ollama_model=self._status.ollama_model,
                cuda_status=self._status.cuda_status,
                clipboard_restore_deadline_ns=self._status.clipboard_restore_deadline_ns,
                pending_force_paste=row.decision == "withheld_low_confidence",
                created_at_ns=self._clock_ns(),
            )

    def _render_header(self) -> Panel:
        status = self._status
        text = Text()
        text.append(f"Pipeline: {status.pipeline}  ", style="bold cyan")
        text.append("Mode: ")
        text.append(status.mode, style=_mode_style(status.mode))
        text.append(f"  Hotkey: {status.hotkey_binding or '-'}")
        ollama = _ollama_label(status)
        text.append(f"  {ollama}", style=("green" if status.ollama_ok else "red"))
        text.append(f"  CUDA: {status.cuda_status}")
        if status.message:
            text.append(f"  {status.message}", style="yellow")
        return Panel(text, title="Sabi Status", expand=True)

    def _render_utterances(self) -> Panel:
        table = Table(expand=True)
        table.add_column("Pipeline", no_wrap=True)
        table.add_column("Raw")
        table.add_column("Cleaned")
        table.add_column("Conf", justify="right", no_wrap=True)
        table.add_column("Latency", justify="right", no_wrap=True)
        table.add_column("Decision")

        if not self._utterances:
            table.add_row("-", "-", "-", "-", "-", "waiting")
        for row in self._utterances:
            decision = row.decision
            style = ""
            if row.decision == "withheld_low_confidence":
                decision = f"pending {PENDING_HINT}"
                style = "yellow"
            elif row.error or row.decision == "error":
                style = "red"
            table.add_row(
                row.pipeline,
                row.raw or "-",
                row.cleaned or "-",
                f"{row.confidence:.2f}",
                f"{row.total_ms:.0f} ms",
                decision,
                style=style,
            )
        return Panel(table, title=f"Last {self.max_utterances} Utterances", expand=True)

    def _render_footer(self) -> Panel:
        p50, p95 = _rolling_percentiles(list(self._latencies))
        text = Text(f"latency p50={p50:.0f} ms  p95={p95:.0f} ms")
        remaining = self._clipboard_restore_remaining_ms()
        if remaining is not None:
            text.append(f"  original clipboard will be restored in {remaining} ms", style="yellow")
        return Panel(text, title=f"Rolling Latency (last {self.latency_window})", expand=True)

    def _clipboard_restore_remaining_ms(self) -> int | None:
        deadline = self._status.clipboard_restore_deadline_ns
        if deadline is None:
            return None
        remaining = max(0, int((deadline - self._clock_ns()) / 1_000_000))
        return remaining


def _mode_style(mode: PipelinePhase) -> str:
    if mode == "idle":
        return "green"
    if mode == "recording":
        return "bold red"
    if mode in {"decoding", "cleaning"}:
        return "yellow"
    return "bold magenta"


def _ollama_label(status: PipelineStatusEvent) -> str:
    if status.ollama_ok is None:
        return "Ollama: unknown"
    if not status.ollama_ok:
        return "Ollama: offline (raw output)"
    model = status.ollama_model or "unknown"
    return f"Ollama: ok ({model})"


def _rolling_percentiles(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    ordered = sorted(values)
    p50 = float(median(ordered))
    idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return p50, float(ordered[idx])


__all__ = ["PENDING_HINT", "StatusTUI"]
