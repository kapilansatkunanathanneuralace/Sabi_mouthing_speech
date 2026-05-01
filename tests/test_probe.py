"""TICKET-002: import smoke and probe unit tests (no real hardware in monkeypatch tests)."""

from __future__ import annotations

import importlib
import sys

import pytest
from rich.console import Console

from sabi.probe import collect_probe_results, list_probe_devices, run_probe


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
    monkeypatch.setattr("sabi.probe._probe_audio", lambda _c, device_index=None: True)
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
    monkeypatch.setattr("sabi.probe._probe_audio", lambda _c, device_index=None: True)

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
    monkeypatch.setattr("sabi.probe._probe_audio", lambda _c, device_index=None: True)
    code = run_probe(console=Console(record=True, width=120))
    assert code == 1


def test_collect_probe_results_uses_selected_audio_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, int | None] = {}
    monkeypatch.setattr(
        "sabi.probe._import_matrix_rows",
        lambda: [("dummy", True, "")],
    )
    monkeypatch.setattr("sabi.probe._probe_webcam", lambda _c, camera_index=0: True)

    def fake_audio(_console: Console, device_index: int | None = None) -> bool:
        seen["device_index"] = device_index
        return True

    monkeypatch.setattr("sabi.probe._probe_audio", fake_audio)
    result = collect_probe_results(camera_index=2, audio_device_index=7)
    assert result["webcam"]["camera_index"] == 2
    assert result["audio"]["device_index"] == 7
    assert seen["device_index"] == 7


def test_list_probe_devices_handles_backend_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sabi.probe as probe_mod

    monkeypatch.setitem(sys.modules, "cv2", None)
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    devices = probe_mod.list_probe_devices(max_camera_index=0)
    assert devices["cameras"]
    assert devices["microphones"]
