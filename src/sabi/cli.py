"""Typer CLI (TICKET-002); pipeline bodies land in later tickets."""

from __future__ import annotations

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
