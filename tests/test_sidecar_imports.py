from __future__ import annotations

import importlib
import sys

from rich.console import Console


def test_default_dispatcher_does_not_import_cv2_or_torch_at_startup() -> None:
    sys.modules.pop("cv2", None)
    sys.modules.pop("torch", None)

    dispatcher_module = importlib.import_module("sabi.sidecar.dispatcher")
    dispatcher_module.make_default_dispatcher()

    assert "cv2" not in sys.modules
    assert "torch" not in sys.modules


def test_collect_probe_results_does_not_write_human_output_to_stdout(
    monkeypatch,
    capsys,
) -> None:
    probe = importlib.import_module("sabi.probe")

    monkeypatch.setattr(probe, "_import_matrix_rows", lambda: [])
    monkeypatch.setattr(
        probe,
        "_probe_webcam",
        lambda console, camera_index=0: _print_probe_line(console, "Webcam: PASS"),
    )
    monkeypatch.setattr(
        probe,
        "_probe_audio",
        lambda console: _print_probe_line(console, "Audio input: PASS"),
    )

    result = probe.collect_probe_results()

    assert result["webcam"]["output"] == "Webcam: PASS"
    assert result["audio"]["output"] == "Audio input: PASS"
    assert capsys.readouterr().out == ""


def _print_probe_line(console: Console, message: str) -> bool:
    console.print(message)
    return True
