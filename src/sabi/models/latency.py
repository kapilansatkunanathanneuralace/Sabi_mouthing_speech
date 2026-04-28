"""Shared helper for appending rows to ``reports/latency-log.md``.

Both :mod:`sabi.models.vsr.smoke` (TICKET-005) and
:mod:`sabi.models.asr_smoke` (TICKET-007) use this helper so the table
stays uniform as new tickets land.
"""

from __future__ import annotations

from pathlib import Path

from sabi.runtime.paths import reports_dir

LATENCY_LOG = reports_dir() / "latency-log.md"

_HEADER = (
    "# Latency log\n\n"
    "Append one row per pipeline run (see tickets/README.md).\n\n"
    "| ticket | hardware | stage | p50_ms | p95_ms | samples | notes |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
)


def append_latency_row(
    ticket: str,
    hardware: str,
    stage: str,
    latency_ms: float,
    samples: int,
    notes: str,
    *,
    p95_ms: float | None = None,
    log_path: Path | None = None,
) -> None:
    """Append one row to ``reports/latency-log.md``, creating the file if needed."""
    path = log_path if log_path is not None else LATENCY_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_HEADER, encoding="utf-8")
    p95_cell = f"{p95_ms:.1f}" if p95_ms is not None else "-"
    row = (
        f"| {ticket} | {hardware} | {stage} | {latency_ms:.1f} | {p95_cell} "
        f"| {samples} | {notes} |\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(row)


__all__ = ["append_latency_row", "LATENCY_LOG"]
