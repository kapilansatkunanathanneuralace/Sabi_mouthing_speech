from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sabi.sidecar.dispatcher import SidecarDispatcher
from sabi.sidecar.handlers.calibration import CalibrationSession, register_calibration_handlers


def _phrases(path: Path) -> None:
    rows = [
        {"id": "one", "text": "One bright sentence."},
        {"id": "two", "text": "Two calm words."},
        {"id": "three", "text": "Three sample sounds."},
        {"id": "four", "text": "Four useful checks."},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_calibration_plan_returns_three_random_sentence_samples(tmp_path: Path) -> None:
    source = tmp_path / "phrases.jsonl"
    _phrases(source)
    session = CalibrationSession()

    result = session.plan({"phrases_path": str(source), "seed": "stable"}, lambda *_args: None)

    assert len(result["samples"]) == 3
    assert {sample["mode"] for sample in result["samples"]} == {"optional"}
    assert all(sample["text"] for sample in result["samples"])


def test_calibration_run_returns_structured_success() -> None:
    notifications = []
    session = CalibrationSession()

    result = session.run(
        {"sample_id": "one", "text": "One bright sentence."},
        lambda method, params=None: notifications.append((method, params)),
    )

    assert result["ok"] is True
    assert result["status"] == "passed"
    assert result["sample_id"] == "one"
    assert result["quality"]["non_empty_output"] is True
    assert notifications == [("calibration.status", {"sample_id": "one", "status": "running"})]


def test_calibration_run_reports_failure() -> None:
    session = CalibrationSession()

    result = session.run(
        {"sample_id": "one", "text": "One bright sentence.", "force_fail": True},
        lambda *_args: None,
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "quality" in result["error"]


def test_calibration_cancel_returns_structured_result() -> None:
    notifications = []
    session = CalibrationSession()
    session.active_sample_id = "one"

    result = session.cancel({}, lambda method, params=None: notifications.append((method, params)))

    assert result == {"cancelled": True, "sample_id": "one"}
    assert notifications == [
        ("calibration.status", {"sample_id": "one", "status": "cancelled"})
    ]


def test_calibration_handlers_dispatch_contract(tmp_path: Path) -> None:
    source = tmp_path / "phrases.jsonl"
    _phrases(source)
    dispatcher = SidecarDispatcher()
    register_calibration_handlers(dispatcher)

    result = asyncio.run(
        dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "calibration.plan",
                "params": {"phrases_path": str(source), "seed": "stable"},
            }
        )
    )

    assert result.response is not None
    assert result.response["result"]["samples"][0]["sample_id"]
