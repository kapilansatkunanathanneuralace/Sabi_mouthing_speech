"""Typer CLI (TICKET-002); pipeline bodies land in later tickets."""

from __future__ import annotations

from pathlib import Path

import typer

from sabi.capture.lip_preview import run_lip_preview
from sabi.capture.lip_roi import LipROIConfig
from sabi.capture.preview import run_cam_preview
from sabi.capture.webcam import WebcamConfig
from sabi.probe import run_probe

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Sabi silent speech / mouthing PoC CLI.",
)


@app.callback()
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo("sabi PoC - see tickets/README.md")
        typer.echo("Try: sabi probe   or   sabi --help")


@app.command("cam-preview")
def cam_preview_cmd(
    camera_index: int = typer.Option(
        0,
        "--camera-index",
        help="Webcam index for OpenCV.",
    ),
    width: int = typer.Option(1280, "--width", help="Requested frame width."),
    height: int = typer.Option(720, "--height", help="Requested frame height."),
    fps: float = typer.Option(25.0, "--fps", help="Requested capture FPS."),
    buffer: int = typer.Option(4, "--buffer", help="Ring buffer size (frames)."),
    mirror: bool = typer.Option(False, "--mirror/--no-mirror", help="Mirror image horizontally."),
) -> None:
    cfg = WebcamConfig(
        device_index=camera_index,
        width=width,
        height=height,
        target_fps=fps,
        buffer_size=buffer,
        mirror=mirror,
    )
    run_cam_preview(cfg)


@app.command("lip-preview")
def lip_preview_cmd(
    camera_index: int = typer.Option(
        0,
        "--camera-index",
        help="Webcam index for OpenCV.",
    ),
    width: int = typer.Option(1280, "--width", help="Requested frame width."),
    height: int = typer.Option(720, "--height", help="Requested frame height."),
    fps: float = typer.Option(25.0, "--fps", help="Requested capture FPS."),
    buffer: int = typer.Option(4, "--buffer", help="Ring buffer size (frames)."),
    mirror: bool = typer.Option(False, "--mirror/--no-mirror", help="Mirror image horizontally."),
    target_size: int = typer.Option(96, "--target-size", help="Square crop side in pixels."),
    smooth_alpha: float = typer.Option(
        0.5,
        "--smooth-alpha",
        help="EWMA factor for bbox smoothing (0=no smoothing, 1=frozen).",
    ),
    max_missing_streak: int = typer.Option(
        15,
        "--max-missing-streak",
        help="Frames without a face before emitting the None sentinel.",
    ),
    grayscale: bool = typer.Option(
        True,
        "--grayscale/--rgb",
        help="Emit grayscale (Auto-AVSR default) or RGB crops.",
    ),
) -> None:
    wcfg = WebcamConfig(
        device_index=camera_index,
        width=width,
        height=height,
        target_fps=fps,
        buffer_size=buffer,
        mirror=mirror,
    )
    lcfg = LipROIConfig(
        target_size=target_size,
        smooth_alpha=smooth_alpha,
        max_missing_streak=max_missing_streak,
        grayscale=grayscale,
    )
    run_lip_preview(wcfg, lcfg)


@app.command("probe")
def probe_cmd(
    camera_index: int = typer.Option(
        0,
        "--camera-index",
        help="Webcam index for OpenCV.",
    ),
) -> None:
    raise typer.Exit(run_probe(camera_index=camera_index))


@app.command("mic-preview")
def mic_preview_cmd(
    device: int = typer.Option(
        -1,
        "--device",
        help="sounddevice input index; -1 uses the system default.",
    ),
    aggressiveness: int = typer.Option(
        2,
        "--aggressiveness",
        help="WebRTC VAD aggressiveness (0=lenient..3=strict).",
    ),
    frame_ms: int = typer.Option(
        20,
        "--frame-ms",
        help="VAD frame size in milliseconds (10, 20, or 30).",
    ),
    min_utterance_ms: int = typer.Option(
        300,
        "--min-utterance-ms",
        help="Discard speech segments shorter than this duration.",
    ),
    max_utterance_ms: int = typer.Option(
        15000,
        "--max-utterance-ms",
        help="Force-close an utterance that runs longer than this duration.",
    ),
    trailing_silence_ms: int = typer.Option(
        400,
        "--trailing-silence-ms",
        help="Silence after speech required to close an utterance.",
    ),
) -> None:
    """Live dB meter + VAD indicator for mic capture (TICKET-006)."""

    from sabi.capture.mic_preview import run_mic_preview
    from sabi.capture.microphone import MicConfig

    cfg = MicConfig(
        device_index=None if device < 0 else device,
        vad_aggressiveness=aggressiveness,
        frame_ms=frame_ms,  # type: ignore[arg-type]
        min_utterance_ms=min_utterance_ms,
        max_utterance_ms=max_utterance_ms,
        trailing_silence_ms=trailing_silence_ms,
    )
    run_mic_preview(cfg)


@app.command("download-vsr")
def download_vsr_cmd(
    force: bool = typer.Option(False, "--force", help="Redownload existing weights."),
    print_hashes: bool = typer.Option(
        False,
        "--print-hashes",
        help="Print sha256 of each resulting file in TOML form.",
    ),
) -> None:
    """Download Chaplin / Auto-AVSR weights per ``configs/vsr_weights.toml`` (TICKET-005)."""

    from sabi.models.vsr.download import main as _download_main

    argv: list[str] = []
    if force:
        argv.append("--force")
    if print_hashes:
        argv.append("--print-hashes")
    raise typer.Exit(_download_main(argv))


@app.command("vsr-smoke")
def vsr_smoke_cmd(
    video_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a short video clip to transcribe.",
    ),
    device: str = typer.Option(
        "auto",
        "--device",
        help="Torch device: auto/cuda/cpu.",
    ),
    precision: str = typer.Option(
        "fp32",
        "--precision",
        help="fp16 enables autocast on CUDA; ignored on CPU.",
    ),
    wer_gate: float = typer.Option(
        0.30,
        "--wer-gate",
        help="Warn above this WER when a sibling .txt ground truth exists.",
    ),
) -> None:
    """Run the VSR wrapper end-to-end over a recorded clip (TICKET-005 acceptance)."""

    import logging

    from sabi.models.vsr.model import VSRModelConfig
    from sabi.models.vsr.smoke import run_vsr_smoke

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    lip_cfg = LipROIConfig(grayscale=True)
    vsr_cfg = VSRModelConfig(device=device, precision=precision)  # type: ignore[arg-type]
    run_vsr_smoke(video_path, vsr_cfg, lip_cfg, wer_gate=wer_gate)


@app.command("silent-dictate")
def silent_dictate_cmd() -> None:
    typer.echo("not implemented yet (TICKET-011)")
    raise typer.Exit(1)


@app.command("dictate")
def dictate_cmd() -> None:
    typer.echo("not implemented yet (TICKET-012)")
    raise typer.Exit(1)


def main() -> None:
    app()
