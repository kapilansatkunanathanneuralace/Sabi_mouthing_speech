"""Typer CLI (TICKET-002); pipeline bodies land in later tickets."""

from __future__ import annotations

import sys
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


def _normalize_cleanup_prompt(value: str, *, param_hint: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"v1", "v2"}:
        raise typer.BadParameter(
            f"{param_hint} must be v1 or v2, got {value!r}",
            param_hint=param_hint,
        )
    return normalized


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


@app.command("sidecar")
def sidecar_cmd() -> None:
    """Run the JSON-RPC stdio sidecar for the desktop shell (TICKET-042)."""

    import logging

    from sabi.sidecar.server import run_stdio_server

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    raise typer.Exit(run_stdio_server())


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


@app.command("fusion-smoke")
def fusion_smoke_cmd(
    asr_json: Path | None = typer.Argument(
        None,
        help="Optional JSON file matching ASRResult fields.",
    ),
    vsr_json: Path | None = typer.Argument(
        None,
        help="Optional JSON file matching VSRResult fields.",
    ),
    config_path: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Override path to configs/fusion.toml.",
    ),
    asr_text: str = typer.Option("", "--asr-text", help="Synthetic ASR transcript."),
    vsr_text: str = typer.Option("", "--vsr-text", help="Synthetic VSR transcript."),
    asr_conf: float = typer.Option(0.7, "--asr-conf", min=0.0, max=1.0),
    vsr_conf: float = typer.Option(0.5, "--vsr-conf", min=0.0, max=1.0),
) -> None:
    """Run pure ASR/VSR transcript fusion without loading models."""

    import json

    from sabi.fusion import FusionCombiner, load_fusion_config
    from sabi.models.asr import ASRResult
    from sabi.models.vsr.model import VSRResult

    if asr_text == "--vsr-text" and asr_json is not None and vsr_json is None and not vsr_text:
        # Windows PowerShell can drop an empty "" argument before Python sees it.
        # Recover the documented `--asr-text "" --vsr-text "..."` smoke command.
        vsr_text = str(asr_json)
        asr_text = ""
        asr_json = None

    def _read_json(path: Path) -> dict:
        if not path.is_file():
            raise typer.BadParameter(f"JSON file not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _asr_from_data(data: dict) -> ASRResult:
        per_word = [
            (str(item[0]), float(item[1]), float(item[2]), float(item[3]))
            for item in data.get("per_word_confidence", [])
        ]
        return ASRResult(
            text=str(data.get("text", "")),
            segments=list(data.get("segments", [])),
            confidence=float(data.get("confidence", 0.0)),
            per_word_confidence=per_word,
            avg_logprob=float(data.get("avg_logprob", 0.0)),
            latency_ms=float(data.get("latency_ms", 0.0)),
            language=data.get("language"),
            device=str(data.get("device", "cpu")),
        )

    def _vsr_from_data(data: dict) -> VSRResult:
        scores = data.get("per_token_scores")
        return VSRResult(
            text=str(data.get("text", "")),
            confidence=float(data.get("confidence", 0.0)),
            per_token_scores=None if scores is None else tuple(float(s) for s in scores),
            latency_ms=float(data.get("latency_ms", 0.0)),
        )

    if asr_json is not None or vsr_json is not None:
        if asr_json is None or vsr_json is None:
            raise typer.BadParameter("pass both ASR and VSR JSON files, or use text shortcuts")
        asr = _asr_from_data(_read_json(asr_json))
        vsr = _vsr_from_data(_read_json(vsr_json))
    else:
        asr_tokens = asr_text.split()
        vsr_tokens = vsr_text.split()
        asr = ASRResult(
            text=asr_text,
            confidence=asr_conf,
            per_word_confidence=[(w, 0.0, 0.0, asr_conf) for w in asr_tokens],
        )
        vsr = VSRResult(
            text=vsr_text,
            confidence=vsr_conf,
            per_token_scores=tuple(vsr_conf for _ in vsr_tokens),
            latency_ms=0.0,
        )

    result = FusionCombiner(load_fusion_config(config_path)).combine(asr, vsr)
    typer.echo(json.dumps(result.to_dict(), indent=2))


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
    prompt_version: str = typer.Option(
        "",
        "--prompt-version",
        help="Cleanup prompt version: v1|v2. Empty = use config.",
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
    if prompt_version:
        overrides["prompt_version"] = _normalize_cleanup_prompt(
            prompt_version,
            param_hint="--prompt-version",
        )
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
        f"model={cfg.model} prompt_version={cfg.prompt_version} source={context.source} "
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
    print(f"prompt   : {cfg.prompt_version}")
    print(f"fallback : {result.used_fallback}")
    if result.reason:
        print(f"reason   : {result.reason}")
    if not probe_ok:
        print("note     : Ollama did not respond to /api/tags - returning raw text.")


@app.command("paste-test")
def paste_test_cmd(
    text: str = typer.Argument(
        ...,
        help="Text to paste into whichever window is focused after the countdown.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Skip Ctrl+V; clipboard is still written and restored so you can verify round-trip.",
    ),
    paste_delay_ms: int = typer.Option(
        15,
        "--paste-delay-ms",
        help=(
            "Delay between clipboard write and Ctrl+V (ms). "
            "15 ms is the smallest reliable value on Slack Desktop."
        ),
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
    cleanup_prompt: str = typer.Option(
        "",
        "--cleanup-prompt",
        help="Cleanup prompt version: v1|v2. Empty = use config.",
    ),
    ui: str = typer.Option(
        "tui",
        "--ui",
        help="Status UI: tui|none.",
    ),
) -> None:
    """Silent-dictation pipeline (TICKET-011)."""

    import logging

    from sabi.pipelines import load_silent_dictate_config, normalize_ui_mode, run_silent_dictate

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
    if cleanup_prompt:
        overrides["cleanup"] = cfg.cleanup.model_copy(
            update={
                "prompt_version": _normalize_cleanup_prompt(
                    cleanup_prompt,
                    param_hint="--cleanup-prompt",
                )
            }
        )
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    try:
        ui_mode = normalize_ui_mode(ui)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--ui") from exc

    raise typer.Exit(run_silent_dictate(cfg, ui=ui_mode))


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
    cleanup_prompt: str = typer.Option(
        "",
        "--cleanup-prompt",
        help="Cleanup prompt version: v1|v2. Empty = use config.",
    ),
    ui: str = typer.Option(
        "tui",
        "--ui",
        help="Status UI: tui|none.",
    ),
) -> None:
    """Audio-dictation pipeline (TICKET-012)."""

    import logging

    from sabi.pipelines import load_audio_dictate_config, normalize_ui_mode, run_audio_dictate

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
    if cleanup_prompt:
        overrides["cleanup"] = cfg.cleanup.model_copy(
            update={
                "prompt_version": _normalize_cleanup_prompt(
                    cleanup_prompt,
                    param_hint="--cleanup-prompt",
                )
            }
        )
    if overrides:
        cfg = cfg.model_copy(update=overrides)

    try:
        ui_mode = normalize_ui_mode(ui)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--ui") from exc

    raise typer.Exit(run_audio_dictate(cfg, ui=ui_mode))


@app.command("fused-dictate")
def fused_dictate_cmd(
    config_path: Path = typer.Option(
        None,
        "--config",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Override path to configs/fused_dictate.toml.",
    ),
    mode: str = typer.Option(
        "",
        "--mode",
        help="Fusion mode override: auto|audio_primary|vsr_primary.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the cleaned text to stdout instead of pasting.",
    ),
    no_parallel: bool = typer.Option(
        False,
        "--no-parallel",
        help="Run VSR then ASR serially instead of in parallel.",
    ),
    force_cpu: bool = typer.Option(
        False,
        "--force-cpu",
        help="Force ASR and VSR onto CPU.",
    ),
    binding: str = typer.Option(
        "",
        "--binding",
        help="Override the primary hotkey chord.",
    ),
    force_paste_binding: str = typer.Option(
        "",
        "--force-paste-binding",
        help="Override the force-paste chord.",
    ),
    confidence_floor: float = typer.Option(
        -1.0,
        "--confidence-floor",
        help="Override fused confidence floor for paste gating. Negative = use config.",
    ),
    force_paste_mode: str = typer.Option(
        "",
        "--force-paste",
        help="Force-paste policy: listener|always|never.",
    ),
    cleanup_prompt: str = typer.Option(
        "",
        "--cleanup-prompt",
        help="Cleanup prompt version: v1|v2. Empty = use config.",
    ),
    ui: str = typer.Option(
        "tui",
        "--ui",
        help="Status UI: tui|none.",
    ),
) -> None:
    """Fused audio-visual dictation pipeline (TICKET-017)."""

    import logging

    from sabi.pipelines import load_fused_dictate_config, normalize_ui_mode, run_fused_dictate

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_fused_dictate_config(config_path)
    overrides: dict[str, object] = {}
    if mode:
        normalized = mode.strip().lower()
        if normalized not in {"auto", "audio_primary", "vsr_primary"}:
            raise typer.BadParameter(
                f"--mode must be auto|audio_primary|vsr_primary, got {mode!r}",
                param_hint="--mode",
            )
        overrides["fusion"] = cfg.fusion.model_copy(update={"mode": normalized})
    if dry_run:
        overrides["dry_run"] = True
    if no_parallel:
        overrides["parallel"] = False
    if force_cpu:
        overrides["device_override"] = "cpu"
    if binding:
        overrides["hotkey"] = cfg.hotkey.model_copy(update={"binding": binding})
    if force_paste_binding:
        overrides["force_paste_binding"] = force_paste_binding
    if confidence_floor >= 0.0:
        overrides["paste_floor_confidence"] = confidence_floor
    if force_paste_mode:
        normalized_fpm = force_paste_mode.strip().lower()
        if normalized_fpm not in {"listener", "always", "never"}:
            raise typer.BadParameter(
                f"--force-paste must be listener|always|never, got {force_paste_mode!r}",
                param_hint="--force-paste",
            )
        overrides["force_paste_mode_fused"] = normalized_fpm
    if cleanup_prompt:
        overrides["cleanup"] = cfg.cleanup.model_copy(
            update={
                "prompt_version": _normalize_cleanup_prompt(
                    cleanup_prompt,
                    param_hint="--cleanup-prompt",
                )
            }
        )
    if overrides:
        cfg = cfg.model_copy(update=overrides)
    try:
        ui_mode = normalize_ui_mode(ui)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--ui") from exc
    raise typer.Exit(run_fused_dictate(cfg, ui=ui_mode))


@app.command("collect-fused-eval")
def collect_fused_eval_cmd(
    out_dir: Path = typer.Option(
        Path("data/eval/fused"),
        "--out-dir",
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Dataset output directory. Writes phrases.jsonl plus video/ and audio/.",
    ),
    phrases: Path = typer.Option(
        Path("data/eval/phrases.sample.jsonl"),
        "--phrases",
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
        help="Source phrases JSONL/JSON file, or a dataset directory containing phrases.jsonl.",
    ),
    limit: int = typer.Option(
        0,
        "--limit",
        min=0,
        help="Maximum number of phrases to collect. 0 = no limit.",
    ),
    start_at: str = typer.Option(
        "",
        "--start-at",
        help="Start at a phrase id or 1-based phrase index.",
    ),
    phrase_id: list[str] | None = typer.Option(
        None,
        "--phrase-id",
        help="Collect only this phrase id. May be passed multiple times.",
    ),
    retry: str = typer.Option(
        "",
        "--retry",
        help="Re-record one phrase id and update its existing output row.",
    ),
    skip_existing: bool = typer.Option(
        False,
        "--skip-existing",
        help="Validate and keep existing media instead of recording over it.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite existing media for selected phrases.",
    ),
    duration_s: float = typer.Option(
        4.0,
        "--duration-s",
        min=0.1,
        help="Seconds to record per phrase.",
    ),
    camera_name: str = typer.Option(
        "",
        "--camera-name",
        help="ffmpeg dshow camera name. List with: ffmpeg -list_devices true -f dshow -i dummy",
    ),
    mic_name: str = typer.Option(
        "",
        "--mic-name",
        help="ffmpeg dshow microphone name.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show planned paths without touching camera, microphone, media, or JSONL.",
    ),
) -> None:
    """Collect paired MP4/WAV media for fused offline eval (TICKET-019)."""

    from sabi.eval.collect_fused import FusedEvalCollectionConfig, collect_fused_eval

    config = FusedEvalCollectionConfig(
        out_dir=out_dir,
        phrases_path=phrases,
        limit=None if limit == 0 else limit,
        start_at=start_at or None,
        phrase_ids=tuple(phrase_id or ()),
        retry_phrase_id=retry or None,
        skip_existing=skip_existing,
        overwrite=overwrite,
        duration_s=duration_s,
        camera_name=camera_name or None,
        mic_name=mic_name or None,
        dry_run=dry_run,
    )

    def _before_record(phrase, index: int, total: int) -> None:  # noqa: ANN001
        typer.echo("")
        typer.echo(f"[{index}/{total}] {phrase.id}: {phrase.text}")
        typer.echo(f"Recording in 3 seconds for {duration_s:.1f} seconds...")
        for remaining in range(3, 0, -1):
            typer.echo(f"  {remaining}...")
            time.sleep(1.0)

    try:
        result = collect_fused_eval(config, before_record=None if dry_run else _before_record)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(f"phrases : {result.phrases_path}")
    typer.echo(
        "summary : "
        f"recorded={result.recorded} skipped={result.skipped} "
        f"planned={result.planned} failed={result.failed}"
    )
    for take in result.takes:
        suffix = f" error={take.error}" if take.error else ""
        typer.echo(
            f"{take.status:8} {take.phrase.id} "
            f"video={take.video_rel} audio={take.audio_rel}{suffix}"
        )
    if result.failed:
        raise typer.Exit(1)


@app.command("fused-eval-check")
def fused_eval_check_cmd(
    dataset: Path = typer.Option(
        Path("data/eval/fused"),
        "--dataset",
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
        help="Fused eval dataset directory or phrases.jsonl file to validate.",
    ),
) -> None:
    """Validate a fused eval dataset before running model eval (TICKET-020)."""

    from sabi.eval.fused_dataset import validate_fused_dataset

    summary = validate_fused_dataset(dataset)
    typer.echo(f"dataset       : {summary.dataset_path}")
    typer.echo(f"phrases       : {summary.phrase_count}")
    typer.echo(f"valid         : {summary.valid_count}")
    typer.echo(f"missing video : {summary.missing_video_count}")
    typer.echo(f"missing audio : {summary.missing_audio_count}")
    typer.echo(f"invalid video : {summary.invalid_video_count}")
    typer.echo(f"invalid audio : {summary.invalid_audio_count}")

    if summary.issues:
        typer.echo("")
        typer.echo("Issues:")
        for issue in summary.issues:
            typer.echo(f"- {issue.phrase_id} {issue.field}: {issue.message}")
        raise typer.Exit(1)

    typer.echo("")
    typer.echo("Dataset is ready for fused eval.")
    typer.echo("Run:")
    typer.echo(f"  {summary.recommended_eval_command}")


@app.command("fused-eval-reset")
def fused_eval_reset_cmd(
    dataset: Path = typer.Option(
        Path("data/eval/fused"),
        "--dataset",
        file_okay=False,
        dir_okay=True,
        writable=True,
        help="Fused eval dataset directory to reset.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Actually delete generated phrases.jsonl plus video/audio media.",
    ),
) -> None:
    """Reset generated fused eval media so collection can start over."""

    from sabi.eval.collect_fused import reset_fused_eval_dataset

    result = reset_fused_eval_dataset(dataset, dry_run=not yes)
    mode = "would delete" if result.dry_run else "deleted"
    typer.echo(f"dataset : {result.out_dir}")
    typer.echo(f"{mode}: {len(result.files)} file(s)")
    for path in result.files:
        typer.echo(f"- {path}")
    if result.dry_run:
        typer.echo("")
        typer.echo("Preview only. Re-run with --yes to delete these files.")


@app.command("fused-tuning-suggest")
def fused_tuning_suggest_cmd(
    report: Path = typer.Option(
        Path("reports/poc-eval-fused-personal.md"),
        "--report",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="TICKET-030 fused eval markdown report to analyze.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Optional markdown output path for suggestions.",
    ),
) -> None:
    """Suggest manual fused tuning actions from a diagnostics report."""

    from sabi.eval.fused_tuning import analyze_fused_tuning_report, write_suggestions_markdown

    analysis = analyze_fused_tuning_report(report)
    typer.echo(analysis.to_markdown())
    if out is not None:
        write_suggestions_markdown(analysis, out)
        typer.echo(f"Wrote fused tuning suggestions: {out}")


@app.command("eval")
def eval_cmd(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
        help="Dataset directory containing phrases.jsonl, or a phrases JSONL file.",
    ),
    runs: int = typer.Option(3, "--runs", min=1, help="Measured runs per phrase."),
    warmups: int = typer.Option(1, "--warmups", min=0, help="Warm-up runs per phrase."),
    pipeline: str = typer.Option(
        "both",
        "--pipeline",
        "--pipelines",
        help="Pipeline selection: both|silent|audio|fused.",
    ),
    cleanup_prompt: str = typer.Option(
        "v1",
        "--cleanup-prompt",
        help="Cleanup prompt versions: v1 or v1,v2.",
    ),
    cleanup_timeout_ms: int | None = typer.Option(
        None,
        "--cleanup-timeout-ms",
        min=1,
        help="Override cleanup timeout for eval runs, in milliseconds.",
    ),
    cleanup_preflight: bool = typer.Option(
        True,
        "--cleanup-preflight/--no-cleanup-preflight",
        help="Probe and warm the cleanup model before measured eval rows.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Markdown report output path. Defaults to reports/poc-eval-<date>.md.",
    ),
) -> None:
    """Offline latency + WER eval harness (TICKET-014)."""

    import logging

    from sabi.eval import EvalConfig, MissingEvalDependencyError, run_eval
    from sabi.eval.harness import require_eval_dependencies
    from sabi.pipelines.audio_dictate import AudioDictateConfig
    from sabi.pipelines.fused_dictate import FusedDictateConfig
    from sabi.pipelines.silent_dictate import SilentDictateConfig

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    normalized = pipeline.strip().lower()
    if normalized not in {"both", "silent", "audio", "fused"}:
        raise typer.BadParameter(
            f"--pipeline must be both|silent|audio|fused, got {pipeline!r}",
            param_hint="--pipeline",
        )
    cleanup_prompts = tuple(
        _normalize_cleanup_prompt(part, param_hint="--cleanup-prompt")
        for part in cleanup_prompt.split(",")
        if part.strip()
    )
    if not cleanup_prompts:
        raise typer.BadParameter(
            "--cleanup-prompt must include v1 or v2",
            param_hint="--cleanup-prompt",
        )
    if len(set(cleanup_prompts)) != len(cleanup_prompts):
        raise typer.BadParameter(
            "--cleanup-prompt contains duplicate versions",
            param_hint="--cleanup-prompt",
        )
    if cleanup_timeout_ms is not None:
        silent_config = SilentDictateConfig(
            cleanup=SilentDictateConfig().cleanup.model_copy(
                update={"timeout_ms": cleanup_timeout_ms}
            )
        )
        audio_config = AudioDictateConfig(
            cleanup=AudioDictateConfig().cleanup.model_copy(
                update={"timeout_ms": cleanup_timeout_ms}
            )
        )
        fused_config = FusedDictateConfig(
            cleanup=FusedDictateConfig().cleanup.model_copy(
                update={"timeout_ms": cleanup_timeout_ms}
            )
        )
    else:
        silent_config = SilentDictateConfig()
        audio_config = AudioDictateConfig()
        fused_config = FusedDictateConfig()
    try:
        require_eval_dependencies()
    except MissingEvalDependencyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    result = run_eval(
        EvalConfig(
            dataset_path=dataset,
            runs=runs,
            warmups=warmups,
            pipeline=normalized,  # type: ignore[arg-type]
            cleanup_prompts=cleanup_prompts,  # type: ignore[arg-type]
            cleanup_preflight=cleanup_preflight,
            silent_config=silent_config,
            audio_config=audio_config,
            fused_config=fused_config,
            out_path=out,
        )
    )
    typer.echo(f"Wrote eval report: {result.report_path}")
    typer.echo(f"Records: {len(result.records)}")


@app.command("eval-fusion-modes")
def eval_fusion_modes_cmd(
    dataset: Path = typer.Option(
        ...,
        "--dataset",
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
        help="Dataset directory containing phrases.jsonl, or a phrases JSONL file.",
    ),
    modes: str = typer.Option(
        "auto,audio_primary,vsr_primary",
        "--modes",
        help="Comma-separated fusion modes: auto,audio_primary,vsr_primary.",
    ),
    runs: int = typer.Option(1, "--runs", min=1, help="Measured runs per phrase."),
    warmups: int = typer.Option(1, "--warmups", min=0, help="Warm-up runs per phrase."),
    cleanup_prompt: str = typer.Option(
        "v1",
        "--cleanup-prompt",
        help="Cleanup prompt versions: v1 or v1,v2.",
    ),
    cleanup_timeout_ms: int | None = typer.Option(
        None,
        "--cleanup-timeout-ms",
        min=1,
        help="Override cleanup timeout for eval runs, in milliseconds.",
    ),
    cleanup_preflight: bool = typer.Option(
        True,
        "--cleanup-preflight/--no-cleanup-preflight",
        help="Probe and warm the cleanup model before the first mode sweep.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        file_okay=True,
        dir_okay=False,
        writable=True,
        help="Markdown report path. Defaults to reports/fusion-mode-ab-<date>.md.",
    ),
) -> None:
    """Compare fused eval across fusion modes (TICKET-037)."""

    import logging
    from datetime import datetime, timezone

    from sabi.eval import MissingEvalDependencyError
    from sabi.eval.fusion_mode_ab import (
        FusionModeAbConfig,
        parse_fusion_modes,
        run_fusion_mode_ab_eval,
    )
    from sabi.eval.harness import require_eval_dependencies
    from sabi.pipelines.fused_dictate import FusedDictateConfig

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        mode_list = parse_fusion_modes(modes)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--modes") from exc

    cleanup_prompts = tuple(
        _normalize_cleanup_prompt(part, param_hint="--cleanup-prompt")
        for part in cleanup_prompt.split(",")
        if part.strip()
    )
    if not cleanup_prompts:
        raise typer.BadParameter(
            "--cleanup-prompt must include v1 or v2",
            param_hint="--cleanup-prompt",
        )
    if len(set(cleanup_prompts)) != len(cleanup_prompts):
        raise typer.BadParameter(
            "--cleanup-prompt contains duplicate versions",
            param_hint="--cleanup-prompt",
        )

    fused_base = FusedDictateConfig()
    if cleanup_timeout_ms is not None:
        fused_base = fused_base.model_copy(
            update={
                "cleanup": fused_base.cleanup.model_copy(
                    update={"timeout_ms": cleanup_timeout_ms}
                )
            }
        )

    try:
        require_eval_dependencies()
    except MissingEvalDependencyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = out if out is not None else Path("reports") / f"fusion-mode-ab-{stamp}.md"

    report_path = run_fusion_mode_ab_eval(
        FusionModeAbConfig(
            dataset_path=dataset,
            modes=mode_list,
            runs=runs,
            warmups=warmups,
            cleanup_prompts=cleanup_prompts,  # type: ignore[arg-type]
            cleanup_preflight=cleanup_preflight,
            fused_base=fused_base,
            out_path=out_path,
        )
    )
    typer.echo(f"Wrote fusion mode A/B report: {report_path}")


def main() -> None:
    app()
