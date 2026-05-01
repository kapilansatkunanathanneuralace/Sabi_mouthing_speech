"""Environment and hardware probe (TICKET-002)."""

from __future__ import annotations

import argparse
import importlib
import io
import os
import platform
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass

from rich.console import Console
from rich.table import Table

try:
    cv2 = importlib.import_module("cv2")
except Exception:  # noqa: BLE001 - import matrix reports dependency failures later
    cv2 = None


@dataclass(frozen=True)
class ProbeResult:
    """Structured probe output for sidecar callers."""

    runtime: dict[str, str]
    imports: list[dict[str, object]]
    torch: dict[str, object]
    webcam: dict[str, object]
    audio: dict[str, object]
    failures: int


def _try_import(name: str, import_fn: Callable[[], None]) -> tuple[str, bool, str]:
    try:
        import_fn()
        return name, True, ""
    except Exception as exc:  # noqa: BLE001 - probe must not crash
        msg = str(exc).splitlines()[0][:120]
        return name, False, msg


def _import_matrix_rows() -> list[tuple[str, bool, str]]:
    rows: list[tuple[str, bool, str]] = []

    def imp_cv2() -> None:
        importlib.import_module("cv2")

    def imp_numpy() -> None:
        importlib.import_module("numpy")

    def imp_mediapipe() -> None:
        importlib.import_module("mediapipe")

    def imp_faster_whisper() -> None:
        importlib.import_module("faster_whisper")

    def imp_sounddevice() -> None:
        importlib.import_module("sounddevice")

    def imp_pyautogui() -> None:
        importlib.import_module("pyautogui")

    def imp_pyperclip() -> None:
        importlib.import_module("pyperclip")

    def imp_keyboard() -> None:
        importlib.import_module("keyboard")

    def imp_httpx() -> None:
        importlib.import_module("httpx")

    def imp_pydantic() -> None:
        importlib.import_module("pydantic")

    def imp_rich() -> None:
        importlib.import_module("rich")

    def imp_typer() -> None:
        importlib.import_module("typer")

    for label, fn in (
        ("cv2", imp_cv2),
        ("numpy", imp_numpy),
        ("mediapipe", imp_mediapipe),
        ("faster_whisper", imp_faster_whisper),
        ("sounddevice", imp_sounddevice),
        ("pyautogui", imp_pyautogui),
        ("pyperclip", imp_pyperclip),
        ("keyboard", imp_keyboard),
        ("httpx", imp_httpx),
        ("pydantic", imp_pydantic),
        ("rich", imp_rich),
        ("typer", imp_typer),
    ):
        rows.append(_try_import(label, fn))

    try:
        importlib.import_module("webrtcvad")
        rows.append(("webrtcvad (webrtcvad-wheels)", True, "backend=webrtcvad"))
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).splitlines()[0][:120]
        try:
            importlib.import_module("silero_vad")
            rows.append(("silero_vad (fallback)", True, "backend=silero_vad"))
        except Exception as exc2:  # noqa: BLE001
            rows.append(
                (
                    "webrtcvad / silero_vad",
                    False,
                    f"webrtcvad: {msg}; silero: {str(exc2).splitlines()[0][:80]}",
                ),
            )

    return rows


def _print_runtime(console: Console) -> None:
    table = Table(title="Runtime")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("python", sys.version.split()[0])
    table.add_row("platform", platform.platform())
    table.add_row("machine", platform.machine())
    table.add_row("cpu_count", str(os.cpu_count() or "?"))
    console.print(table)


def _print_torch(console: Console) -> None:
    import torch

    cuda_ok = bool(torch.cuda.is_available())
    table = Table(title="PyTorch / CUDA")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("torch", torch.__version__)
    table.add_row("import", "PASS")
    table.add_row("cuda_available", str(cuda_ok))
    if cuda_ok:
        table.add_row("device", torch.cuda.get_device_name(0))
        try:
            free_b, total_b = torch.cuda.mem_get_info()
            table.add_row("vram_free_gb", f"{free_b / (1024**3):.2f}")
            table.add_row("vram_total_gb", f"{total_b / (1024**3):.2f}")
        except Exception:  # noqa: BLE001
            table.add_row("vram", "(mem_get_info unavailable)")
    console.print(table)
    if not cuda_ok:
        console.print(
            "[yellow]CUDA: not available (CPU fallback will be used)[/yellow]",
        )


