"""Fused audio-visual dictation pipeline (TICKET-017)."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ContextManager, Literal

from pydantic import BaseModel, Field, model_validator

from sabi.capture.lip_roi import LipFrame, LipROIConfig, LipROIDetector
from sabi.capture.microphone import MicConfig, MicrophoneSource, Utterance
from sabi.capture.webcam import WebcamConfig, WebcamSource
from sabi.cleanup.ollama import CleanedText, CleanupConfig, CleanupContext, TextCleaner
from sabi.fusion import FusedResult, FusionCombiner, FusionConfig
from sabi.input.hotkey import HotkeyConfig, HotkeyController, TriggerEvent
from sabi.models.asr import ASRModel, ASRModelConfig, ASRResult
from sabi.models.latency import append_latency_row
from sabi.models.vsr.model import VSRModel, VSRModelConfig, VSRResult
from sabi.output.inject import InjectConfig, InjectResult
from sabi.output.inject import paste_text as _real_paste_text
from sabi.pipelines.events import PipelinePhase, PipelineStatusEvent, UiMode, normalize_ui_mode

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "fused_dictate.toml"
DEFAULT_JSONL_DIR = REPO_ROOT / "reports"

PasteDecision = Literal[
    "pasted",
    "withheld_low_confidence",
    "withheld_empty",
    "force_pasted",
    "dry_run",
    "error",
]
ForcePasteMode = Literal["listener", "always", "never"]
Device = Literal["auto", "cuda", "cpu"]


class FusedDictateConfig(BaseModel):
    """Top-level config for :class:`FusedDictatePipeline`."""

    webcam: WebcamConfig = Field(default_factory=WebcamConfig)
    lip_roi: LipROIConfig = Field(default_factory=LipROIConfig)
    vsr: VSRModelConfig = Field(default_factory=VSRModelConfig)
    mic: MicConfig = Field(default_factory=MicConfig)
    asr: ASRModelConfig = Field(default_factory=ASRModelConfig)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    inject: InjectConfig = Field(default_factory=InjectConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)

    parallel: bool = True
    paste_floor_confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    occlusion_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    vad_coverage_floor: float = Field(default=0.5, ge=0.0, le=1.0)
    force_paste_binding: str = "f12"
    force_paste_window_ms: int = Field(default=1500, ge=0)
    force_paste_mode_fused: ForcePasteMode = "listener"
    keep_camera_open: bool = False
    keep_mic_open: bool = True
    predict_timeout_ms: int = Field(default=15000, ge=1)
    dry_run: bool = False
    device_override: Device | None = None
    jsonl_dir: Path = Field(default_factory=lambda: DEFAULT_JSONL_DIR)
    hardware_label: str = "windows"

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _validate_bindings_and_hotkey(self) -> "FusedDictateConfig":
        primary = self.hotkey.binding.strip().lower()
        force = self.force_paste_binding.strip().lower()
        if primary == force:
            raise ValueError(
                "fused_dictate: hotkey.binding and force_paste_binding must differ; "
                f"both are {primary!r}."
            )
        if self.hotkey.mode != "push_to_talk":
            object.__setattr__(
                self,
                "hotkey",
                self.hotkey.model_copy(update={"mode": "push_to_talk"}),
            )
        return self


@dataclass(frozen=True)
class UtteranceProcessed:
    """Final fused event emitted once per utterance."""

    utterance_id: int
    started_at_ns: int
    ended_at_ns: int
    text_raw: str
    text_final: str
    confidence: float
    used_fallback: bool
    decision: PasteDecision
    latencies: dict[str, float]
    fusion: dict[str, Any]
    asr: dict[str, Any]
    vsr: dict[str, Any]
    frame_count: int
    face_present_ratio: float
    duration_ms: float
    vad_coverage: float
    peak_dbfs: float
    pipeline: Literal["fused"] = "fused"
    error: str | None = None


WebcamFactory = Callable[[WebcamConfig], ContextManager[Any]]
ROIFactory = Callable[[LipROIConfig], ContextManager[Any]]
VSRFactory = Callable[[VSRModelConfig], ContextManager[Any]]
MicFactory = Callable[[MicConfig], ContextManager[Any]]
ASRFactory = Callable[[ASRModelConfig], ContextManager[Any]]
CombinerFactory = Callable[[FusionConfig], Any]
CleanerFactory = Callable[[CleanupConfig], ContextManager[Any]]
HotkeyFactory = Callable[[HotkeyConfig], Any]
PasteFunc = Callable[[str, InjectConfig], InjectResult]
LatencyWriter = Callable[..., None]


@dataclass
class _Deps:
    webcam_factory: WebcamFactory
    roi_factory: ROIFactory
    vsr_factory: VSRFactory
    mic_factory: MicFactory
    asr_factory: ASRFactory
    combiner_factory: CombinerFactory
    cleaner_factory: CleanerFactory
    hotkey_factory: HotkeyFactory
    paste_fn: PasteFunc
    latency_writer: LatencyWriter = append_latency_row
    now_ns: Callable[[], int] = time.monotonic_ns
    perf_counter: Callable[[], float] = time.perf_counter
    sleep: Callable[[float], None] = time.sleep


def _default_deps() -> _Deps:
    return _Deps(
        webcam_factory=lambda cfg: WebcamSource(cfg),
        roi_factory=lambda cfg: LipROIDetector(cfg),
        vsr_factory=lambda cfg: VSRModel(cfg),
        mic_factory=lambda cfg: MicrophoneSource(cfg),
        asr_factory=lambda cfg: ASRModel(cfg),
        combiner_factory=lambda cfg: FusionCombiner(cfg),
        cleaner_factory=lambda cfg: TextCleaner(cfg),
        hotkey_factory=lambda cfg: HotkeyController(cfg),
        paste_fn=_real_paste_text,
    )


@dataclass
class _ActiveUtterance:
    utterance_id: int
    started_at_ns: int
    t0_perf: float
    stop_event: threading.Event
    mic_start_event: threading.Event
    mic_end_event: threading.Event
    capture_open_ms: float = 0.0
    mic_open_ms: float = 0.0
    webcam_cm: ContextManager[Any] | None = None
    webcam: Any | None = None
    mic_cm: ContextManager[Any] | None = None
    mic: Any | None = None
    capture_thread: threading.Thread | None = None
    mic_thread: threading.Thread | None = None
    frames: list[LipFrame] = None  # type: ignore[assignment]
    face_present: int = 0
    face_missing: int = 0
    roi_ms: float = 0.0
    first_frame_perf: float | None = None
    last_frame_perf: float | None = None
    utterance: Utterance | None = None
    mic_error: str | None = None

    def __post_init__(self) -> None:
        if self.frames is None:
            self.frames = []


@dataclass
class _PendingForcePaste:
    processed: UtteranceProcessed
    timer: threading.Timer
    text_final: str
    stash_perf: float


class _JsonlWriter:
    """Append-only writer for ``reports/fused_dictate_<date>.jsonl``."""

    def __init__(self, directory: Path, *, enabled: bool = True) -> None:
        self._dir = directory
        self._enabled = enabled
        self._lock = threading.Lock()
        self._path: Path | None = None

    @property
    def path(self) -> Path | None:
        return self._path

    def _path_for(self, ts_ns: int) -> Path:
        dt = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
        return self._dir / f"fused_dictate_{dt.strftime('%Y%m%d')}.jsonl"

    def write(self, record: dict[str, Any]) -> None:
        if not self._enabled:
            return
        ts_ns = int(record.get("ts_ns") or time.time_ns())
        record.setdefault("ts_ns", ts_ns)
        path = self._path_for(ts_ns)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._path = path


class FusedDictatePipeline:
    """Fused dictation pipeline (TICKET-017)."""

    def __init__(
        self,
        config: FusedDictateConfig | None = None,
        *,
        deps: _Deps | None = None,
        jsonl_writer: _JsonlWriter | None = None,
    ) -> None:
        self._config = config or FusedDictateConfig()
        self._deps = deps or _default_deps()
        if self._config.device_override is not None:
            device_update = {"device": self._config.device_override}
            self._config = self._config.model_copy(
                update={
                    "vsr": self._config.vsr.model_copy(update=device_update),
                    "asr": self._config.asr.model_copy(update=device_update),
                }
            )
        if self._config.dry_run and not self._config.inject.dry_run:
            self._config = self._config.model_copy(
                update={"inject": self._config.inject.model_copy(update={"dry_run": True})}
            )

        self._vsr_cm: ContextManager[Any] | None = None
        self._vsr: Any | None = None
        self._asr_cm: ContextManager[Any] | None = None
        self._asr: Any | None = None
        self._cleaner_cm: ContextManager[Any] | None = None
        self._cleaner: Any | None = None
        self._roi_cm: ContextManager[Any] | None = None
        self._roi: Any | None = None
        self._combiner: Any | None = None
        self._primary_hk: Any | None = None
        self._force_hk: Any | None = None
        self._persistent_webcam_cm: ContextManager[Any] | None = None
        self._persistent_webcam: Any | None = None
        self._persistent_mic_cm: ContextManager[Any] | None = None
        self._persistent_mic: Any | None = None
        self._warmup_ms = 0.0

        self._state_lock = threading.RLock()
        self._subscribers: list[Callable[[UtteranceProcessed], None]] = []
        self._status_subscribers: list[Callable[[PipelineStatusEvent], None]] = []
        self._last_status: PipelineStatusEvent | None = None
        self._utterance_counter = 0
        self._active: _ActiveUtterance | None = None
        self._pending: dict[int, _PendingForcePaste] = {}
        self._dispatch_threads: list[threading.Thread] = []
        self._ollama_ok: bool | None = None
        self._jsonl = jsonl_writer or _JsonlWriter(self._config.jsonl_dir)
        self._entered = False
        self._closed = False

    @property
    def config(self) -> FusedDictateConfig:
        return self._config

    @property
    def jsonl_path(self) -> Path | None:
        return self._jsonl.path

    def subscribe(self, callback: Callable[[UtteranceProcessed], None]) -> None:
        with self._state_lock:
            self._subscribers.append(callback)

    def subscribe_status(
        self,
        callback: Callable[[PipelineStatusEvent], None],
        *,
        replay: bool = True,
    ) -> None:
        with self._state_lock:
            self._status_subscribers.append(callback)
            last = self._last_status
        if replay and last is not None:
            callback(last)

    def _notify(self, event: UtteranceProcessed) -> None:
        with self._state_lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                logger.exception("fused_dictate subscriber raised")

    def _notify_status(self, event: PipelineStatusEvent) -> None:
        with self._state_lock:
            self._last_status = event
            subs = list(self._status_subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                logger.exception("fused_dictate status subscriber raised")

    def _emit_status(
        self,
        mode: PipelinePhase,
        *,
        utterance_id: int | None = None,
        message: str | None = None,
        clipboard_restore_deadline_ns: int | None = None,
        pending_force_paste: bool = False,
    ) -> None:
        self._notify_status(
            PipelineStatusEvent(
                pipeline="fused",
                mode=mode,
                utterance_id=utterance_id,
                hotkey_binding=self._config.hotkey.binding,
                force_paste_binding=self._config.force_paste_binding,
                ollama_ok=self._ollama_ok,
                ollama_model=self._config.cleanup.model,
                cuda_status=_cuda_status(self._config.vsr.device),
                message=message,
                clipboard_restore_deadline_ns=clipboard_restore_deadline_ns,
                pending_force_paste=pending_force_paste,
                created_at_ns=self._deps.now_ns(),
            )
        )

    def __enter__(self) -> "FusedDictatePipeline":
        if self._entered:
            raise RuntimeError("FusedDictatePipeline is not re-entrant")
        self._entered = True
        self._vsr_cm = self._deps.vsr_factory(self._config.vsr)
        self._vsr = self._vsr_cm.__enter__()
        self._asr_cm = self._deps.asr_factory(self._config.asr)
        self._asr = self._asr_cm.__enter__()
        self._cleaner_cm = self._deps.cleaner_factory(self._config.cleanup)
        self._cleaner = self._cleaner_cm.__enter__()
        self._roi_cm = self._deps.roi_factory(self._config.lip_roi)
        self._roi = self._roi_cm.__enter__()
        self._combiner = self._deps.combiner_factory(self._config.fusion)

        t_warm = self._deps.perf_counter()
        for model in (self._vsr, self._asr):
            warm = getattr(model, "warm_up", None)
            if callable(warm):
                try:
                    warm()
                except Exception:
                    logger.warning("fused_dictate: model warm_up failed", exc_info=True)
        self._warmup_ms = (self._deps.perf_counter() - t_warm) * 1000.0

        try:
            if hasattr(self._cleaner, "is_available"):
                self._ollama_ok = bool(self._cleaner.is_available())
        except Exception:
            self._ollama_ok = False

        if self._config.keep_camera_open:
            self._persistent_webcam_cm = self._deps.webcam_factory(self._config.webcam)
            self._persistent_webcam = self._persistent_webcam_cm.__enter__()
        if self._config.keep_mic_open:
            self._persistent_mic_cm = self._deps.mic_factory(self._config.mic)
            self._persistent_mic = self._persistent_mic_cm.__enter__()

        self._primary_hk = self._deps.hotkey_factory(self._config.hotkey)
        self._primary_hk.bus.subscribe_start(self.on_trigger_start)
        self._primary_hk.bus.subscribe_stop(self.on_trigger_stop)
        self._primary_hk.start()

        if self._config.force_paste_mode_fused == "listener":
            force_cfg = HotkeyConfig(
                mode="push_to_talk",
                binding=self._config.force_paste_binding,
                min_hold_ms=0,
                cooldown_ms=250,
            )
            self._force_hk = self._deps.hotkey_factory(force_cfg)
            self._force_hk.bus.subscribe_start(self._handle_force_paste)
            self._force_hk.start()

        self._emit_status("idle")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._state_lock:
            active = self._active
            self._active = None
            pending = list(self._pending.values())
            self._pending.clear()
            dispatch_threads = list(self._dispatch_threads)
            self._dispatch_threads.clear()

        for entry in pending:
            entry.timer.cancel()
        if active is not None:
            active.stop_event.set()
            active.mic_end_event.set()
            for thread in (active.capture_thread, active.mic_thread):
                if thread is not None:
                    _safe_join(thread, timeout=1.0)
            self._close_per_trigger(active)
        for thread in dispatch_threads:
            _safe_join(thread, timeout=2.0)
        for hk in (self._primary_hk, self._force_hk):
            if hk is not None:
                try:
                    hk.stop()
                except Exception:
                    logger.exception("fused_dictate: hotkey.stop failed")
        self._primary_hk = None
        self._force_hk = None

        for cm_attr in (
            "_persistent_mic_cm",
            "_persistent_webcam_cm",
            "_roi_cm",
            "_cleaner_cm",
            "_asr_cm",
            "_vsr_cm",
        ):
            cm = getattr(self, cm_attr, None)
            if cm is not None:
                try:
                    cm.__exit__(None, None, None)
                except Exception:
                    logger.exception("fused_dictate: %s close failed", cm_attr)
                setattr(self, cm_attr, None)
        self._persistent_mic = None
        self._persistent_webcam = None
        self._roi = None
        self._cleaner = None
        self._asr = None
        self._vsr = None
        self._entered = False

    def on_trigger_start(self, event: TriggerEvent) -> None:
        with self._state_lock:
            if self._active is not None:
                self._active.stop_event.set()
                self._active.mic_end_event.set()
            self._utterance_counter += 1
            active = _ActiveUtterance(
                utterance_id=self._utterance_counter,
                started_at_ns=event.started_at_ns,
                t0_perf=self._deps.perf_counter(),
                stop_event=threading.Event(),
                mic_start_event=threading.Event(),
                mic_end_event=threading.Event(),
            )
            self._active = active

        self._jsonl.write(
            {
                "event_type": "trigger_start",
                "utterance_id": active.utterance_id,
                "ts_ns": event.started_at_ns,
                "trigger_id": event.trigger_id,
                "mode": event.mode,
                "reason": event.reason,
            }
        )
        self._emit_status("recording", utterance_id=active.utterance_id)
        try:
            self._open_capture_devices(active)
        except Exception as exc:
            with self._state_lock:
                self._active = None
            self._emit_error(
                active.utterance_id,
                active.started_at_ns,
                f"capture_open_failed: {exc}",
            )
            return

        active.capture_thread = threading.Thread(
            target=self._capture_loop,
            args=(active,),
            name=f"sabi-fused-video-{active.utterance_id}",
            daemon=True,
        )
        active.mic_thread = threading.Thread(
            target=self._mic_loop,
            args=(active,),
            name=f"sabi-fused-audio-{active.utterance_id}",
            daemon=True,
        )
        active.capture_thread.start()
        active.mic_thread.start()
        active.mic_start_event.set()

    def on_trigger_stop(self, event: TriggerEvent) -> None:
        with self._state_lock:
            active = self._active
            self._active = None
        if active is None:
            return
        active.stop_event.set()
        active.mic_end_event.set()
        for thread in (active.capture_thread, active.mic_thread):
            if thread is not None:
                thread.join(timeout=2.0)
        self._close_per_trigger(active)

        self._jsonl.write(
            {
                "event_type": "trigger_stop",
                "utterance_id": active.utterance_id,
                "ts_ns": event.started_at_ns,
                "trigger_id": event.trigger_id,
                "frame_count": len(active.frames),
                "face_present": active.face_present,
                "face_missing": active.face_missing,
                "audio_samples": (
                    0 if active.utterance is None else int(active.utterance.samples.size)
                ),
            }
        )
        self._emit_status("decoding", utterance_id=active.utterance_id)
        thread = threading.Thread(
            target=self._dispatch_utterance,
            args=(active,),
            name=f"sabi-fused-dispatch-{active.utterance_id}",
            daemon=True,
        )
        with self._state_lock:
            self._dispatch_threads = [t for t in self._dispatch_threads if t.is_alive()]
            self._dispatch_threads.append(thread)
        thread.start()

    def _open_capture_devices(self, active: _ActiveUtterance) -> None:
        if self._config.keep_camera_open and self._persistent_webcam is not None:
            active.webcam = self._persistent_webcam
        else:
            t_open = self._deps.perf_counter()
            active.webcam_cm = self._deps.webcam_factory(self._config.webcam)
            active.webcam = active.webcam_cm.__enter__()
            active.capture_open_ms = (self._deps.perf_counter() - t_open) * 1000.0
        if self._config.keep_mic_open and self._persistent_mic is not None:
            active.mic = self._persistent_mic
        else:
            t_open = self._deps.perf_counter()
            active.mic_cm = self._deps.mic_factory(self._config.mic)
            active.mic = active.mic_cm.__enter__()
            active.mic_open_ms = (self._deps.perf_counter() - t_open) * 1000.0

    def _close_per_trigger(self, active: _ActiveUtterance) -> None:
        for attr in ("webcam_cm", "mic_cm"):
            cm = getattr(active, attr, None)
            if cm is not None:
                try:
                    cm.__exit__(None, None, None)
                except Exception:
                    logger.exception("fused_dictate: per-trigger %s close failed", attr)
                setattr(active, attr, None)

    def _capture_loop(self, active: _ActiveUtterance) -> None:
        assert self._roi is not None
        last_ts_ns = -1
        while not active.stop_event.is_set():
            try:
                ts_ns, frame_rgb = active.webcam.get_latest(timeout=0.1)
            except Exception:
                if active.stop_event.is_set():
                    break
                continue
            if ts_ns == last_ts_ns:
                self._deps.sleep(0.005)
                continue
            last_ts_ns = ts_ns
            now_perf = self._deps.perf_counter()
            active.first_frame_perf = active.first_frame_perf or now_perf
            active.last_frame_perf = now_perf
            roi_t0 = self._deps.perf_counter()
            try:
                lip = self._roi.process_frame(ts_ns, frame_rgb)
            except Exception:
                lip = None
            active.roi_ms += (self._deps.perf_counter() - roi_t0) * 1000.0
            if lip is None:
                active.face_missing += 1
            else:
                active.face_present += 1
                active.frames.append(lip)

    def _mic_loop(self, active: _ActiveUtterance) -> None:
        try:
            active.utterance = active.mic.push_to_talk_segment(
                active.mic_start_event,
                active.mic_end_event,
            )
        except Exception as exc:
            active.mic_error = str(exc)

    def _dispatch_utterance(self, active: _ActiveUtterance) -> None:
        try:
            self._dispatch_utterance_inner(active)
        except Exception as exc:
            logger.exception("fused_dictate: dispatch crashed")
            self._emit_error(active.utterance_id, active.started_at_ns, f"dispatch_crash: {exc}")

    def _dispatch_utterance_inner(self, active: _ActiveUtterance) -> None:
        capture_ms = max((self._deps.now_ns() - active.started_at_ns) / 1_000_000.0, 0.0)
        if active.first_frame_perf is not None and active.last_frame_perf is not None:
            capture_ms = (active.last_frame_perf - active.first_frame_perf) * 1000.0
        total_frames = active.face_present + active.face_missing
        face_ratio = active.face_present / total_frames if total_frames else 0.0
        utt = active.utterance
        asr_silent = _is_silent(utt, self._config)
        vsr_no_face = not active.frames or face_ratio < self._config.occlusion_threshold
        if asr_silent and vsr_no_face:
            self._emit_error(
                active.utterance_id,
                active.started_at_ns,
                "neither modality captured input",
                active=active,
                capture_ms=capture_ms,
                face_ratio=face_ratio,
            )
            return

        assert self._vsr is not None and self._asr is not None and self._combiner is not None
        vsr_result: VSRResult | None = None
        asr_result: ASRResult | None = None
        vsr_ms = 0.0
        asr_ms = 0.0
        if self._config.parallel:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {}
                if not vsr_no_face:
                    t = self._deps.perf_counter()
                    futures["vsr"] = (pool.submit(self._vsr.predict, active.frames), t)
                if not asr_silent and utt is not None:
                    t = self._deps.perf_counter()
                    futures["asr"] = (pool.submit(self._asr.transcribe, utt), t)
                for name, (future, start) in futures.items():
                    try:
                        result = future.result(timeout=self._config.predict_timeout_ms / 1000.0)
                    except Exception:
                        logger.exception("fused_dictate: %s branch failed", name)
                        continue
                    elapsed = (self._deps.perf_counter() - start) * 1000.0
                    if name == "vsr":
                        vsr_result = result
                        vsr_ms = float(getattr(result, "latency_ms", elapsed))
                    else:
                        asr_result = result
                        asr_ms = float(getattr(result, "latency_ms", elapsed))
        else:
            if not vsr_no_face:
                start = self._deps.perf_counter()
                vsr_result = self._vsr.predict(active.frames)
                fallback_ms = (self._deps.perf_counter() - start) * 1000.0
                vsr_ms = float(getattr(vsr_result, "latency_ms", fallback_ms))
            if not asr_silent and utt is not None:
                start = self._deps.perf_counter()
                asr_result = self._asr.transcribe(utt)
                fallback_ms = (self._deps.perf_counter() - start) * 1000.0
                asr_ms = float(getattr(asr_result, "latency_ms", fallback_ms))

        fused: FusedResult = self._combiner.combine(asr_result, vsr_result)
        if vsr_no_face:
            fused = replace(fused, mode_reason="vsr no-face")
        if asr_silent:
            fused = replace(fused, mode_reason="asr silent")
        if not fused.text.strip():
            self._emit_error(
                active.utterance_id,
                active.started_at_ns,
                "neither modality captured input",
                active=active,
                capture_ms=capture_ms,
                face_ratio=face_ratio,
            )
            return

        self._emit_status("cleaning", utterance_id=active.utterance_id)
        assert self._cleaner is not None
        cleanup_t0 = self._deps.perf_counter()
        try:
            cleaned: CleanedText = self._cleaner.cleanup(
                fused.text,
                CleanupContext(source="fused", register_hint="dictation"),
            )
        except Exception as exc:
            cleaned = CleanedText(
                text=fused.text,
                latency_ms=(self._deps.perf_counter() - cleanup_t0) * 1000.0,
                used_fallback=True,
                reason=f"cleanup_exception: {exc}",
            )

        processed = self._build_processed(
            active=active,
            decision=self._route_decision(fused.confidence),
            text_raw=fused.text,
            text_final=cleaned.text,
            confidence=fused.confidence,
            used_fallback=cleaned.used_fallback,
            capture_ms=capture_ms,
            vsr_ms=vsr_ms,
            asr_ms=asr_ms,
            fusion_ms=fused.latency_ms,
            cleanup_ms=cleaned.latency_ms,
            inject_ms=0.0,
            fusion=fused,
            asr_result=asr_result,
            vsr_result=vsr_result,
            face_ratio=face_ratio,
            error=None,
        )
        if processed.decision == "withheld_low_confidence":
            self._schedule_force_paste(processed)
            return

        self._emit_status("pasting", utterance_id=active.utterance_id)
        inject_ms, decision, error, restore_deadline = self._perform_paste(
            cleaned.text, base_decision=processed.decision
        )
        if restore_deadline is not None:
            self._emit_status(
                "pasting",
                utterance_id=active.utterance_id,
                clipboard_restore_deadline_ns=restore_deadline,
            )
        latencies = {**processed.latencies, "inject_ms": inject_ms}
        self._finalize(
            replace(processed, decision=decision, error=error, latencies=latencies)
        )

    def _route_decision(self, confidence: float) -> PasteDecision:
        if self._config.force_paste_mode_fused == "always":
            return "pasted"
        if confidence >= self._config.paste_floor_confidence:
            return "pasted"
        return "withheld_low_confidence"

    def _perform_paste(
        self,
        text: str,
        *,
        base_decision: PasteDecision,
    ) -> tuple[float, PasteDecision, str | None, int | None]:
        if self._config.dry_run:
            print(text)
            return 0.0, "dry_run", None, None
        try:
            cfg = self._config.inject
            result = self._deps.paste_fn(text, cfg)
        except Exception as exc:
            return 0.0, "error", f"paste_error: {exc}", None
        restore_deadline = None
        if getattr(result, "error", None) is None:
            restore_deadline = self._deps.now_ns() + (cfg.restore_delay_ms * 1_000_000)
        return (
            float(getattr(result, "latency_ms", 0.0)),
            base_decision,
            getattr(result, "error", None),
            restore_deadline,
        )

    def _schedule_force_paste(self, processed: UtteranceProcessed) -> None:
        def _on_expiry() -> None:
            with self._state_lock:
                entry = self._pending.pop(processed.utterance_id, None)
            if entry is not None:
                self._finalize(entry.processed)

        timer = threading.Timer(self._config.force_paste_window_ms / 1000.0, _on_expiry)
        timer.daemon = True
        with self._state_lock:
            self._pending[processed.utterance_id] = _PendingForcePaste(
                processed=processed,
                timer=timer,
                text_final=processed.text_final,
                stash_perf=self._deps.perf_counter(),
            )
        timer.start()
        self._emit_status(
            "idle",
            utterance_id=processed.utterance_id,
            message=f"{self._config.force_paste_binding.upper()} to paste anyway",
            pending_force_paste=True,
        )

    def _handle_force_paste(self, event: TriggerEvent) -> None:
        if self._config.force_paste_mode_fused != "listener":
            return
        with self._state_lock:
            if not self._pending:
                return
            utterance_id = max(self._pending.keys())
            entry = self._pending.pop(utterance_id)
        entry.timer.cancel()
        self._jsonl.write(
            {
                "event_type": "force_paste_hit",
                "utterance_id": entry.processed.utterance_id,
                "ts_ns": event.started_at_ns,
                "trigger_id": event.trigger_id,
                "text_final": entry.text_final,
            }
        )
        self._emit_status("pasting", utterance_id=entry.processed.utterance_id)
        inject_ms, decision, error, restore_deadline = self._perform_paste(
            entry.text_final, base_decision="force_pasted"
        )
        if restore_deadline is not None:
            self._emit_status(
                "pasting",
                utterance_id=entry.processed.utterance_id,
                clipboard_restore_deadline_ns=restore_deadline,
            )
        latencies = {**entry.processed.latencies, "inject_ms": inject_ms}
        self._finalize(
            replace(entry.processed, decision=decision, error=error, latencies=latencies)
        )

    def _build_processed(
        self,
        *,
        active: _ActiveUtterance,
        decision: PasteDecision,
        text_raw: str,
        text_final: str,
        confidence: float,
        used_fallback: bool,
        capture_ms: float,
        vsr_ms: float,
        asr_ms: float,
        fusion_ms: float,
        cleanup_ms: float,
        inject_ms: float,
        fusion: FusedResult,
        asr_result: ASRResult | None,
        vsr_result: VSRResult | None,
        face_ratio: float,
        error: str | None,
    ) -> UtteranceProcessed:
        utt = active.utterance
        duration_ms = 0.0 if utt is None else float(utt.duration_s * 1000.0)
        latencies = {
            "capture_ms": float(capture_ms),
            "roi_ms": float(active.roi_ms),
            "vsr_ms": float(vsr_ms),
            "asr_ms": float(asr_ms),
            "fusion_ms": float(fusion_ms),
            "cleanup_ms": float(cleanup_ms),
            "inject_ms": float(inject_ms),
            "warmup_ms": float(self._warmup_ms),
            "capture_open_ms": float(active.capture_open_ms),
            "mic_open_ms": float(active.mic_open_ms),
            "total_ms": (self._deps.perf_counter() - active.t0_perf) * 1000.0,
        }
        return UtteranceProcessed(
            utterance_id=active.utterance_id,
            started_at_ns=active.started_at_ns,
            ended_at_ns=self._deps.now_ns(),
            text_raw=text_raw,
            text_final=text_final,
            confidence=float(confidence),
            used_fallback=used_fallback,
            decision=decision,
            latencies=latencies,
            fusion=_fusion_block(fusion),
            asr=_asr_block(asr_result),
            vsr=_vsr_block(vsr_result),
            frame_count=len(active.frames),
            face_present_ratio=face_ratio,
            duration_ms=duration_ms,
            vad_coverage=0.0 if utt is None else float(utt.vad_coverage),
            peak_dbfs=-math.inf if utt is None else float(utt.peak_dbfs),
            error=error,
        )

    def _emit_error(
        self,
        utterance_id: int,
        started_at_ns: int,
        reason: str,
        *,
        active: _ActiveUtterance | None = None,
        capture_ms: float = 0.0,
        face_ratio: float = 0.0,
    ) -> None:
        self._jsonl.write(
            {
                "event_type": "pipeline_error",
                "utterance_id": utterance_id,
                "ts_ns": self._deps.now_ns(),
                "reason": reason,
            }
        )
        if active is None:
            latencies = _zero_latencies()
            frame_count = 0
        else:
            latencies = {
                **_zero_latencies(),
                "capture_ms": capture_ms,
                "roi_ms": active.roi_ms,
                "capture_open_ms": active.capture_open_ms,
                "mic_open_ms": active.mic_open_ms,
                "warmup_ms": self._warmup_ms,
                "total_ms": (self._deps.perf_counter() - active.t0_perf) * 1000.0,
            }
            frame_count = len(active.frames)
        processed = UtteranceProcessed(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            ended_at_ns=self._deps.now_ns(),
            text_raw="",
            text_final="",
            confidence=0.0,
            used_fallback=False,
            decision="error",
            latencies=latencies,
            fusion={},
            asr={},
            vsr={},
            frame_count=frame_count,
            face_present_ratio=face_ratio,
            duration_ms=0.0,
            vad_coverage=0.0,
            peak_dbfs=-math.inf,
            error=reason,
        )
        self._finalize(processed)

    def _finalize(self, processed: UtteranceProcessed) -> None:
        self._jsonl.write(
            {
                "event_type": "utterance_processed",
                "utterance_id": processed.utterance_id,
                "ts_ns": processed.ended_at_ns,
                "started_at_ns": processed.started_at_ns,
                "pipeline": "fused",
                "text_raw": processed.text_raw,
                "text_final": processed.text_final,
                "confidence": processed.confidence,
                "used_fallback": processed.used_fallback,
                "decision": processed.decision,
                "cleanup": {
                    "prompt_version": self._config.cleanup.prompt_version,
                    "used_fallback": processed.used_fallback,
                },
                "latencies": processed.latencies,
                "fusion": processed.fusion,
                "asr": processed.asr,
                "vsr": processed.vsr,
                "frame_count": processed.frame_count,
                "face_present_ratio": processed.face_present_ratio,
                "duration_ms": processed.duration_ms,
                "vad_coverage": processed.vad_coverage,
                "peak_dbfs": processed.peak_dbfs,
                "error": processed.error,
            }
        )
        lat = processed.latencies
        notes = (
            f"decision={processed.decision} confidence={processed.confidence:.2f} "
            f"fusion={processed.fusion.get('mode_reason', '-')} "
            f"prompt={self._config.cleanup.prompt_version} "
            f"fallback={processed.used_fallback} "
            f"[cap={lat['capture_ms']:.0f} roi={lat['roi_ms']:.0f} "
            f"vsr={lat['vsr_ms']:.0f} asr={lat['asr_ms']:.0f} "
            f"fusion={lat['fusion_ms']:.1f} clean={lat['cleanup_ms']:.0f} "
            f"inject={lat['inject_ms']:.0f}]"
        )
        if processed.error:
            notes += f" error={processed.error}"
        try:
            self._deps.latency_writer(
                "TICKET-017",
                self._config.hardware_label,
                "pipeline",
                processed.latencies["total_ms"],
                1,
                notes,
            )
        except Exception:
            logger.exception("fused_dictate: failed to append latency row")
        self._notify(processed)
        self._emit_status("idle", utterance_id=processed.utterance_id)


def _is_silent(utt: Utterance | None, cfg: FusedDictateConfig) -> bool:
    if utt is None:
        return True
    if utt.samples.size == 0:
        return True
    if utt.peak_dbfs == float("-inf") or utt.peak_dbfs <= cfg.asr.silence_peak_dbfs:
        return True
    if utt.vad_coverage < cfg.vad_coverage_floor:
        return True
    return False


def _fusion_block(result: FusedResult) -> dict[str, Any]:
    return {
        "text": result.text,
        "confidence": result.confidence,
        "source_weights": result.source_weights,
        "per_word_origin": result.per_word_origin,
        "per_word_confidence": result.per_word_confidence,
        "mode_used": result.mode_used,
        "mode_reason": result.mode_reason,
        "latency_ms": result.latency_ms,
    }


def _asr_block(result: ASRResult | None) -> dict[str, Any]:
    if result is None:
        return {"text": "", "confidence": 0.0, "latency_ms": 0.0}
    return {"text": result.text, "confidence": result.confidence, "latency_ms": result.latency_ms}


def _vsr_block(result: VSRResult | None) -> dict[str, Any]:
    if result is None:
        return {"text": "", "confidence": 0.0, "latency_ms": 0.0}
    return {"text": result.text, "confidence": result.confidence, "latency_ms": result.latency_ms}


def _zero_latencies() -> dict[str, float]:
    return {
        "capture_ms": 0.0,
        "roi_ms": 0.0,
        "vsr_ms": 0.0,
        "asr_ms": 0.0,
        "fusion_ms": 0.0,
        "cleanup_ms": 0.0,
        "inject_ms": 0.0,
        "warmup_ms": 0.0,
        "capture_open_ms": 0.0,
        "mic_open_ms": 0.0,
        "total_ms": 0.0,
    }


def _safe_join(thread: threading.Thread, *, timeout: float) -> None:
    try:
        thread.join(timeout=timeout)
    except RuntimeError:
        pass


def _update_from_section(model: BaseModel, section: dict[str, Any] | None) -> BaseModel:
    if not section:
        return model
    overrides = {k: v for k, v in section.items() if k in model.__class__.model_fields}
    return model.model_copy(update=overrides) if overrides else model


def load_fused_dictate_config(path: Path | None = None) -> FusedDictateConfig:
    target = path if path is not None else DEFAULT_CONFIG_PATH
    cfg = FusedDictateConfig()
    if not target.is_file():
        return cfg
    with target.open("rb") as f:
        data = tomllib.load(f)
    cfg = cfg.model_copy(
        update={
            "webcam": _update_from_section(cfg.webcam, data.get("webcam")),
            "lip_roi": _update_from_section(cfg.lip_roi, data.get("lip_roi")),
            "vsr": _update_from_section(cfg.vsr, data.get("vsr")),
            "mic": _update_from_section(cfg.mic, data.get("mic")),
            "asr": _update_from_section(cfg.asr, data.get("asr")),
            "fusion": _update_from_section(cfg.fusion, data.get("fusion")),
            "cleanup": _update_from_section(cfg.cleanup, data.get("cleanup")),
            "inject": _update_from_section(cfg.inject, data.get("inject")),
            "hotkey": _update_from_section(cfg.hotkey, data.get("hotkey")),
        }
    )
    pipeline = data.get("pipeline") or {}
    overrides = {k: v for k, v in pipeline.items() if k in FusedDictateConfig.model_fields}
    if "jsonl_dir" in overrides and isinstance(overrides["jsonl_dir"], str):
        overrides["jsonl_dir"] = Path(overrides["jsonl_dir"])
    return FusedDictateConfig.model_validate({**cfg.model_dump(), **overrides})


def run_fused_dictate(
    config: FusedDictateConfig | None = None,
    *,
    deps: _Deps | None = None,
    stop_event: threading.Event | None = None,
    ui: UiMode = "tui",
) -> int:
    cfg = config or FusedDictateConfig()
    stop = stop_event if stop_event is not None else threading.Event()
    ui_mode = normalize_ui_mode(ui)
    print(
        (
            "sabi fused-dictate: binding={binding} force_paste={fmode}({fbind}) "
            "dry_run={dry} parallel={parallel}"
        ).format(
            binding=cfg.hotkey.binding,
            fmode=cfg.force_paste_mode_fused,
            fbind=cfg.force_paste_binding,
            dry=cfg.dry_run,
            parallel=cfg.parallel,
        )
    )
    print("Hold the hotkey to dictate with camera + mic. Ctrl+C to exit.")
    status_tui = None
    if ui_mode == "tui":
        from sabi.ui.status_tui import StatusTUI

        status_tui = StatusTUI()
        status_tui.handle_status(_initial_fused_status(cfg))
        status_tui.start()
    pipeline = FusedDictatePipeline(cfg, deps=deps)
    if status_tui is not None:
        pipeline.subscribe_status(status_tui.handle_status)
        pipeline.subscribe(status_tui.handle_utterance)
    else:
        pipeline.subscribe(_print_fused_event)
    try:
        with pipeline:
            try:
                while not stop.is_set():
                    stop.wait(timeout=0.5)
            except KeyboardInterrupt:
                print("\nexiting...")
                stop.set()
    finally:
        if status_tui is not None:
            status_tui.stop()
    return 0


def _initial_fused_status(cfg: FusedDictateConfig) -> PipelineStatusEvent:
    return PipelineStatusEvent(
        pipeline="fused",
        mode="idle",
        hotkey_binding=cfg.hotkey.binding,
        force_paste_binding=cfg.force_paste_binding,
        ollama_ok=None,
        ollama_model=cfg.cleanup.model,
        cuda_status=_cuda_status(cfg.vsr.device),
        created_at_ns=time.monotonic_ns(),
    )


def _print_fused_event(ev: UtteranceProcessed) -> None:
    line = (
        f"[{ev.decision.upper()}] id={ev.utterance_id} "
        f"text={ev.text_final!r} conf={ev.confidence:.2f} "
        f"mode={ev.fusion.get('mode_used', '-')} total_ms={ev.latencies['total_ms']:.0f}"
    )
    if ev.error:
        line += f" error={ev.error}"
    print(line)


def _cuda_status(device: Any) -> str:
    try:
        import torch

        available = bool(torch.cuda.is_available())
    except Exception:
        available = False
    selected = str(device or "auto")
    return f"{selected} ({'available' if available else 'unavailable'})"


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "FusedDictateConfig",
    "FusedDictatePipeline",
    "PasteDecision",
    "UtteranceProcessed",
    "load_fused_dictate_config",
    "run_fused_dictate",
]
