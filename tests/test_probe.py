"""TICKET-002: import smoke and probe unit tests (no real hardware in monkeypatch tests)."""

from __future__ import annotations

import importlib

import pytest
from rich.console import Console

from sabi.probe import run_probe


@pytest.mark.parametrize(
    "module",
    [
        "cv2",
        "numpy",
        "torch",
        "mediapipe",
        "faster_whisper",
        "sounddevice",
        "webrtcvad",
        "pyautogui",
        "pyperclip",
        "keyboard",
        "httpx",
        "pydantic",
        "rich",
        "typer",
    ],
)
def test_declared_dependency_imports(module: str) -> None:
    """Fails fast if the environment is missing a pinned runtime dependency."""
    importlib.import_module(module)


def test_run_probe_all_patched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sabi.probe._print_torch", lambda _c: None)
    monkeypatch.setattr(
        "sabi.probe._import_matrix_rows",
        lambda: [("dummy", True, "")],
    )
    monkeypatch.setattr("sabi.probe._print_import_table", lambda _c, _rows: True)
    monkeypatch.setattr("sabi.probe._probe_webcam", lambda _c, camera_index=0: True)
    monkeypatch.setattr("sabi.probe._probe_audio", lambda _c: True)
    code = run_probe(console=Console(record=True, width=120))
    assert code == 0


def test_probe_webcam_privacy_remediation_in_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the camera cannot open, output must mention privacy (acceptance criterion)."""

    class BadCapture:
        def isOpened(self) -> bool:
            return False

        def read(self) -> tuple[bool, None]:
            return False, None

        def release(self) -> None:
            return None

    import sabi.probe as probe_mod

    monkeypatch.setattr(probe_mod.cv2, "VideoCapture", lambda *a, **k: BadCapture())
    monkeypatch.setattr("sabi.probe._print_torch", lambda _c: None)
    monkeypatch.setattr(
        "sabi.probe._import_matrix_rows",
        lambda: [("dummy", True, "")],
    )
    monkeypatch.setattr("sabi.probe._print_import_table", lambda _c, _rows: True)
    monkeypatch.setattr("sabi.probe._probe_audio", lambda _c: True)

    console = Console(record=True, width=120)
    code = run_probe(console=console)
    text = console.export_text()
    assert code == 1
    assert "Privacy" in text or "privacy" in text


def test_run_probe_webcam_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sabi.probe._print_torch", lambda _c: None)
    monkeypatch.setattr(
        "sabi.probe._import_matrix_rows",
        lambda: [("dummy", True, "")],
    )
    monkeypatch.setattr("sabi.probe._print_import_table", lambda _c, _rows: True)
    monkeypatch.setattr("sabi.probe._probe_webcam", lambda _c, camera_index=0: False)
    monkeypatch.setattr("sabi.probe._probe_audio", lambda _c: True)
    code = run_probe(console=Console(record=True, width=120))
    assert code == 1