def _probe_webcam(console: Console, camera_index: int = 0) -> bool:
    cap = None
    try:
        if cv2 is None:
            raise RuntimeError("cv2 is not available")
        if sys.platform == "win32":
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            console.print(
                "[red]Webcam: FAILED to open device.[/red]\n"
                "Remediation: Windows Settings > Privacy & security > Camera - "
                "allow desktop apps. Close other apps using the camera. "
                "Try a different USB port or camera index.",
            )
            return False
        ok, frame = cap.read()
        if not ok or frame is None:
            console.print(
                "[red]Webcam: opened but failed to read a frame.[/red]\n"
                "Remediation: same as above; check drivers and privacy.",
            )
            return False
        h, w = frame.shape[:2]
        console.print(
            f"[green]Webcam: PASS[/green] - resolution {w}x{h} (index {camera_index})",
        )
        return True
    finally:
        if cap is not None:
            cap.release()


def _probe_audio(console: Console, device_index: int | None = None) -> bool:
    import sounddevice as sd

    try:
        default_in, _default_out = sd.default.device
        selected = default_in if device_index is None else device_index
        if selected is None or int(selected) < 0:
            console.print("[red]Audio input: no default input device.[/red]")
            return False
        dev = sd.query_devices(selected, "input")
        name = str(dev.get("name", ""))
        default_sr = dev.get("default_samplerate")
        console.print(
            f"[green]Audio input[/green]: index={selected}, name={name!r}, "
            f"default_samplerate={default_sr}",
        )
        try:
            sd.check_input_settings(
                samplerate=16000,
                channels=1,
                dtype="float32",
                device=selected,
            )
            console.print("[green]16 kHz mono float32: PASS[/green] (check_input_settings)")
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"[yellow]16 kHz mono float32: WARN[/yellow] — {exc!s}. "
                "You may need a different device or resampling in TICKET-006.",
            )
        return True
    except Exception as exc:  # noqa: BLE001
        console.print(
            f"[red]Audio input: FAILED - {exc!s}[/red]\n"
            "Remediation: Windows Settings > Privacy & security > Microphone - "
            "allow desktop apps.",
        )
        return False


def list_probe_devices(*, max_camera_index: int = 4) -> dict[str, object]:
    """Return probe-compatible camera indexes and sounddevice input indexes."""

    cameras: list[dict[str, object]] = []
    try:
        if cv2 is None:
            raise RuntimeError("cv2 is not available")
        for index in range(max_camera_index + 1):
            cap = None
            try:
                if sys.platform == "win32":
                    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(index)
                available = bool(cap.isOpened())
                cameras.append(
                    {
                        "kind": "camera",
                        "index": index,
                        "name": f"Camera {index}",
                        "available": available,
                        "detail": "OpenCV device index",
                    },
                )
            finally:
                if cap is not None:
                    cap.release()
    except Exception as exc:  # noqa: BLE001 - device listing must not crash
        cameras.append(
            {
                "kind": "camera",
                "index": 0,
                "name": "Camera 0",
                "available": False,
                "detail": str(exc),
            },
        )

    microphones: list[dict[str, object]] = []
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        for index, device in enumerate(devices):
            max_inputs = int(device.get("max_input_channels", 0))
            if max_inputs <= 0:
                continue
            microphones.append(
                {
                    "kind": "microphone",
                    "index": index,
                    "name": str(device.get("name", f"Microphone {index}")),
                    "available": True,
                    "detail": f"{max_inputs} input channel(s)",
                },
            )
    except Exception as exc:  # noqa: BLE001
        microphones.append(
            {
                "kind": "microphone",
                "index": -1,
                "name": "System default microphone",
                "available": False,
                "detail": str(exc),
            },
        )

    return {"cameras": cameras, "microphones": microphones}


