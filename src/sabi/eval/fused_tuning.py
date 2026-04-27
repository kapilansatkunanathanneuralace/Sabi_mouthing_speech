"""Eval-driven fused tuning recommendations (TICKET-031)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FusedPhraseRow:
    id: str
    run: str
    raw_wer: float
    cleaned_wer: float
    confidence: float
    total_ms: float
    decision: str


@dataclass(frozen=True)
class FusedDiagnosticRow:
    id: str
    prompt: str
    run: str
    asr_text: str
    asr_confidence: float
    vsr_text: str
    vsr_confidence: float
    fusion_mode: str
    fusion_reason: str
    source_asr: float
    source_vsr: float
    face_ratio: float
    vad_coverage: float
    peak_dbfs: float
    cleanup_fallback: bool
    cleanup_reason: str
    flags: tuple[str, ...]


@dataclass(frozen=True)
class Recommendation:
    category: str
    message: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FusedTuningAnalysis:
    report_path: Path
    phrase_count: int
    diagnostic_count: int
    recommendations: tuple[Recommendation, ...]

    def to_markdown(self) -> str:
        lines = [
            "# Fused Tuning Suggestions",
            "",
            f"- Source report: `{self.report_path}`",
            f"- Phrase rows: {self.phrase_count}",
            f"- Diagnostic rows: {self.diagnostic_count}",
            "",
        ]
        if not self.recommendations:
            lines.extend(
                [
                    "## No Strong Recommendations",
                    "",
                    "No clear tuning action was detected from the report.",
                    "",
                ]
            )
            return "\n".join(lines)

        for rec in self.recommendations:
            lines.extend([f"## {rec.category}", "", rec.message, ""])
            lines.append("Evidence:")
            for item in rec.evidence:
                lines.append(f"- {item}")
            lines.append("")
        return "\n".join(lines)


def analyze_fused_tuning_report(path: Path) -> FusedTuningAnalysis:
    """Read a TICKET-030 fused report and produce manual tuning suggestions."""

    text = path.read_text(encoding="utf-8")
    phrase_rows = _parse_phrase_rows(text)
    diagnostic_rows = _parse_diagnostic_rows(text)
    recommendations = _build_recommendations(phrase_rows, diagnostic_rows)
    return FusedTuningAnalysis(
        report_path=path,
        phrase_count=len(phrase_rows),
        diagnostic_count=len(diagnostic_rows),
        recommendations=tuple(recommendations),
    )


def write_suggestions_markdown(analysis: FusedTuningAnalysis, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(analysis.to_markdown(), encoding="utf-8")
    return path


def _parse_phrase_rows(text: str) -> dict[tuple[str, str], FusedPhraseRow]:
    rows = {}
    for row in _parse_table(text, "## Phrase Results"):
        if row.get("pipeline") != "fused":
            continue
        key = (row.get("id", ""), row.get("run", ""))
        rows[key] = FusedPhraseRow(
            id=key[0],
            run=key[1],
            raw_wer=_to_float(row.get("raw_wer")),
            cleaned_wer=_to_float(row.get("cleaned_wer")),
            confidence=_to_float(row.get("confidence")),
            total_ms=_to_float(row.get("total_ms")),
            decision=row.get("decision", ""),
        )
    return rows


def _parse_diagnostic_rows(text: str) -> list[FusedDiagnosticRow]:
    rows = []
    for row in _parse_table(text, "## Fused Diagnostics"):
        source_asr, source_vsr = _parse_source_weights(row.get("source_weights", ""))
        rows.append(
            FusedDiagnosticRow(
                id=row.get("id", ""),
                prompt=row.get("prompt", ""),
                run=row.get("run", ""),
                asr_text=row.get("asr_text", ""),
                asr_confidence=_to_float(row.get("asr_confidence")),
                vsr_text=row.get("vsr_text", ""),
                vsr_confidence=_to_float(row.get("vsr_confidence")),
                fusion_mode=row.get("fusion_mode", ""),
                fusion_reason=row.get("fusion_reason", ""),
                source_asr=source_asr,
                source_vsr=source_vsr,
                face_ratio=_to_float(row.get("face_ratio")),
                vad_coverage=_to_float(row.get("vad_coverage")),
                peak_dbfs=_to_float(row.get("peak_dbfs")),
                cleanup_fallback=_parse_bool(row.get("cleanup_fallback", "")),
                cleanup_reason=row.get("cleanup_reason", ""),
                flags=tuple(
                    part.strip()
                    for part in row.get("flags", "").split(",")
                    if part.strip() and part.strip() != "-"
                ),
            )
        )
    return rows


def _parse_table(text: str, heading: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    try:
        start = lines.index(heading)
    except ValueError:
        return []

    table_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## ") and table_lines:
            break
        if line.startswith("|"):
            table_lines.append(line)
        elif table_lines and line.strip():
            break
    if len(table_lines) < 2:
        return []

    headers = _split_markdown_row(table_lines[0])
    data_lines = table_lines[2:]
    parsed = []
    for line in data_lines:
        cells = _split_markdown_row(line)
        if len(cells) != len(headers):
            continue
        parsed.append(dict(zip(headers, cells, strict=True)))
    return parsed


def _split_markdown_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in body:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def _build_recommendations(
    phrase_rows: dict[tuple[str, str], FusedPhraseRow],
    diagnostic_rows: list[FusedDiagnosticRow],
) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if not diagnostic_rows:
        return [
            Recommendation(
                category="Regenerate Diagnostics",
                message=(
                    "This report does not include `## Fused Diagnostics`. Re-run fused eval after "
                    "TICKET-030 so the recommender can inspect ASR, VSR, fusion, "
                    "and capture signals."
                ),
                evidence=("Missing Fused Diagnostics table.",),
            )
        ]

    high_conf = [
        row
        for row in diagnostic_rows
        if "high_conf_high_wer" in row.flags
        or _phrase_for(row, phrase_rows).cleaned_wer >= 0.5
        and _phrase_for(row, phrase_rows).confidence >= 0.95
    ]
    if high_conf:
        recs.append(
            Recommendation(
                category="Confidence Calibration",
                message=(
                    "Likely action: lower trust in fused confidence before paste gating. Several "
                    "phrases are severe WER failures despite very high confidence."
                ),
                evidence=_phrase_evidence(high_conf, phrase_rows, limit=5),
            )
        )

    fallback_rows = [row for row in diagnostic_rows if row.cleanup_fallback]
    if _ratio(fallback_rows, diagnostic_rows) >= 0.25:
        recs.append(
            Recommendation(
                category="Cleanup / Ollama",
                message=(
                    "Likely action: check Ollama availability or increase cleanup timeout before "
                    "judging prompt quality. The report is often measuring raw fusion output."
                ),
                evidence=_cleanup_evidence(fallback_rows, limit=5),
            )
        )

    worsened = [
        row
        for row in diagnostic_rows
        if _phrase_for(row, phrase_rows).cleaned_wer > _phrase_for(row, phrase_rows).raw_wer + 0.05
    ]
    if worsened:
        recs.append(
            Recommendation(
                category="Cleanup Prompt",
                message=(
                    "Likely action: compare cleanup prompt versions or inspect prompt behavior. "
                    "Cleanup made WER worse on at least one phrase."
                ),
                evidence=_phrase_evidence(worsened, phrase_rows, limit=5),
            )
        )

    asr_good_vsr_bad = [
        row
        for row in diagnostic_rows
        if _is_disagreement(row)
        and row.source_asr >= 0.6
        and _phrase_for(row, phrase_rows).cleaned_wer <= 0.25
    ]
    if asr_good_vsr_bad:
        recs.append(
            Recommendation(
                category="Capture / VSR",
                message=(
                    "Likely action: improve camera framing, lighting, lip ROI, or VSR settings. "
                    "ASR appears to be carrying successful fused outputs while VSR disagrees."
                ),
                evidence=_modality_evidence(asr_good_vsr_bad, phrase_rows, limit=5),
            )
        )

    vsr_good_asr_bad = [
        row
        for row in diagnostic_rows
        if _is_disagreement(row)
        and row.source_vsr >= 0.6
        and _phrase_for(row, phrase_rows).cleaned_wer <= 0.25
    ]
    if vsr_good_asr_bad:
        recs.append(
            Recommendation(
                category="Microphone / ASR",
                message=(
                    "Likely action: improve microphone input, room noise, or ASR settings. "
                    "VSR appears to be carrying successful fused outputs while ASR disagrees."
                ),
                evidence=_modality_evidence(vsr_good_asr_bad, phrase_rows, limit=5),
            )
        )

    fusion_failures = [
        row
        for row in diagnostic_rows
        if _phrase_for(row, phrase_rows).cleaned_wer >= 0.5
        and (
            "alignment_below_threshold" in row.fusion_reason
            or row.fusion_mode in {"audio_primary", "vsr_primary"}
        )
    ]
    if fusion_failures:
        recs.append(
            Recommendation(
                category="Fusion Config",
                message=(
                    "Likely action: run a small A/B with `audio_primary` and `vsr_primary`, then "
                    "adjust fusion thresholds. Severe failures cluster around hard source choices."
                ),
                evidence=_modality_evidence(fusion_failures, phrase_rows, limit=5),
            )
        )

    capture_rows = [
        row
        for row in diagnostic_rows
        if row.face_ratio < 0.8 or row.vad_coverage < 0.7 or row.peak_dbfs < -35.0
    ]
    if capture_rows:
        recs.append(
            Recommendation(
                category="Capture Quality",
                message=(
                    "Likely action: improve the recording setup before model tuning. "
                    "Some rows show "
                    "low face visibility, low VAD coverage, or very quiet audio."
                ),
                evidence=_capture_evidence(capture_rows, limit=5),
            )
        )

    latency = _latency_recommendation(phrase_rows, diagnostic_rows)
    if latency is not None:
        recs.append(latency)

    if _has_model_finetuning_signal(diagnostic_rows, phrase_rows):
        disagreement_count = sum(1 for row in diagnostic_rows if _is_disagreement(row))
        severe_count = sum(
            1
            for row in diagnostic_rows
            if _phrase_for(row, phrase_rows).cleaned_wer >= 0.5
        )
        recs.append(
            Recommendation(
                category="Model Fine-Tuning Candidate",
                message=(
                    "Likely action: use this report as evidence for the VSR fine-tuning research "
                    "ticket, but do not train yet. Repeated modality disagreement and severe WER "
                    "suggest there may be a personal adaptation opportunity."
                ),
                evidence=(
                    f"{disagreement_count} rows show ASR/VSR disagreement.",
                    f"{severe_count} rows have severe WER.",
                ),
            )
        )

    return recs


def _phrase_for(
    row: FusedDiagnosticRow,
    phrase_rows: dict[tuple[str, str], FusedPhraseRow],
) -> FusedPhraseRow:
    return phrase_rows.get(
        (row.id, row.run),
        FusedPhraseRow(row.id, row.run, 0.0, 0.0, 0.0, 0.0, "-"),
    )


def _ratio(part: list[object], whole: list[object]) -> float:
    return len(part) / len(whole) if whole else 0.0


def _is_disagreement(row: FusedDiagnosticRow) -> bool:
    return "asr_vsr_disagree" in row.flags


def _phrase_evidence(
    rows: list[FusedDiagnosticRow],
    phrase_rows: dict[tuple[str, str], FusedPhraseRow],
    *,
    limit: int,
) -> tuple[str, ...]:
    evidence = []
    for row in rows[:limit]:
        phrase = _phrase_for(row, phrase_rows)
        evidence.append(
            f"{row.id} run {row.run}: cleaned_wer={phrase.cleaned_wer:.3f}, "
            f"confidence={phrase.confidence:.2f}, flags={','.join(row.flags) or '-'}"
        )
    return tuple(evidence)


def _cleanup_evidence(rows: list[FusedDiagnosticRow], *, limit: int) -> tuple[str, ...]:
    reasons: dict[str, int] = {}
    for row in rows:
        reason = row.cleanup_reason or "fallback"
        reasons[reason] = reasons.get(reason, 0) + 1
    top = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return tuple(f"{reason}: {count} row(s)" for reason, count in top)


def _modality_evidence(
    rows: list[FusedDiagnosticRow],
    phrase_rows: dict[tuple[str, str], FusedPhraseRow],
    *,
    limit: int,
) -> tuple[str, ...]:
    evidence = []
    for row in rows[:limit]:
        phrase = _phrase_for(row, phrase_rows)
        evidence.append(
            f"{row.id}: mode={row.fusion_mode}, reason={row.fusion_reason}, "
            f"weights=asr={row.source_asr:.2f}/vsr={row.source_vsr:.2f}, "
            f"cleaned_wer={phrase.cleaned_wer:.3f}"
        )
    return tuple(evidence)


def _capture_evidence(rows: list[FusedDiagnosticRow], *, limit: int) -> tuple[str, ...]:
    return tuple(
        f"{row.id}: face_ratio={row.face_ratio:.2f}, vad_coverage={row.vad_coverage:.2f}, "
        f"peak_dbfs={row.peak_dbfs:.1f}"
        for row in rows[:limit]
    )


def _latency_recommendation(
    phrase_rows: dict[tuple[str, str], FusedPhraseRow],
    diagnostic_rows: list[FusedDiagnosticRow],
) -> Recommendation | None:
    totals = [row.total_ms for row in phrase_rows.values() if row.total_ms > 0]
    if not totals:
        return None
    median_total = sorted(totals)[len(totals) // 2]
    if median_total < 5000.0:
        return None
    vsr_heavy = sum(1 for row in diagnostic_rows if row.vsr_confidence >= 0.95)
    return Recommendation(
        category="Latency",
        message=(
            "Likely action: inspect per-stage latency before tuning model behavior. Median total "
            "latency is high enough that VSR/ROI/cleanup optimization may matter for demo feel."
        ),
        evidence=(
            f"median_total_ms={median_total:.1f}",
            f"high_vsr_confidence_rows={vsr_heavy}",
        ),
    )


def _has_model_finetuning_signal(
    diagnostic_rows: list[FusedDiagnosticRow],
    phrase_rows: dict[tuple[str, str], FusedPhraseRow],
) -> bool:
    disagreements = sum(1 for row in diagnostic_rows if _is_disagreement(row))
    severe = sum(
        1 for row in diagnostic_rows if _phrase_for(row, phrase_rows).cleaned_wer >= 0.5
    )
    return disagreements >= max(3, len(diagnostic_rows) // 2) and severe >= 2


def _parse_source_weights(value: str) -> tuple[float, float]:
    asr = 0.0
    vsr = 0.0
    for part in value.split():
        if part.startswith("asr="):
            asr = _to_float(part.removeprefix("asr="))
        elif part.startswith("vsr="):
            vsr = _to_float(part.removeprefix("vsr="))
    return asr, vsr


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"yes", "true", "1"}


def _to_float(value: object) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "FusedDiagnosticRow",
    "FusedPhraseRow",
    "FusedTuningAnalysis",
    "Recommendation",
    "analyze_fused_tuning_report",
    "write_suggestions_markdown",
]
