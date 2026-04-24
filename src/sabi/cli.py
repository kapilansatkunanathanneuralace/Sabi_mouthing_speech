"""Typer CLI (TICKET-002); pipeline bodies land in later tickets."""

from __future__ import annotations

import time
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


@app.command("asr-smoke")
def asr_smoke_cmd(
    wav_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a short 16 kHz mono wav clip to transcribe.",
    ),
    device: str = typer.Option(
        "auto",
        "--device",
        help="faster-whisper device: auto/cuda/cpu.",
    ),
    model_size: str = typer.Option(
        "small",
        "--model-size",
        help="Checkpoint size (tiny/base/small/medium/large-v3); roadmap MVP = small.",
    ),
    compute_type: str = typer.Option(
        "",
        "--compute-type",
        help="Override CTranslate2 compute_type (e.g. int8, int8_float16, float16).",
    ),
    language: str = typer.Option(
        "en",
        "--language",
        help="ISO 639-1 code. Pass empty string to enable auto-detect.",
    ),
    beam_size: int = typer.Option(1, "--beam-size", help="Decoding beam size."),
    wer_gate: float = typer.Option(
        0.10,
        "--wer-gate",
        help="Warn above this WER when a sibling .txt ground truth exists.",
    ),
    latency_gate_ms: float = typer.Option(
        500.0,
        "--latency-gate-ms",
        help="Warn when transcription latency exceeds this budget.",
    ),
    warmup: bool = typer.Option(
        True,
        "--warmup/--no-warmup",
        help="Run one 0.5 s dummy inference before the real transcription.",
    ),
) -> None:
    """Run the ASR wrapper end-to-end over a recorded clip (TICKET-007 acceptance)."""

    import logging

    from sabi.models.asr import ASRModelConfig
    from sabi.models.asr_smoke import run_asr_smoke

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asr_cfg = ASRModelConfig(
        model_size=model_size,  # type: ignore[arg-type]
        device=device,  # type: ignore[arg-type]
        compute_type=compute_type or None,
        language=language or None,
        beam_size=beam_size,
    )
    run_asr_smoke(
        wav_path,
        asr_cfg,
        wer_gate=wer_gate,
        warmup=warmup,
        latency_gate_ms=latency_gate_ms,
    )


@app.command("cleanup-smoke")
def cleanup_smoke_cmd(
    text: str = typer.Argument(
        ...,
        help='Raw text to clean, e.g. "um i think it might like work".',
    ),
    config_path: Path = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Override path to configs/cleanup.toml.",
    ),
    base_url: str = typer.Option(
        "",
        "--base-url",
        help="Override Ollama base URL (e.g. http://127.0.0.1:11434).",
    ),
    model: str = typer.Option(
        "",
        "--model",
        help="Override Ollama model tag (e.g. llama3.2:3b-instruct-q4_K_M).",
    ),
    timeout_ms: int = typer.Option(
        0,
        "--timeout-ms",
        help="Override cleanup request timeout in milliseconds.",
    ),
    source: str = typer.Option(
        "asr",
        "--source",
        help="CleanupContext.source: asr or vsr.",
    ),
    register_hint: str = typer.Option(
        "dictation",
        "--register-hint",
        help="CleanupContext.register_hint: dictation/meeting/chat.",
    ),
    focused_app: str = typer.Option(
        "",
        "--focused-app",
        help="Optional focused-app hint (TICKET-011/012 will populate this).",
    ),
) -> None:
    """Run one cleanup pass against a local Ollama instance (TICKET-008)."""

    import logging

    from sabi.cleanup import CleanupContext, TextCleaner, load_cleanup_config
    from sabi.models.latency import append_latency_row

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_cleanup_config(config_path)
    overrides: dict[str, object] = {}
    if base_url:
        overrides["base_url"] = base_url
    if model:
        overrides["model"] = model
    if timeout_ms > 0:
        overrides["timeout_ms"] = timeout_ms
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    context = CleanupContext(
        source=source,  # type: ignore[arg-type]
        register_hint=register_hint,  # type: ignore[arg-type]
        focused_app=focused_app or None,
    )

    with TextCleaner(cfg) as cleaner:
        probe_ok = cleaner.is_available()
        result = cleaner.cleanup(text, context)

    hardware = "ollama" if probe_ok and not result.used_fallback else "fallback"
    notes = (
        f"model={cfg.model} source={context.source} "
        f"fallback={result.used_fallback}"
    )
    if result.reason:
        notes += f" reason={result.reason}"
    append_latency_row(
        "TICKET-008",
        hardware,
        "cleanup",
        result.latency_ms,
        len(text),
        notes,
    )

    print(f"raw      : {text!r}")
    print(f"cleaned  : {result.text!r}")
    print(f"latency  : {result.latency_ms:.1f} ms")
    print(f"fallback : {result.used_fallback}")
    if result.reason:
        print(f"reason   : {result.reason}")
    if not probe_ok:
        print("note     : Ollama did not respond to /api/tags - returning raw text.")