def collect_probe_results(
    *,
    camera_index: int = 0,
    audio_device_index: int | None = None,
) -> dict[str, object]:
    """Return probe results as structured data without writing to stdout."""

    failures = 0
    import_rows = _import_matrix_rows()
    imports = [
        {"module": name, "ok": ok, "detail": detail}
        for name, ok, detail in import_rows
    ]
    if not all(bool(row["ok"]) for row in imports):
        failures += 1

    torch_result: dict[str, object]
    try:
        import torch

        cuda_ok = bool(torch.cuda.is_available())
        torch_result = {"ok": True, "version": torch.__version__, "cuda_available": cuda_ok}
        if cuda_ok:
            torch_result["device"] = torch.cuda.get_device_name(0)
    except Exception as exc:  # noqa: BLE001 - probe must not crash
        torch_result = {"ok": False, "error": str(exc)}
        failures += 1

    record = Console(file=io.StringIO(), record=True, width=120)
    webcam_ok = _probe_webcam(record, camera_index=camera_index)
    if not webcam_ok:
        failures += 1
    webcam = {
        "ok": webcam_ok,
        "camera_index": camera_index,
        "output": record.export_text(clear=True).strip(),
    }

    try:
        audio_ok = _probe_audio(record, device_index=audio_device_index)
    except Exception as exc:  # noqa: BLE001 - packaged audio backends may fail to load
        audio_ok = False
        record.print(f"[red]Audio input: FAILED - {exc!s}[/red]")
    if not audio_ok:
        failures += 1
    audio = {
        "ok": audio_ok,
        "device_index": audio_device_index,
        "output": record.export_text(clear=True).strip(),
    }

    result = ProbeResult(
        runtime={
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": str(os.cpu_count() or "?"),
        },
        imports=imports,
        torch=torch_result,
        webcam=webcam,
        audio=audio,
        failures=failures,
    )
    return asdict(result)


def _print_import_table(console: Console, rows: list[tuple[str, bool, str]]) -> bool:
    table = Table(title="Package imports")
    table.add_column("Module", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Detail", style="dim")
    all_ok = True
    for name, ok, detail in rows:
        status = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        if not ok:
            all_ok = False
        table.add_row(name, status, detail)
    console.print(table)
    return all_ok


def run_probe(
    *,
    camera_index: int = 0,
    audio_device_index: int | None = None,
    console: Console | None = None,
) -> int:
    """Run all checks. Returns process exit code (0 = success)."""
    con = console or Console()
    failures = 0

    _print_runtime(con)

    try:
        _print_torch(con)
    except Exception as exc:  # noqa: BLE001
        con.print(f"[red]torch import/runtime FAILED: {exc}[/red]")
        failures += 1

    import_rows = _import_matrix_rows()
    if not _print_import_table(con, import_rows):
        failures += 1

    if not _probe_webcam(con, camera_index=camera_index):
        failures += 1

    if not _probe_audio(con, device_index=audio_device_index):
        failures += 1

    if failures:
        con.print(f"\n[red]Probe finished with {failures} failure(s).[/red]")
        return 1
    con.print("\n[green]Probe finished: all mandatory checks passed.[/green]")
    return 0


def _cli_argv() -> int:
    parser = argparse.ArgumentParser(description="Sabi environment probe.")
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Webcam index for OpenCV.",
    )
    parser.add_argument(
        "--audio-device-index",
        type=int,
        default=None,
        help="sounddevice input index; omit to use the system default.",
    )
    args = parser.parse_args()
    return run_probe(
        camera_index=args.camera_index,
        audio_device_index=args.audio_device_index,
    )


def main() -> int:
    """Entry for `python scripts/probe_env.py` (parses ``sys.argv``)."""
    return _cli_argv()


if __name__ == "__main__":
    raise SystemExit(main())
