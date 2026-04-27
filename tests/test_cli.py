"""Lightweight CLI contract tests."""

from __future__ import annotations

from typer.testing import CliRunner

from sabi.cli import app


def test_dictation_commands_advertise_ui_option() -> None:
    runner = CliRunner()

    silent = runner.invoke(app, ["silent-dictate", "--help"])
    audio = runner.invoke(app, ["dictate", "--help"])

    assert silent.exit_code == 0
    assert audio.exit_code == 0
    assert "--ui" in silent.output
    assert "tui|none" in silent.output
    assert "--ui" in audio.output
    assert "tui|none" in audio.output
    assert "--cleanup-prompt" in silent.output
    assert "--cleanup-prompt" in audio.output


def test_eval_command_advertises_eval_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["eval", "--help"])

    assert result.exit_code == 0
    assert "--dataset" in result.output
    assert "--pipeline" in result.output
    assert "--runs" in result.output
    assert "--cleanup-prompt" in result.output


def test_cleanup_smoke_advertises_prompt_version() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["cleanup-smoke", "--help"])

    assert result.exit_code == 0
    assert "--prompt-version" in result.output


def test_fusion_smoke_advertises_text_shortcuts() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["fusion-smoke", "--help"])

    assert result.exit_code == 0
    assert "--asr-text" in result.output
    assert "--vsr-text" in result.output
    assert "--asr-conf" in result.output


def test_fused_dictate_advertises_ui_and_fusion_flags() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["fused-dictate", "--help"])

    assert result.exit_code == 0
    assert "--ui" in result.output
    assert "tui|none" in result.output
    assert "--mode" in result.output
    assert "--no-parallel" in result.output
    assert "--cleanup-prompt" in result.output


def test_collect_fused_eval_advertises_collection_flags() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["collect-fused-eval", "--help"])

    assert result.exit_code == 0
    assert "--phrases" in result.output
    assert "--out-dir" in result.output
    assert "--retry" in result.output
    assert "--skip-existing" in result.output
    assert "--camera-name" in result.output
    assert "--mic-name" in result.output
    assert "--dry-run" in result.output


def test_fused_eval_check_advertises_dataset_option() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["fused-eval-check", "--help"])

    assert result.exit_code == 0
    assert "--dataset" in result.output
    assert "Validate a fused eval dataset" in result.output


def test_fused_eval_reset_advertises_safety_flag() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["fused-eval-reset", "--help"])

    assert result.exit_code == 0
    assert "--dataset" in result.output
    assert "--yes" in result.output
    assert "Reset generated fused eval media" in result.output


def test_fused_tuning_suggest_advertises_report_and_out() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["fused-tuning-suggest", "--help"])

    assert result.exit_code == 0
    assert "--report" in result.output
    assert "--out" in result.output
    assert "Suggest manual fused tuning actions" in result.output