@app.command("paste-test")
def paste_test_cmd(
    text: str = typer.Argument(..., help="Text to paste into whichever window is focused after the countdown."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Skip Ctrl+V; clipboard is still written and restored so you can verify round-trip.",
    ),
    paste_delay_ms: int = typer.Option(
        15,
        "--paste-delay-ms",
        help="Delay between clipboard write and Ctrl+V (ms). 15 ms is the smallest reliable value on Slack Desktop.",
    ),
    restore_delay_ms: int = typer.Option(
        400,
        "--restore-delay-ms",
        help="Delay before the prior clipboard contents are restored (ms).",
    ),
    countdown: int = typer.Option(
        3,
        "--countdown",
        help="Seconds to wait before pressing Ctrl+V so the user can focus the target window.",
    ),
) -> None:
    """Paste a string into the focused window (TICKET-009)."""

    import logging

    from sabi.models.latency import append_latency_row
    from sabi.output import InjectConfig, paste_text

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = InjectConfig(
        paste_delay_ms=paste_delay_ms,
        restore_delay_ms=restore_delay_ms,
        dry_run=dry_run,
    )

    if not dry_run and countdown > 0:
        typer.echo(f"Focus the target window. Pasting in {countdown} s...")
        for remaining in range(countdown, 0, -1):
            typer.echo(f"  {remaining}...")
            time.sleep(1.0)

    result = paste_text(text, cfg)

    notes = f"dry_run={dry_run} paste_delay_ms={paste_delay_ms} restore_delay_ms={restore_delay_ms}"
    if result.error:
        notes += f" error={result.error}"
    append_latency_row(
        "TICKET-009",
        "windows",
        "inject",
        result.latency_ms,
        result.length,
        notes,
    )

    print(f"text     : {text!r}")
    print(f"length   : {result.length}")
    print(f"latency  : {result.latency_ms:.1f} ms")
    print(f"dry_run  : {dry_run}")
    if result.error:
        print(f"error    : {result.error}")


@app.command("hotkey-debug")
def hotkey_debug_cmd(
    config_path: Path = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Override path to configs/hotkey.toml.",
    ),
    mode: str = typer.Option(
        "",
        "--mode",
        help="Override trigger mode: push_to_talk or toggle.",
    ),
    binding: str = typer.Option(
        "",
        "--binding",
        help="Override hotkey chord (e.g. 'ctrl+alt+space').",
    ),
    min_hold_ms: int = typer.Option(
        0,
        "--min-hold-ms",
        help="Override minimum hold duration in milliseconds.",
    ),
    cooldown_ms: int = typer.Option(
        0,
        "--cooldown-ms",
        help="Override cooldown between successful on_start events.",
    ),
) -> None:
    """Print TRIGGER START / STOP events from the hotkey layer (TICKET-010)."""

    import logging

    from sabi.input import load_hotkey_config, run_hotkey_debug

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_hotkey_config(config_path)
    overrides: dict[str, object] = {}
    if mode:
        overrides["mode"] = mode
    if binding:
        overrides["binding"] = binding
    if min_hold_ms > 0:
        overrides["min_hold_ms"] = min_hold_ms
    if cooldown_ms > 0:
        overrides["cooldown_ms"] = cooldown_ms
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    raise typer.Exit(run_hotkey_debug(cfg))


