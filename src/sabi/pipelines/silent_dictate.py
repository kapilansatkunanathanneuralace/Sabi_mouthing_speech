"""Silent-dictation pipeline (TICKET-011).

Wires the webcam (TICKET-003), lip-ROI (TICKET-004), Chaplin VSR
(TICKET-005), Ollama cleanup (TICKET-008), clipboard paste (TICKET-009)
and hotkey trigger (TICKET-010) behind :class:`SilentDictatePipeline`
and the ``python -m sabi silent-dictate`` CLI.

Design notes:

* The webcam opens only while the hotkey is held; ``capture_open_ms``
  is logged separately from the per-utterance budget so the Windows
  DirectShow open cost (500-1500 ms) does not get attributed to VSR.
* Low-confidence utterances are held back for ``force_paste_window_ms``
  (default 1.5 s); a second :class:`~sabi.input.HotkeyController` bound
  to F12 lets the user confirm and paste anyway. See
  ``force_paste_mode`` for the ``listener`` / ``always`` / ``never``
  policies.
* Every component is swappable via the ``deps=`` seam so the full
  pipeline can be unit-tested without a webcam, CUDA, Ollama daemon,
  clipboard, or real keyboard hook.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ContextManager, Literal

from pydantic import BaseModel, Field, model_validator

from sabi.capture.lip_roi import LipFrame, LipROIConfig, LipROIDetector
from sabi.capture.webcam import WebcamConfig, WebcamSource
from sabi.cleanup.ollama import (
    CleanedText,
    CleanupConfig,
    CleanupContext,
    TextCleaner,
)
from sabi.input.hotkey import (
    HotkeyConfig,
    HotkeyController,
    TriggerEvent,
)
from sabi.models.latency import append_latency_row
from sabi.models.vsr.model import VSRModel, VSRModelConfig, VSRResult
from sabi.output.inject import InjectConfig, InjectResult
from sabi.output.inject import paste_text as _real_paste_text
from sabi.pipelines.events import PipelinePhase, PipelineStatusEvent, UiMode, normalize_ui_mode
from sabi.runtime.paths import configs_dir, reports_dir

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = configs_dir() / "silent_dictate.toml"
DEFAULT_JSONL_DIR = reports_dir()

PasteDecision = Literal[
    "pasted",
    "withheld_low_confidence",
    "withheld_occluded",
    "withheld_empty",
    "force_pasted",
    "dry_run",
    "error",
]
ForcePasteMode = Literal["listener", "always", "never"]
Device = Literal["auto", "cuda", "cpu"]


class SilentDictateConfig(BaseModel):
    """Top-level config for :class:`SilentDictatePipeline`.

    Composes the per-module configs plus pipeline-level knobs. Load from
    ``configs/silent_dictate.toml`` via :func:`load_silent_dictate_config`;
    the loader overlays only the fields that appear in the TOML on top
    of the component defaults so partial files are fine.
    """

    webcam: WebcamConfig = Field(default_factory=WebcamConfig)
    lip_roi: LipROIConfig = Field(default_factory=LipROIConfig)
    vsr: VSRModelConfig = Field(default_factory=VSRModelConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    inject: InjectConfig = Field(default_factory=InjectConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)

    confidence_floor: float = Field(default=0.35, ge=0.0, le=1.0)
    occlusion_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum fraction of captured frames that must have a detected face.",
    )
    force_paste_binding: str = Field(default="f12")
    force_paste_window_ms: int = Field(default=1500, ge=0)
    force_paste_mode: ForcePasteMode = "listener"
    keep_camera_open: bool = False
    dry_run: bool = False
    device_override: Device | None = Field(
        default=None,
        description="If set, overrides `vsr.device` at pipeline construction time.",
    )
    jsonl_dir: Path = Field(default_factory=lambda: DEFAULT_JSONL_DIR)
    hardware_label: str = Field(
        default="windows",
        description="Hardware tag used in reports/latency-log.md rows.",
    )

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _validate_bindings(self) -> "SilentDictateConfig":
        primary = self.hotkey.binding.strip().lower()
        force = self.force_paste_binding.strip().lower()
        if primary == force:
            raise ValueError(
                "silent_dictate: hotkey.binding and force_paste_binding must differ; "
                f"both are {primary!r}."
            )
        return self


@dataclass(frozen=True)
class UtteranceProcessed:
    """Final event emitted once per utterance.

    TICKET-013 (overlay) and TICKET-014 (eval harness) both subscribe
    to this event. ``latencies`` keys include ``capture_open_ms``,
    ``capture_ms``, ``roi_ms``, ``vsr_ms``, ``cleanup_ms``,
    ``inject_ms`` and ``total_ms`` - any stage the pipeline skipped
    (e.g. ``inject_ms`` for a withheld utterance) is ``0.0``.
    """

    utterance_id: int
    started_at_ns: int
    ended_at_ns: int
    text_raw: str
    text_final: str
    confidence: float
    used_fallback: bool
    decision: PasteDecision
    latencies: dict[str, float]
    frame_count: int
    face_present_ratio: float
    error: str | None = None


# --- Dependency injection seam --------------------------------------------


WebcamFactory = Callable[[WebcamConfig], ContextManager[Any]]
ROIFactory = Callable[[LipROIConfig], ContextManager[Any]]
VSRFactory = Callable[[VSRModelConfig], ContextManager[Any]]
CleanerFactory = Callable[[CleanupConfig], ContextManager[Any]]
HotkeyFactory = Callable[[HotkeyConfig], Any]
PasteFunc = Callable[[str, InjectConfig], InjectResult]
LatencyWriter = Callable[..., None]


@dataclass
class _Deps:
    """Injection bundle used by :class:`SilentDictatePipeline`.

    Tests build one of these with fakes; production code leaves
    ``deps=None`` and :func:`_default_deps` wires the real components.
    """

    webcam_factory: WebcamFactory
    roi_factory: ROIFactory
    vsr_factory: VSRFactory
    cleaner_factory: CleanerFactory
    hotkey_factory: HotkeyFactory
    paste_fn: PasteFunc
    latency_writer: LatencyWriter = append_latency_row
    now_ns: Callable[[], int] = time.monotonic_ns
    perf_counter: Callable[[], float] = time.perf_counter
    sleep: Callable[[float], None] = time.sleep


def _default_deps() -> _Deps:
    """Build a :class:`_Deps` wired to the real hardware-backed components."""

    def _vsr_ctx(cfg: VSRModelConfig) -> ContextManager[VSRModel]:
        return VSRModel(cfg)

    def _cleaner_ctx(cfg: CleanupConfig) -> ContextManager[TextCleaner]:
        return TextCleaner(cfg)

    def _webcam_ctx(cfg: WebcamConfig) -> ContextManager[WebcamSource]:
        return WebcamSource(cfg)

    def _roi_ctx(cfg: LipROIConfig) -> ContextManager[LipROIDetector]:
        return LipROIDetector(cfg)

    def _hotkey_ctor(cfg: HotkeyConfig) -> HotkeyController:
        return HotkeyController(cfg)

    return _Deps(
        webcam_factory=_webcam_ctx,
        roi_factory=_roi_ctx,
        vsr_factory=_vsr_ctx,
        cleaner_factory=_cleaner_ctx,
        hotkey_factory=_hotkey_ctor,
        paste_fn=_real_paste_text,
    )


# --- Internal state -------------------------------------------------------


@dataclass
class _ActiveUtterance:
    utterance_id: int
    started_at_ns: int
    t0_perf: float
    stop_event: threading.Event
    capture_open_ms: float = 0.0
    first_frame_perf: float | None = None
    last_frame_perf: float | None = None
    roi_ms: float = 0.0
    frames: list[LipFrame] = field(default_factory=list)
    face_present: int = 0
    face_missing: int = 0
    capture_thread: threading.Thread | None = None
    webcam_cm: Any | None = None
    webcam: Any | None = None


@dataclass
class _PendingForcePaste:
    utterance_id: int
    text_final: str
    stash_ns: int
    stash_perf: float
    timer: threading.Timer
    cleaned: CleanedText
    vsr_result: VSRResult
    face_ratio: float
    frame_count: int
    started_at_ns: int
    t0_perf: float
    capture_open_ms: float
    capture_ms: float
    roi_ms: float


# --- JSONL writer ---------------------------------------------------------


class _JsonlWriter:
    """Append-only writer for ``reports/silent_dictate_<date>.jsonl``."""

    def __init__(self, directory: Path, *, enabled: bool = True) -> None:
        self._dir = directory
        self._enabled = enabled
        self._lock = threading.Lock()
        self._path: Path | None = None

    def _path_for(self, ts_ns: int) -> Path:
        dt = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
        return self._dir / f"silent_dictate_{dt.strftime('%Y%m%d')}.jsonl"

    @property
    def path(self) -> Path | None:
        return self._path

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


# --- Pipeline -------------------------------------------------------------


class SilentDictatePipeline:
    """Silent-dictation pipeline (TICKET-011) - see module docstring."""

    def __init__(
        self,
        config: SilentDictateConfig | None = None,
        *,
        deps: _Deps | None = None,
        jsonl_writer: _JsonlWriter | None = None,
    ) -> None:
        self._config = config or SilentDictateConfig()
        self._deps = deps or _default_deps()

        if self._config.device_override is not None:
            device_update = {"device": self._config.device_override}
            self._config = self._config.model_copy(
                update={"vsr": self._config.vsr.model_copy(update=device_update)}
            )
        if self._config.dry_run and not self._config.inject.dry_run:
            self._config = self._config.model_copy(
                update={"inject": self._config.inject.model_copy(update={"dry_run": True})}
            )

        self._vsr_cm: ContextManager[Any] | None = None
        self._vsr: Any | None = None
        self._cleaner_cm: ContextManager[Any] | None = None
        self._cleaner: Any | None = None
        self._roi_cm: ContextManager[Any] | None = None
        self._roi: Any | None = None
        self._primary_hk: Any | None = None
        self._force_hk: Any | None = None
        self._persistent_webcam_cm: ContextManager[Any] | None = None
        self._persistent_webcam: Any | None = None

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
    def config(self) -> SilentDictateConfig:
        return self._config

    @property
    def jsonl_path(self) -> Path | None:
        return self._jsonl.path

    # --- Subscriber API (TICKET-013 overlay hook) --------------------------

    def subscribe(self, callback: Callable[[UtteranceProcessed], None]) -> None:
        """Register a callback for every :class:`UtteranceProcessed` event."""
        with self._state_lock:
            self._subscribers.append(callback)

    def subscribe_status(
        self,
        callback: Callable[[PipelineStatusEvent], None],
        *,
        replay: bool = True,
    ) -> None:
        """Register a callback for live phase/status updates."""
        with self._state_lock:
            self._status_subscribers.append(callback)
            last = self._last_status
        if replay and last is not None:
            try:
                callback(last)
            except Exception:
                logger.exception("silent_dictate status subscriber raised")

    def _notify(self, event: UtteranceProcessed) -> None:
        with self._state_lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                logger.exception("silent_dictate subscriber raised")

    def _notify_status(self, event: PipelineStatusEvent) -> None:
        with self._state_lock:
            self._last_status = event
            subs = list(self._status_subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                logger.exception("silent_dictate status subscriber raised")

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
                pipeline="silent",
                mode=mode,
                utterance_id=utterance_id,
                hotkey_binding=self._config.hotkey.binding,
                force_paste_binding=self._config.force_paste_binding,
                ollama_ok=self._ollama_ok,
                ollama_model=self._config.cleanup.model,
                cuda_status=_cuda_status(getattr(self._vsr, "device", self._config.vsr.device)),
                message=message,
                clipboard_restore_deadline_ns=clipboard_restore_deadline_ns,
                pending_force_paste=pending_force_paste,
                created_at_ns=self._deps.now_ns(),
            )
        )

    # --- Context management -----------------------------------------------

    def __enter__(self) -> "SilentDictatePipeline":
        if self._entered:
            raise RuntimeError("SilentDictatePipeline is not re-entrant")
        self._entered = True

        self._vsr_cm = self._deps.vsr_factory(self._config.vsr)
        self._vsr = self._vsr_cm.__enter__()
        logger.info("silent_dictate: VSR model ready")

        self._cleaner_cm = self._deps.cleaner_factory(self._config.cleanup)
        self._cleaner = self._cleaner_cm.__enter__()
        try:
            if hasattr(self._cleaner, "is_available"):
                probe = bool(self._cleaner.is_available())
                self._ollama_ok = probe
                logger.info("silent_dictate: cleanup reachable=%s", probe)
        except Exception:
            self._ollama_ok = False
            logger.warning("silent_dictate: cleanup probe failed", exc_info=True)

        self._roi_cm = self._deps.roi_factory(self._config.lip_roi)
        self._roi = self._roi_cm.__enter__()

        if self._config.keep_camera_open:
            t0 = self._deps.perf_counter()
            self._persistent_webcam_cm = self._deps.webcam_factory(self._config.webcam)
            self._persistent_webcam = self._persistent_webcam_cm.__enter__()
            logger.info(
                "silent_dictate: camera opened in persistent mode (%.1f ms)",
                (self._deps.perf_counter() - t0) * 1000.0,
            )

        self._primary_hk = self._deps.hotkey_factory(self._config.hotkey)
        self._primary_hk.bus.subscribe_start(self.on_trigger_start)
        self._primary_hk.bus.subscribe_stop(self.on_trigger_stop)
        self._primary_hk.start()

        if self._config.force_paste_mode == "listener":
            force_cfg = HotkeyConfig(
                mode="push_to_talk",
                binding=self._config.force_paste_binding,
                min_hold_ms=0,
                cooldown_ms=250,
            )
            self._force_hk = self._deps.hotkey_factory(force_cfg)
            self._force_hk.bus.subscribe_start(self._handle_force_paste)
            self._force_hk.start()

        logger.info(
            "silent_dictate: pipeline ready (binding=%s, force_paste_mode=%s, dry_run=%s)",
            self._config.hotkey.binding,
            self._config.force_paste_mode,
            self._config.dry_run,
        )
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
            try:
                entry.timer.cancel()
            except Exception:
                pass

        if active is not None:
            active.stop_event.set()
            if active.capture_thread is not None:
                _safe_join(active.capture_thread, timeout=1.0)
            self._close_per_trigger_webcam(active)

        for thread in dispatch_threads:
            _safe_join(thread, timeout=2.0)

        for hk in (self._primary_hk, self._force_hk):
            if hk is not None:
                try:
                    hk.stop()
                except Exception:
                    logger.exception("silent_dictate: hotkey.stop failed")
        self._primary_hk = None
        self._force_hk = None

        if self._persistent_webcam_cm is not None:
            try:
                self._persistent_webcam_cm.__exit__(None, None, None)
            except Exception:
                logger.exception("silent_dictate: persistent webcam close failed")
            self._persistent_webcam_cm = None
            self._persistent_webcam = None

        for cm_attr in ("_roi_cm", "_cleaner_cm", "_vsr_cm"):
            cm = getattr(self, cm_attr, None)
            if cm is not None:
                try:
                    cm.__exit__(None, None, None)
                except Exception:
                    logger.exception("silent_dictate: %s close failed", cm_attr)
                setattr(self, cm_attr, None)
        self._roi = None
        self._cleaner = None
        self._vsr = None

        self._entered = False

    # --- Trigger handlers -------------------------------------------------

    def on_trigger_start(self, event: TriggerEvent) -> None:
        """Bus callback: allocate a new utterance + open camera per trigger."""
        with self._state_lock:
            if self._active is not None:
                logger.warning(
                    "silent_dictate: trigger start while already active (id=%s); dropping old",
                    self._active.utterance_id,
                )
                self._active.stop_event.set()
            self._utterance_counter += 1
            utterance_id = self._utterance_counter
            active = _ActiveUtterance(
                utterance_id=utterance_id,
                started_at_ns=event.started_at_ns,
                t0_perf=self._deps.perf_counter(),
                stop_event=threading.Event(),
            )
            self._active = active

        self._jsonl.write(
            {
                "event_type": "trigger_start",
                "utterance_id": utterance_id,
                "ts_ns": event.started_at_ns,
                "trigger_id": event.trigger_id,
                "mode": event.mode,
                "reason": event.reason,
            }
        )
        self._emit_status("recording", utterance_id=utterance_id)

        try:
            if self._config.keep_camera_open and self._persistent_webcam is not None:
                active.webcam = self._persistent_webcam
                active.capture_open_ms = 0.0
            else:
                t_open = self._deps.perf_counter()
                cm = self._deps.webcam_factory(self._config.webcam)
                active.webcam_cm = cm
                active.webcam = cm.__enter__()
                active.capture_open_ms = (self._deps.perf_counter() - t_open) * 1000.0
        except Exception as exc:
            logger.exception("silent_dictate: failed to open webcam")
            with self._state_lock:
                self._active = None
            self._emit_error(utterance_id, event.started_at_ns, f"webcam_open_failed: {exc}")
            return

        thread = threading.Thread(
            target=self._capture_loop,
            args=(active,),
            name=f"sabi-capture-{utterance_id}",
            daemon=True,
        )
        active.capture_thread = thread
        thread.start()

    def on_trigger_stop(self, event: TriggerEvent) -> None:
        """Bus callback: stop capture and dispatch VSR -> cleanup -> paste."""
        with self._state_lock:
            active = self._active
            self._active = None
        if active is None:
            return

        active.stop_event.set()
        if active.capture_thread is not None:
            active.capture_thread.join(timeout=2.0)

        self._close_per_trigger_webcam(active)

        self._jsonl.write(
            {
                "event_type": "trigger_stop",
                "utterance_id": active.utterance_id,
                "ts_ns": event.started_at_ns if event is not None else time.time_ns(),
                "trigger_id": event.trigger_id,
                "frame_count": len(active.frames),
                "face_present": active.face_present,
                "face_missing": active.face_missing,
            }
        )
        self._emit_status("decoding", utterance_id=active.utterance_id)

        thread = threading.Thread(
            target=self._dispatch_utterance,
            args=(active,),
            name=f"sabi-dispatch-{active.utterance_id}",
            daemon=True,
        )
        with self._state_lock:
            self._dispatch_threads = [t for t in self._dispatch_threads if t.is_alive()]
            self._dispatch_threads.append(thread)
        thread.start()

    # --- Capture worker ----------------------------------------------------

    def _capture_loop(self, active: _ActiveUtterance) -> None:
        """Pull frames from the webcam, run ROI, append to buffer."""
        webcam = active.webcam
        roi = self._roi
        assert roi is not None
        last_ts_ns = -1
        while not active.stop_event.is_set():
            try:
                ts_ns, frame_rgb = webcam.get_latest(timeout=0.1)
            except Exception:
                if active.stop_event.is_set():
                    break
                continue
            if ts_ns == last_ts_ns:
                time.sleep(0.005)
                continue
            last_ts_ns = ts_ns
            now_perf = self._deps.perf_counter()
            if active.first_frame_perf is None:
                active.first_frame_perf = now_perf
            active.last_frame_perf = now_perf

            roi_t0 = self._deps.perf_counter()
            try:
                lip = roi.process_frame(ts_ns, frame_rgb)
            except Exception:
                logger.exception("silent_dictate: ROI detection raised; treating as missing face")
                lip = None
            active.roi_ms += (self._deps.perf_counter() - roi_t0) * 1000.0
            if lip is not None:
                active.frames.append(lip)
                active.face_present += 1
            else:
                active.face_missing += 1

    def _close_per_trigger_webcam(self, active: _ActiveUtterance) -> None:
        if active.webcam_cm is None:
            return
        try:
            active.webcam_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("silent_dictate: per-trigger webcam close failed")
        active.webcam_cm = None
        active.webcam = None

    # --- Dispatch (gates + VSR + cleanup + paste) --------------------------

    def _dispatch_utterance(self, active: _ActiveUtterance) -> None:
        try:
            self._dispatch_utterance_inner(active)
        except Exception as exc:
            logger.exception("silent_dictate: dispatch crashed")
            self._emit_error(active.utterance_id, active.started_at_ns, f"dispatch_crash: {exc}")

    def _dispatch_utterance_inner(self, active: _ActiveUtterance) -> None:
        frame_count = len(active.frames)
        total_frames = active.face_present + active.face_missing
        face_ratio = (active.face_present / total_frames) if total_frames else 0.0
        capture_ms = 0.0
        if active.first_frame_perf is not None and active.last_frame_perf is not None:
            capture_ms = (active.last_frame_perf - active.first_frame_perf) * 1000.0

        # Gate 1: empty capture.
        if frame_count == 0:
            self._emit_final(
                active=active,
                decision="withheld_empty",
                text_raw="",
                text_final="",
                confidence=0.0,
                used_fallback=False,
                vsr_ms=0.0,
                cleanup_ms=0.0,
                inject_ms=0.0,
                capture_ms=capture_ms,
                frame_count=frame_count,
                face_ratio=face_ratio,
                error=None,
            )
            return

        # Gate 2: occlusion.
        if face_ratio < self._config.occlusion_threshold:
            logger.error(
                "silent_dictate: camera could not see your mouth; nothing pasted "
                "(face_ratio=%.2f < %.2f)",
                face_ratio,
                self._config.occlusion_threshold,
            )
            self._emit_final(
                active=active,
                decision="withheld_occluded",
                text_raw="",
                text_final="",
                confidence=0.0,
                used_fallback=False,
                vsr_ms=0.0,
                cleanup_ms=0.0,
                inject_ms=0.0,
                capture_ms=capture_ms,
                frame_count=frame_count,
                face_ratio=face_ratio,
                error="camera could not see your mouth",
            )
            return

        # VSR inference.
        assert self._vsr is not None
        self._emit_status("decoding", utterance_id=active.utterance_id)
        vsr_t0 = self._deps.perf_counter()
        try:
            vsr_result: VSRResult = self._vsr.predict(active.frames)
        except Exception as exc:
            logger.exception("silent_dictate: VSR predict failed")
            self._emit_final(
                active=active,
                decision="error",
                text_raw="",
                text_final="",
                confidence=0.0,
                used_fallback=False,
                vsr_ms=(self._deps.perf_counter() - vsr_t0) * 1000.0,
                cleanup_ms=0.0,
                inject_ms=0.0,
                capture_ms=capture_ms,
                frame_count=frame_count,
                face_ratio=face_ratio,
                error=f"vsr_error: {exc}",
            )
            return
        vsr_ms = getattr(vsr_result, "latency_ms", None)
        if vsr_ms is None:
            vsr_ms = (self._deps.perf_counter() - vsr_t0) * 1000.0

        # Cleanup.
        assert self._cleaner is not None
        self._emit_status("cleaning", utterance_id=active.utterance_id)
        cleanup_ctx = CleanupContext(source="vsr", register_hint="dictation")
        cleanup_t0 = self._deps.perf_counter()
        try:
            cleaned: CleanedText = self._cleaner.cleanup(vsr_result.text, cleanup_ctx)
        except Exception as exc:
            logger.warning("silent_dictate: cleanup raised; using raw VSR text", exc_info=True)
            cleaned = CleanedText(
                text=vsr_result.text,
                latency_ms=(self._deps.perf_counter() - cleanup_t0) * 1000.0,
                used_fallback=True,
                reason=f"cleanup_exception: {exc}",
            )

        decision = self._route_decision(vsr_result.confidence)
        if decision == "withheld_low_confidence":
            self._schedule_force_paste(
                active=active,
                cleaned=cleaned,
                vsr_result=vsr_result,
                face_ratio=face_ratio,
                frame_count=frame_count,
                capture_ms=capture_ms,
            )
            return

        # Paste (or dry-run).
        self._emit_status("pasting", utterance_id=active.utterance_id)
        inject_ms, inject_decision, inject_error, restore_deadline = self._perform_paste(
            cleaned.text, base_decision=decision
        )
        if restore_deadline is not None:
            self._emit_status(
                "pasting",
                utterance_id=active.utterance_id,
                clipboard_restore_deadline_ns=restore_deadline,
            )

        self._emit_final(
            active=active,
            decision=inject_decision,
            text_raw=vsr_result.text,
            text_final=cleaned.text,
            confidence=float(vsr_result.confidence),
            used_fallback=cleaned.used_fallback,
            vsr_ms=float(vsr_ms),
            cleanup_ms=float(cleaned.latency_ms),
            inject_ms=inject_ms,
            capture_ms=capture_ms,
            frame_count=frame_count,
            face_ratio=face_ratio,
            error=inject_error,
        )

    def _route_decision(self, confidence: float) -> PasteDecision:
        """Return the initial paste decision based on confidence + mode."""
        if self._config.force_paste_mode == "always":
            return "pasted"
        if confidence >= self._config.confidence_floor:
            return "pasted"
        if self._config.force_paste_mode == "never":
            return "withheld_low_confidence"
        return "withheld_low_confidence"

    def _perform_paste(
        self,
        text: str,
        *,
        base_decision: PasteDecision,
    ) -> tuple[float, PasteDecision, str | None, int | None]:
        """Run paste/dry-run and return latency, decision, error, restore deadline."""
        if self._config.dry_run:
            print(text)
            return 0.0, "dry_run", None, None
        try:
            cfg = self._config.inject
            result = self._deps.paste_fn(text, cfg)
        except Exception as exc:
            logger.exception("silent_dictate: paste failed")
            return 0.0, "error", f"paste_error: {exc}", None
        restore_deadline_ns = None
        if getattr(result, "error", None) is None:
            restore_deadline_ns = self._deps.now_ns() + (cfg.restore_delay_ms * 1_000_000)
        return (
            float(getattr(result, "latency_ms", 0.0)),
            base_decision,
            getattr(result, "error", None),
            restore_deadline_ns,
        )

    # --- Force-paste listener --------------------------------------------

    def _schedule_force_paste(
        self,
        *,
        active: _ActiveUtterance,
        cleaned: CleanedText,
        vsr_result: VSRResult,
        face_ratio: float,
        frame_count: int,
        capture_ms: float,
    ) -> None:
        """Stash a pending paste and start the ``force_paste_window_ms`` timer."""
        stash_ns = self._deps.now_ns()
        stash_perf = self._deps.perf_counter()

        def _on_expiry() -> None:
            with self._state_lock:
                entry = self._pending.pop(active.utterance_id, None)
            if entry is None:
                return
            self._emit_final(
                active=active,
                decision="withheld_low_confidence",
                text_raw=vsr_result.text,
                text_final=cleaned.text,
                confidence=float(vsr_result.confidence),
                used_fallback=cleaned.used_fallback,
                vsr_ms=float(vsr_result.latency_ms),
                cleanup_ms=float(cleaned.latency_ms),
                inject_ms=0.0,
                capture_ms=entry.capture_ms,
                frame_count=entry.frame_count,
                face_ratio=entry.face_ratio,
                error=None,
            )

        timer = threading.Timer(self._config.force_paste_window_ms / 1000.0, _on_expiry)
        timer.daemon = True
        entry = _PendingForcePaste(
            utterance_id=active.utterance_id,
            text_final=cleaned.text,
            stash_ns=stash_ns,
            stash_perf=stash_perf,
            timer=timer,
            cleaned=cleaned,
            vsr_result=vsr_result,
            face_ratio=face_ratio,
            frame_count=frame_count,
            started_at_ns=active.started_at_ns,
            t0_perf=active.t0_perf,
            capture_open_ms=active.capture_open_ms,
            capture_ms=capture_ms,
            roi_ms=active.roi_ms,
        )
        with self._state_lock:
            self._pending[active.utterance_id] = entry
        timer.start()
        self._emit_status(
            "idle",
            utterance_id=active.utterance_id,
            message=f"{self._config.force_paste_binding.upper()} to paste anyway",
            pending_force_paste=True,
        )
        logger.info(
            "silent_dictate: utterance %s withheld (confidence=%.2f); "
            "press %s within %d ms to paste",
            active.utterance_id,
            vsr_result.confidence,
            self._config.force_paste_binding,
            self._config.force_paste_window_ms,
        )

    def _handle_force_paste(self, event: TriggerEvent) -> None:
        """Force-paste hotkey callback: paste the most-recent pending utterance."""
        if self._config.force_paste_mode != "listener":
            return
        with self._state_lock:
            if not self._pending:
                logger.info("silent_dictate: force-paste pressed with no pending utterance")
                return
            utterance_id = max(self._pending.keys())
            entry = self._pending.pop(utterance_id)
        entry.timer.cancel()

        self._jsonl.write(
            {
                "event_type": "force_paste_hit",
                "utterance_id": entry.utterance_id,
                "ts_ns": event.started_at_ns,
                "trigger_id": event.trigger_id,
                "text_final": entry.text_final,
            }
        )

        self._emit_status("pasting", utterance_id=entry.utterance_id)
        inject_ms, decision, error, restore_deadline = self._perform_paste(
            entry.text_final, base_decision="force_pasted"
        )
        if restore_deadline is not None:
            self._emit_status(
                "pasting",
                utterance_id=entry.utterance_id,
                clipboard_restore_deadline_ns=restore_deadline,
            )

        ended_at_ns = self._deps.now_ns()
        total_ms = (self._deps.perf_counter() - entry.t0_perf) * 1000.0
        latencies = {
            "capture_open_ms": entry.capture_open_ms,
            "capture_ms": entry.capture_ms,
            "roi_ms": entry.roi_ms,
            "vsr_ms": float(entry.vsr_result.latency_ms),
            "cleanup_ms": float(entry.cleaned.latency_ms),
            "inject_ms": inject_ms,
            "total_ms": total_ms,
        }
        processed = UtteranceProcessed(
            utterance_id=entry.utterance_id,
            started_at_ns=entry.started_at_ns,
            ended_at_ns=ended_at_ns,
            text_raw=entry.vsr_result.text,
            text_final=entry.text_final,
            confidence=float(entry.vsr_result.confidence),
            used_fallback=entry.cleaned.used_fallback,
            decision=decision,
            latencies=latencies,
            frame_count=entry.frame_count,
            face_present_ratio=entry.face_ratio,
            error=error,
        )
        self._finalize(processed)

    # --- Emission helpers -------------------------------------------------

    def _emit_final(
        self,
        *,
        active: _ActiveUtterance,
        decision: PasteDecision,
        text_raw: str,
        text_final: str,
        confidence: float,
        used_fallback: bool,
        vsr_ms: float,
        cleanup_ms: float,
        inject_ms: float,
        capture_ms: float,
        frame_count: int,
        face_ratio: float,
        error: str | None,
    ) -> None:
        ended_at_ns = self._deps.now_ns()
        total_ms = (self._deps.perf_counter() - active.t0_perf) * 1000.0
        latencies = {
            "capture_open_ms": active.capture_open_ms,
            "capture_ms": capture_ms,
            "roi_ms": active.roi_ms,
            "vsr_ms": float(vsr_ms),
            "cleanup_ms": float(cleanup_ms),
            "inject_ms": float(inject_ms),
            "total_ms": total_ms,
        }
        processed = UtteranceProcessed(
            utterance_id=active.utterance_id,
            started_at_ns=active.started_at_ns,
            ended_at_ns=ended_at_ns,
            text_raw=text_raw,
            text_final=text_final,
            confidence=confidence,
            used_fallback=used_fallback,
            decision=decision,
            latencies=latencies,
            frame_count=frame_count,
            face_present_ratio=face_ratio,
            error=error,
        )
        self._finalize(processed)

    def _emit_error(self, utterance_id: int, started_at_ns: int, reason: str) -> None:
        """Emit a pipeline_error JSONL line + an ``error`` UtteranceProcessed event."""
        self._jsonl.write(
            {
                "event_type": "pipeline_error",
                "utterance_id": utterance_id,
                "ts_ns": self._deps.now_ns(),
                "reason": reason,
            }
        )
        processed = UtteranceProcessed(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            ended_at_ns=self._deps.now_ns(),
            text_raw="",
            text_final="",
            confidence=0.0,
            used_fallback=False,
            decision="error",
            latencies={
                "capture_open_ms": 0.0,
                "capture_ms": 0.0,
                "roi_ms": 0.0,
                "vsr_ms": 0.0,
                "cleanup_ms": 0.0,
                "inject_ms": 0.0,
                "total_ms": 0.0,
            },
            frame_count=0,
            face_present_ratio=0.0,
            error=reason,
        )
        self._finalize(processed)

    def _finalize(self, processed: UtteranceProcessed) -> None:
        """Write JSONL + latency-log row, then notify subscribers."""
        self._jsonl.write(
            {
                "event_type": "utterance_processed",
                "utterance_id": processed.utterance_id,
                "ts_ns": processed.ended_at_ns,
                "started_at_ns": processed.started_at_ns,
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
                "frame_count": processed.frame_count,
                "face_present_ratio": processed.face_present_ratio,
                "error": processed.error,
            }
        )

        device = getattr(self._vsr, "device", None) or "unknown"
        lat = processed.latencies
        breakdown = (
            f"open={lat['capture_open_ms']:.0f} "
            f"cap={lat['capture_ms']:.0f} "
            f"roi={lat['roi_ms']:.0f} "
            f"vsr={lat['vsr_ms']:.0f} "
            f"clean={lat['cleanup_ms']:.0f} "
            f"inject={lat['inject_ms']:.0f}"
        )
        notes = (
            f"decision={processed.decision} frames={processed.frame_count} "
            f"face_ratio={processed.face_present_ratio:.2f} "
            f"confidence={processed.confidence:.2f} device={device} "
            f"prompt={self._config.cleanup.prompt_version} "
            f"fallback={processed.used_fallback} [{breakdown}]"
        )
        if processed.error:
            notes += f" error={processed.error}"
        try:
            self._deps.latency_writer(
                "TICKET-011",
                self._config.hardware_label,
                "pipeline",
                processed.latencies["total_ms"],
                1,
                notes,
            )
        except Exception:
            logger.exception("silent_dictate: failed to append latency row")

        self._notify(processed)
        self._emit_status("idle", utterance_id=processed.utterance_id)


# --- Helpers --------------------------------------------------------------


def _safe_join(thread: threading.Thread, *, timeout: float) -> None:
    """Join a thread while tolerating shutdown before ``thread.start()`` wins."""

    try:
        thread.join(timeout=timeout)
    except RuntimeError:
        logger.debug(
            "silent_dictate: skipped join for thread %r (not yet started)",
            thread.name,
        )


# --- Config loader --------------------------------------------------------


def _update_from_section(
    model: BaseModel,
    section: dict[str, Any] | None,
) -> BaseModel:
    if not section:
        return model
    overrides = {k: v for k, v in section.items() if k in model.__class__.model_fields}
    if not overrides:
        return model
    return model.model_copy(update=overrides)


def load_silent_dictate_config(path: Path | None = None) -> SilentDictateConfig:
    """Load :class:`SilentDictateConfig` from TOML (or defaults).

    Accepts a file that omits any/all of the ``[webcam]``, ``[lip_roi]``,
    ``[vsr]``, ``[cleanup]``, ``[inject]``, ``[hotkey]``, ``[pipeline]``
    sections. Every present field overlays the corresponding nested
    model via :meth:`pydantic.BaseModel.model_copy`.
    """
    target = path if path is not None else DEFAULT_CONFIG_PATH
    cfg = SilentDictateConfig()
    if not target.is_file():
        return cfg
    with target.open("rb") as f:
        data = tomllib.load(f)

    cfg = cfg.model_copy(
        update={
            "webcam": _update_from_section(cfg.webcam, data.get("webcam")),
            "lip_roi": _update_from_section(cfg.lip_roi, data.get("lip_roi")),
            "vsr": _update_from_section(cfg.vsr, data.get("vsr")),
            "cleanup": _update_from_section(cfg.cleanup, data.get("cleanup")),
            "inject": _update_from_section(cfg.inject, data.get("inject")),
            "hotkey": _update_from_section(cfg.hotkey, data.get("hotkey")),
        }
    )
    pipeline = data.get("pipeline") or {}
    pipeline_overrides = {
        k: v for k, v in pipeline.items() if k in SilentDictateConfig.model_fields
    }
    if pipeline_overrides:
        if "jsonl_dir" in pipeline_overrides and isinstance(pipeline_overrides["jsonl_dir"], str):
            pipeline_overrides["jsonl_dir"] = Path(pipeline_overrides["jsonl_dir"])
        cfg = cfg.model_copy(update=pipeline_overrides)
    return cfg


# --- CLI entry point ------------------------------------------------------


def run_silent_dictate(
    config: SilentDictateConfig | None = None,
    *,
    deps: _Deps | None = None,
    stop_event: threading.Event | None = None,
    ui: UiMode = "tui",
) -> int:
    """Run the pipeline until ``stop_event`` is set or Ctrl+C arrives."""
    cfg = config or SilentDictateConfig()
    stop = stop_event if stop_event is not None else threading.Event()
    ui_mode = normalize_ui_mode(ui)

    print(
        (
            "sabi silent-dictate: binding={binding}  "
            "force_paste={fmode}({fbind})  dry_run={dry}"
        ).format(
            binding=cfg.hotkey.binding,
            fmode=cfg.force_paste_mode,
            fbind=cfg.force_paste_binding,
            dry=cfg.dry_run,
        )
    )
    print("Hold the hotkey to dictate. Ctrl+C to exit.")

    status_tui = None
    if ui_mode == "tui":
        from sabi.ui.status_tui import StatusTUI

        status_tui = StatusTUI()
        status_tui.handle_status(_initial_silent_status(cfg))
        status_tui.start()

    pipeline = SilentDictatePipeline(cfg, deps=deps)
    if status_tui is not None:
        pipeline.subscribe_status(status_tui.handle_status)
        pipeline.subscribe(status_tui.handle_utterance)
    else:
        pipeline.subscribe(_print_silent_event)

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


def _initial_silent_status(cfg: SilentDictateConfig) -> PipelineStatusEvent:
    return PipelineStatusEvent(
        pipeline="silent",
        mode="idle",
        hotkey_binding=cfg.hotkey.binding,
        force_paste_binding=cfg.force_paste_binding,
        ollama_ok=None,
        ollama_model=cfg.cleanup.model,
        cuda_status=_cuda_status(cfg.vsr.device),
        created_at_ns=time.monotonic_ns(),
    )


def _print_silent_event(ev: UtteranceProcessed) -> None:
    line = (
        f"[{ev.decision.upper()}] id={ev.utterance_id} "
        f"text={ev.text_final!r} conf={ev.confidence:.2f} "
        f"frames={ev.frame_count} total_ms={ev.latencies['total_ms']:.0f}"
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
    "PasteDecision",
    "SilentDictateConfig",
    "SilentDictatePipeline",
    "UtteranceProcessed",
    "load_silent_dictate_config",
    "run_silent_dictate",
]
