"""Fusion mode A/B offline eval (TICKET-037)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sabi.cleanup.ollama import PromptVersion
from sabi.eval.harness import (
    EvalConfig,
    EvalRecord,
    EvalResult,
    run_eval,
)
from sabi.eval.harness import _git_sha as eval_git_sha
from sabi.eval.harness import _hardware_summary as eval_hardware_summary
from sabi.pipelines.fused_dictate import FusedDictateConfig

_ALLOWED_MODES: frozenset[str] = frozenset({"auto", "audio_primary", "vsr_primary"})


def parse_fusion_modes(value: str) -> tuple[str, ...]:
    """Parse and validate a comma-separated fusion mode list."""

    parts = tuple(p.strip().lower() for p in value.split(",") if p.strip())
    if not parts:
        raise ValueError("--modes must list at least one of auto,audio_primary,vsr_primary")
    unknown = [p for p in parts if p not in _ALLOWED_MODES]
    if unknown:
        raise ValueError(f"unknown fusion mode(s): {', '.join(unknown)}")
    if len(set(parts)) != len(parts):
        raise ValueError("--modes contains duplicate entries")
    return parts


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    head = "| " + " | ".join(headers) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _high_conf_high_wer_count(records: Iterable[EvalRecord]) -> int:
    return sum(
        1
        for r in records
        if r.event.confidence >= 0.95 and r.cleaned_wer >= 0.5
    )


def _records_for_phrase_run(
    records: tuple[EvalRecord, ...], phrase_id: str, run_index: int
) -> list[EvalRecord]:
    return [r for r in records if r.phrase.id == phrase_id and r.run_index == run_index]


def _best_mode_for_phrase(
    by_mode: dict[str, EvalResult],
    modes: tuple[str, ...],
    phrase_id: str,
    run_index: int = 0,
) -> tuple[str, dict[str, float]]:
    """Return mode with lowest cleaned_wer; ties break on raw_wer then mode order."""

    scores: dict[str, tuple[float, float]] = {}
    for m in modes:
        recs = _records_for_phrase_run(by_mode[m].records, phrase_id, run_index)
        if not recs:
            continue
        r0 = recs[0]
        scores[m] = (r0.cleaned_wer, r0.raw_wer)
    if not scores:
        return "-", {}

    def sort_key(item: tuple[str, tuple[float, float]]) -> tuple[float, float, int]:
        mode, (cw, rw) = item
        return (cw, rw, modes.index(mode))

    best = min(scores.items(), key=sort_key)[0]
    return best, {m: scores[m][0] for m in scores}


def render_fusion_mode_ab_report(
    *,
    dataset_path: Path,
    modes: tuple[str, ...],
    runs: int,
    warmups: int,
    cleanup_prompts: tuple[PromptVersion, ...],
    by_mode: dict[str, EvalResult],
    elapsed_ms: float,
) -> str:
    """Build a single markdown report comparing fusion modes."""

    lines: list[str] = [
        "# Sabi Fusion Mode A/B Eval Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Git SHA: {eval_git_sha()}",
        f"- Hardware: {eval_hardware_summary()}",
        f"- Dataset: `{dataset_path}`",
        f"- Modes: {', '.join(modes)}",
        f"- Runs per phrase: {runs}",
        f"- Warmups per phrase: {warmups}",
        f"- Cleanup prompts: {', '.join(cleanup_prompts)}",
        f"- Total wall time: {elapsed_ms:.1f} ms",
        "",
        "## Summary by mode",
        "",
    ]

    sum_rows = []
    for m in modes:
        res = by_mode[m]
        stats = res.summary_stats["fused"]
        recs = list(res.records)
        hchw = _high_conf_high_wer_count(recs)
        sum_rows.append(
            [
                m,
                f"{stats['raw_wer']:.3f}",
                f"{stats['cleaned_wer']:.3f}",
                f"{stats.get('cleanup_fallback_count', 0):.0f}",
                f"{stats.get('cleanup_fallback_rate', 0.0):.2%}",
                f"{hchw}",
                f"{stats['total_p50']:.1f}",
                f"{stats['total_p95']:.1f}",
                f"{stats['total_max']:.1f}",
            ]
        )
    lines.append(
        _md_table(
            [
                "mode",
                "mean_raw_wer",
                "mean_cleaned_wer",
                "cleanup_fallbacks",
                "cleanup_fallback_rate",
                "high_conf_high_wer_rows",
                "total_p50_ms",
                "total_p95_ms",
                "total_max_ms",
            ],
            sum_rows,
        )
    )
    lines.extend(["", "## Per-stage latency by mode (p50 ms)", ""])

    stage_rows: list[list[str]] = []
    stages = ("capture_ms", "roi_ms", "vsr_ms", "asr_ms", "fusion_ms", "cleanup_ms", "total_ms")
    for m in modes:
        st = by_mode[m].stage_stats
        row = [m]
        for stage in stages:
            key = ("fused", stage)
            if key in st:
                row.append(f"{st[key]['p50']:.1f}")
            else:
                row.append("-")
        stage_rows.append(row)
    lines.append(
        _md_table(
            ["mode", *stages],
            stage_rows,
        )
    )

    phrase_ids = sorted({r.phrase.id for r in by_mode[modes[0]].records})
    phrase_rows: list[list[str]] = []
    severe: list[tuple[str, str, dict[str, float], float, str]] = []

    for pid in phrase_ids:
        best, cleaned_by_mode = _best_mode_for_phrase(by_mode, modes, pid, 0)
        if not cleaned_by_mode:
            continue
        cvals = [cleaned_by_mode[m] for m in modes if m in cleaned_by_mode]
        spread = max(cvals) - min(cvals) if cvals else 0.0
        row = [pid, best, f"{spread:.3f}"]
        for m in modes:
            recs = _records_for_phrase_run(by_mode[m].records, pid, 0)
            if recs:
                r = recs[0]
                row.append(f"{r.cleaned_wer:.3f}")
            else:
                row.append("-")
        phrase_rows.append(row)
        if spread >= 0.25 or any(v >= 0.5 for v in cvals):
            worst_m = max(cleaned_by_mode, key=cleaned_by_mode.get)
            wr = _records_for_phrase_run(by_mode[worst_m].records, pid, 0)[0]
            fusion = wr.event.fusion if isinstance(wr.event.fusion, dict) else {}
            reason = str(fusion.get("mode_reason") or "")
            severe.append((pid, worst_m, cleaned_by_mode, spread, reason))

    lines.extend(
        [
            "",
            "## Per-phrase cleaned WER by mode",
            "",
            "Best mode is the lowest `cleaned_wer` for that phrase (tie-break: lower `raw_wer`, "
            "then mode order as listed).",
            "",
        ]
    )
    hdr = ["phrase_id", "best_mode", "cleaned_wer_spread", *[f"cleaned_wer_{m}" for m in modes]]
    lines.append(_md_table(hdr, phrase_rows))

    lines.extend(
        [
            "",
            "## Severe mode disagreements",
            "",
            "Phrases where `cleaned_wer` spread across modes is at least **0.25**, or any mode "
            "has `cleaned_wer` ≥ **0.5**.",
            "",
        ]
    )
    if not severe:
        lines.append("- None observed for this dataset and run settings.")
    else:
        sev_rows = []
        for pid, worst_m, cleaned_by, spread, reason in severe:
            detail = ", ".join(f"{m}={cleaned_by[m]:.3f}" for m in modes if m in cleaned_by)
            sev_rows.append([pid, worst_m, f"{spread:.3f}", _cell(detail), _cell(reason)])
        sev_headers = [
            "phrase_id",
            "worst_mode",
            "spread",
            "cleaned_wer_by_mode",
            "worst_mode_fusion_reason",
        ]
        lines.append(_md_table(sev_headers, sev_rows))

    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True)
class FusionModeAbConfig:
    """Configuration for a fusion-mode A/B eval sweep."""

    dataset_path: Path
    modes: tuple[str, ...] = ("auto", "audio_primary", "vsr_primary")
    runs: int = 1
    warmups: int = 1
    cleanup_prompts: tuple[PromptVersion, ...] = ("v1",)
    cleanup_preflight: bool = True
    cleanup_preflight_first_mode_only: bool = True
    fused_base: FusedDictateConfig | None = None
    out_path: Path | None = None


def run_fusion_mode_ab_eval(
    config: FusionModeAbConfig,
    *,
    fused_runner_factory: Callable[[FusedDictateConfig], Any] | None = None,
) -> Path:
    """Run fused eval once per fusion mode and write a combined markdown report."""

    base = config.fused_base or FusedDictateConfig()
    out = config.out_path
    if out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        out = Path("reports") / f"fusion-mode-ab-{stamp}.md"

    by_mode: dict[str, EvalResult] = {}
    t0 = time.perf_counter()
    for i, mode in enumerate(config.modes):
        fusion_cfg = base.fusion.model_copy(update={"mode": mode})
        fused_cfg = base.model_copy(update={"fusion": fusion_cfg})
        pre = config.cleanup_preflight
        if config.cleanup_preflight_first_mode_only and i > 0:
            pre = False
        ev = EvalConfig(
            dataset_path=config.dataset_path,
            runs=config.runs,
            warmups=config.warmups,
            pipeline="fused",
            cleanup_prompts=config.cleanup_prompts,
            cleanup_preflight=pre,
            fused_config=fused_cfg,
            write_output=False,
        )
        runner = fused_runner_factory(fused_cfg) if fused_runner_factory else None
        by_mode[mode] = run_eval(ev, fused_runner=runner)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    body = render_fusion_mode_ab_report(
        dataset_path=config.dataset_path,
        modes=config.modes,
        runs=config.runs,
        warmups=config.warmups,
        cleanup_prompts=config.cleanup_prompts,
        by_mode=by_mode,
        elapsed_ms=elapsed_ms,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return out