@app.command("silent-dictate")
def silent_dictate_cmd(
    config_path: Path = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Override path to configs/silent_dictate.toml.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the cleaned text to stdout instead of pasting (TICKET-009 dry-run).",
    ),
    force_cpu: bool = typer.Option(
        False,
        "--force-cpu",
        help="Force VSR onto CPU (smoke-testing on machines without CUDA).",
    ),
    keep_camera_open: bool = typer.Option(
        False,
        "--keep-camera-open",
        help="Keep the webcam hot between triggers (faster utterances; LED stays on).",
    ),
    binding: str = typer.Option(
        "",
        "--binding",
        help="Override the primary hotkey chord (e.g. 'ctrl+alt+space').",
    ),
    force_paste_binding: str = typer.Option(
        "",
        "--force-paste-binding",
        help="Override the force-paste chord (default F12).",
    ),
    confidence_floor: float = typer.Option(
        -1.0,
        "--confidence-floor",
        help="Override VSR confidence floor for paste gating. Negative = use config.",
    ),
    force_paste_mode: str = typer.Option(
        "",
        "--force-paste",
        help="Force-paste policy: listener|always|never.",
    ),
) -> None:
    """Silent-dictation pipeline (TICKET-011)."""

    import logging

    from sabi.pipelines import load_silent_dictate_config, run_silent_dictate

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_silent_dictate_config(config_path)

    overrides: dict[str, object] = {}
    if dry_run:
        overrides["dry_run"] = True
    if keep_camera_open:
        overrides["keep_camera_open"] = True
    if force_cpu:
        overrides["device_override"] = "cpu"
    if binding:
        overrides["hotkey"] = cfg.hotkey.model_copy(update={"binding": binding})
    if force_paste_binding:
        overrides["force_paste_binding"] = force_paste_binding
    if confidence_floor >= 0.0:
        overrides["confidence_floor"] = confidence_floor
    if force_paste_mode:
        overrides["force_paste_mode"] = force_paste_mode  # type: ignore[assignment]
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    raise typer.Exit(run_silent_dictate(cfg))


@app.command("dictate")
def dictate_cmd(
    config_path: Path = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Override path to configs/audio_dictate.toml.",
    ),
    mode: str = typer.Option(
        "",
        "--mode",
        help="Trigger mode: push-to-talk|push_to_talk|vad. Empty = use config.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the cleaned text to stdout instead of pasting.",
    ),
    force_cpu: bool = typer.Option(
        False,
        "--force-cpu",
        help="Force ASR onto CPU (smoke-testing on machines without CUDA).",
    ),
    ptt_open_per_trigger: bool = typer.Option(
        False,
        "--ptt-open-per-trigger",
        help="Open the microphone per PTT trigger instead of preopening on pipeline start.",
    ),
    binding: str = typer.Option(
        "",
        "--binding",
        help="Override the primary hotkey chord (e.g. 'ctrl+alt+space').",
    ),
    force_paste_binding: str = typer.Option(
        "",
        "--force-paste-binding",
        help="Override the force-paste chord (default F12).",
    ),
    confidence_floor: float = typer.Option(
        -1.0,
        "--confidence-floor",
        help="Override ASR confidence floor for paste gating. Negative = use config.",
    ),
    force_paste_mode: str = typer.Option(
        "",
        "--force-paste",
        help=(
            "Force-paste policy: listener|always|never. "
            "Applied to both PTT and VAD fields when provided."
        ),
    ),
) -> None:
    """Audio-dictation pipeline (TICKET-012)."""

    import logging

    from sabi.pipelines import load_audio_dictate_config, run_audio_dictate

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_audio_dictate_config(config_path)

    overrides: dict[str, object] = {}
    if mode:
        normalized = mode.strip().lower().replace("-", "_")
        if normalized not in {"push_to_talk", "vad"}:
            raise typer.BadParameter(
                f"--mode must be 'push-to-talk' or 'vad', got {mode!r}",
                param_hint="--mode",
            )
        overrides["trigger_mode"] = normalized  # type: ignore[assignment]
    if dry_run:
        overrides["dry_run"] = True
    if ptt_open_per_trigger:
        overrides["ptt_open_per_trigger"] = True
    if force_cpu:
        overrides["device_override"] = "cpu"
    if binding:
        overrides["hotkey"] = cfg.hotkey.model_copy(update={"binding": binding})
    if force_paste_binding:
        overrides["force_paste_binding"] = force_paste_binding
    if confidence_floor >= 0.0:
        overrides["confidence_floor"] = confidence_floor
    if force_paste_mode:
        normalized_fpm = force_paste_mode.strip().lower()
        if normalized_fpm not in {"listener", "always", "never"}:
            raise typer.BadParameter(
                f"--force-paste must be listener|always|never, got {force_paste_mode!r}",
                param_hint="--force-paste",
            )
        overrides["force_paste_mode_ptt"] = normalized_fpm  # type: ignore[assignment]
        overrides["force_paste_mode_vad"] = normalized_fpm  # type: ignore[assignment]
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    raise typer.Exit(run_audio_dictate(cfg))


def main() -> None:
    app()
