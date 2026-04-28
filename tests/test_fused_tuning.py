"""TICKET-031: fused tuning recommendation tests."""

from __future__ import annotations

from pathlib import Path

from sabi.eval.fused_tuning import analyze_fused_tuning_report, write_suggestions_markdown


def _md_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _sep(count: int) -> str:
    return _md_row(["---"] * count)


def _report(rows: str) -> str:
    phrase_headers = [
        "id",
        "pipeline",
        "run",
        "raw_text",
        "cleaned_text",
        "raw_wer",
        "cleaned_wer",
        "confidence",
        "total_ms",
        "decision",
    ]
    diagnostic_headers = [
        "id",
        "prompt",
        "run",
        "asr_text",
        "asr_confidence",
        "vsr_text",
        "vsr_confidence",
        "fusion_mode",
        "fusion_reason",
        "source_weights",
        "per_word_origin",
        "face_ratio",
        "vad_coverage",
        "peak_dbfs",
        "cleanup_prompt",
        "cleanup_fallback",
        "cleanup_reason",
        "flags",
    ]
    diagnostics = [
        [
            "high",
            "v1",
            "0",
            "birch canoe",
            "0.80",
            "bunkers small",
            "1.00",
            "vsr_primary",
            "alignment_below_threshold",
            "asr=0.00 vsr=1.00",
            "vsr vsr",
            "1.00",
            "1.00",
            "-14.0",
            "v1",
            "yes",
            "http_error: ReadTimeout",
            "high_conf_high_wer, asr_vsr_disagree, cleanup_fallback",
        ],
        [
            "asr_good",
            "v1",
            "0",
            "hello world",
            "0.85",
            "yellow word",
            "0.45",
            "audio_primary",
            "auto -> audio_primary",
            "asr=0.80 vsr=0.20",
            "asr both",
            "1.00",
            "1.00",
            "-12.0",
            "v1",
            "no",
            "-",
            "asr_vsr_disagree",
        ],
        [
            "vsr_good",
            "v1",
            "0",
            "wrong audio",
            "0.30",
            "hello world",
            "0.95",
            "vsr_primary",
            "asr below floor and vsr above floor",
            "asr=0.10 vsr=0.90",
            "vsr vsr",
            "1.00",
            "1.00",
            "-12.0",
            "v1",
            "no",
            "-",
            "asr_vsr_disagree",
        ],
        [
            "capture",
            "v1",
            "0",
            "quiet audio",
            "0.30",
            "quiet video",
            "0.30",
            "audio_primary",
            "auto -> audio_primary",
            "asr=0.50 vsr=0.50",
            "both both",
            "0.50",
            "0.40",
            "-40.0",
            "v1",
            "no",
            "-",
            "low_face_ratio, low_vad_coverage, low_audio_peak",
        ],
    ]
    diagnostic_rows = "\n".join(_md_row(row) for row in diagnostics)
    return f"""# Sabi PoC Eval Report

## Summary

| pipeline | raw_wer | cleaned_wer | total_p50_ms | total_p95_ms | total_max_ms |
| --- | --- | --- | --- | --- | --- |
| fused | 0.500 | 0.500 | 6000.0 | 7000.0 | 8000.0 |

## Phrase Results

{_md_row(phrase_headers)}
{_sep(len(phrase_headers))}
{rows}

## Fused Diagnostics

{_md_row(diagnostic_headers)}
{_sep(len(diagnostic_headers))}
{diagnostic_rows}

## Known Failure Modes
"""


def test_analyze_fused_tuning_report_recommends_major_categories(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        _report(
            "\n".join(
                [
                    "| high | fused | 0 | bad | bad | 1.000 | 1.000 | 1.00 | 6500.0 | dry_run |",
                    _md_row(
                        [
                            "asr_good",
                            "fused",
                            "0",
                            "hello world",
                            "hello world",
                            "0.000",
                            "0.000",
                            "0.85",
                            "6200.0",
                            "dry_run",
                        ]
                    ),
                    _md_row(
                        [
                            "vsr_good",
                            "fused",
                            "0",
                            "hello world",
                            "hello world",
                            "0.000",
                            "0.000",
                            "0.95",
                            "6100.0",
                            "dry_run",
                        ]
                    ),
                    "| capture | fused | 0 | bad | bad | 0.500 | 0.500 | 0.50 | 6300.0 | dry_run |",
                ]
            )
        ),
        encoding="utf-8",
    )

    analysis = analyze_fused_tuning_report(report)
    categories = {rec.category for rec in analysis.recommendations}

    assert "Confidence Calibration" in categories
    assert "Cleanup / Ollama" in categories
    assert "Capture / VSR" in categories
    assert "Microphone / ASR" in categories
    assert "Capture Quality" in categories
    assert "Latency" in categories
    assert "Model Fine-Tuning Candidate" in categories


def test_analyze_fused_tuning_report_handles_missing_diagnostics(tmp_path: Path) -> None:
    report = tmp_path / "old-report.md"
    report.write_text("# Sabi PoC Eval Report\n\n## Phrase Results\n", encoding="utf-8")

    analysis = analyze_fused_tuning_report(report)

    assert analysis.recommendations[0].category == "Regenerate Diagnostics"


def test_write_suggestions_markdown(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        _report("| high | fused | 0 | bad | bad | 1.000 | 1.000 | 1.00 | 6500.0 | dry_run |"),
        encoding="utf-8",
    )
    analysis = analyze_fused_tuning_report(report)
    out = tmp_path / "suggestions.md"

    write_suggestions_markdown(analysis, out)

    text = out.read_text(encoding="utf-8")
    assert "# Fused Tuning Suggestions" in text
    assert "Confidence Calibration" in text
