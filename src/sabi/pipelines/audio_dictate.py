"""Audio-dictation pipeline (TICKET-012).

Wires the microphone + VAD (TICKET-006), faster-whisper ASR (TICKET-007),
Ollama cleanup (TICKET-008), clipboard paste (TICKET-009), and hotkey
trigger (TICKET-010) behind :class:`AudioDictatePipeline` and the
``python -m sabi dictate`` CLI.

Design notes:

* Structurally parallel to :mod:`sabi.pipelines.silent_dictate` so
  TICKET-014 can merge the two JSONL streams. The ``pipeline`` field on
  :class:`UtteranceProcessed` tags every event as ``"audio"``.
* Two trigger modes, selectable at config time:
    - ``push_to_talk`` uses
      :meth:`sabi.capture.microphone.MicrophoneSource.push_to_talk_segment`
      between two ``threading.Event`` edges wired to the hotkey.
    - ``vad`` uses toggle-mode hotkey activation + a consumer thread
      that pulls segmented :class:`~sabi.capture.microphone.Utterance`
      objects out of the mic's VAD queue.
* The mic is preopened on ``__enter__`` (default). Pass
  ``ptt_open_per_trigger=True`` for the privacy-oriented PTT path that
  re-opens the mic per trigger.
* Force-paste is mode-dependent: ``force_paste_mode_ptt`` (default
  ``listener``) hides low-confidence utterances behind a 1.5 s F12
  window; ``force_paste_mode_vad`` (default ``always``) just pastes
  because the VAD stream cannot reliably pause.
* Every hardware component is swappable via the ``deps=`` seam so the
  full pipeline can be unit-tested without a microphone, CUDA, Ollama
  daemon, clipboard, or real keyboard hook.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ContextManager, Literal

from pydantic import BaseModel, Field, model_validator

from sabi.capture.microphone import MicConfig, MicrophoneSource, Utterance
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
from sabi.models.asr import ASRModel, ASRModelConfig, ASRResult
from sabi.models.latency import append_latency_row
from sabi.output.inject import InjectConfig, InjectResult
from sabi.output.inject import paste_text as _real_paste_text
from sabi.pipelines.events import PipelinePhase, PipelineStatusEvent, UiMode, normalize_ui_mode
from sabi.runtime.paths import configs_dir, reports_dir

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = configs_dir() / "audio_dictate.toml"
DEFAULT_JSONL_DIR = reports_dir()

PasteDecision = Literal[
    "pasted",
    "withheld_low_confidence",
    "withheld_silence",
    "withheld_empty",
    "force_pasted",
    "dry_run",
    "error",
]
ForcePasteMode = Literal["listener", "always", "never"]
TriggerMode = Literal["push_to_talk", "vad"]
Device = Literal["auto", "cuda", "cpu"]


class AudioDictateConfig(BaseModel):
    """Top-level config for :class:`AudioDictatePipeline`.

    Composes the per-module configs plus pipeline-level knobs. Load from
    ``configs/audio_dictate.toml`` via :func:`load_audio_dictate_config`.
    """

    mic: MicConfig = Field(default_factory=MicConfig)
    asr: ASRModelConfig = Field(default_factory=ASRModelConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    inject: InjectConfig = Field(default_factory=InjectConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)

    trigger_mode: TriggerMode = "push_to_talk"
    confidence_floor: float = Field(default=0.40, ge=0.0, le=1.0)
    force_paste_binding: str = Field(default="f12")
    force_paste_window_ms: int = Field(default=1500, ge=0)
    force_paste_mode_ptt: ForcePasteMode = "listener"
    force_paste_mode_vad: ForcePasteMode = "always"
    ptt_open_per_trigger: bool = False
    vad_coverage_floor: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Discard utterances whose Utterance.vad_coverage is below this.",
    )
    dry_run: bool = False
    device_override: Device | None = Field(
        default=None,
        description="If set, overrides `asr.device` at pipeline construction time.",
    )
    jsonl_dir: Path = Field(default_factory=lambda: DEFAULT_JSONL_DIR)
    hardware_label: str = Field(
        default="windows",
        description="Hardware tag used in reports/latency-log.md rows.",
    )

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _validate_bindings_and_mode(self) -> "AudioDictateConfig":
        primary = self.hotkey.binding.strip().lower()
        force = self.force_paste_binding.strip().lower()
        if primary == force:
            raise ValueError(
                "audio_dictate: hotkey.binding and force_paste_binding must differ; "
                f"both are {primary!r}."
            )
        expected_hotkey_mode = (
            "push_to_talk" if self.trigger_mode == "push_to_talk" else "toggle"
        )
        if self.hotkey.mode != expected_hotkey_mode:
            logger.info(
                "audio_dictate: auto-coercing hotkey.mode %r -> %r to match trigger_mode=%s",
                self.hotkey.mode,
                expected_hotkey_mode,
                self.trigger_mode,
            )
            object.__setattr__(
                self,
                "hotkey",
                self.hotkey.model_copy(update={"mode": expected_hotkey_mode}),
            )
        return self


@dataclass(frozen=True)
class UtteranceProcessed:
    """Final event emitted once per utterance.

    Shares the shape with :class:`sabi.pipelines.silent_dictate.UtteranceProcessed`
    except for the audio-specific fields (``duration_ms``, ``vad_coverage``,
    ``peak_dbfs``) and the ``pipeline="audio"`` tag. TICKET-013 overlay and
    TICKET-014 eval harness both subscribe to this event.

    ``latencies`` keys:

    ``mic_open_ms``, ``warmup_ms``, ``capture_ms``, ``vad_ms``,
    ``asr_ms``, ``cleanup_ms``, ``inject_ms``, ``total_ms``. Stages the
    pipeline skipped are ``0.0``.
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
    duration_ms: float
    vad_coverage: float
    peak_dbfs: float
    trigger_mode: TriggerMode
    pipeline: Literal["audio"] = "audio"
    error: str | None = None


# --- Dependency injection seam --------------------------------------------


MicFactory = Callable[[MicConfig], ContextManager[Any]]
ASRFactory = Callable[[ASRModelConfig], ContextManager[Any]]
CleanerFactory = Callable[[CleanupConfig], ContextManager[Any]]
HotkeyFactory = Callable[[HotkeyConfig], Any]
PasteFunc = Callable[[str, InjectConfig], InjectResult]
LatencyWriter = Callable[..., None]


@dataclass
class _Deps:
    """Injection bundle used by :class:`AudioDictatePipeline`.

    Tests build one of these with fakes; production code leaves
    ``deps=None`` and :func:`_default_deps` wires the real components.
    """

    mic_factory: MicFactory
    asr_factory: ASRFactory
    cleaner_factory: CleanerFactory
    hotkey_factory: HotkeyFactory
    paste_fn: PasteFunc
    latency_writer: LatencyWriter = append_latency_row
    now_ns: Callable[[], int] = time.monotonic_ns
    perf_counter: Callable[[], float] = time.perf_counter
    sleep: Callable[[float], None] = time.sleep


def _default_deps() -> _Deps:
    """Build a :class:`_Deps` wired to the real hardware-backed components."""

    def _mic_ctx(cfg: MicConfig) -> ContextManager[MicrophoneSource]:
        return MicrophoneSource(cfg)

    def _asr_ctx(cfg: ASRModelConfig) -> ContextManager[ASRModel]:
        return ASRModel(cfg)

    def _cleaner_ctx(cfg: CleanupConfig) -> ContextManager[TextCleaner]:
        return TextCleaner(cfg)

    def _hotkey_ctor(cfg: HotkeyConfig) -> HotkeyController:
        return HotkeyController(cfg)

    return _Deps(
        mic_factory=_mic_ctx,
        asr_factory=_asr_ctx,
        cleaner_factory=_cleaner_ctx,
        hotkey_factory=_hotkey_ctor,
        paste_fn=_real_paste_text,
    )


# --- Internal state -------------------------------------------------------


@dataclass
class _ActivePTT:
    """Per-trigger bookkeeping for push-to-talk capture."""

    utterance_id: int
    started_at_ns: int
    t0_perf: float
    start_event: threading.Event
    end_event: threading.Event
    capture_thread: threading.Thread | None = None
    guard_timer: threading.Timer | None = None
    mic_open_ms: float = 0.0
    mic_cm: Any | None = None
    mic: Any | None = None
    utterance: Utterance | None = None
    capture_error: str | None = None


@dataclass
class _PendingForcePaste:
    """Low-confidence utterance queued behind the F12 listener."""

    utterance_id: int
    started_at_ns: int
    t0_perf: float
    text_final: str
    cleaned: CleanedText
    asr_result: ASRResult
    duration_ms: float
    vad_coverage: float
    peak_dbfs: float
    mic_open_ms: float
    warmup_ms: float
    capture_ms: float
    timer: threading.Timer


# --- JSONL writer ---------------------------------------------------------


class _JsonlWriter:
    """Append-only writer for ``reports/audio_dictate_<date>.jsonl``."""

    def __init__(self, directory: Path, *, enabled: bool = True) -> None:
        self._dir = directory
        self._enabled = enabled
        self._lock = threading.Lock()
        self._path: Path | None = None

    def _path_for(self, ts_ns: int) -> Path:
        dt = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc)
        return self._dir / f"audio_dictate_{dt.strftime('%Y%m%d')}.jsonl"

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


class AudioDictatePipeline:
    """Audio-dictation pipeline (TICKET-012) - see module docstring."""

    def __init__(
        self,
        config: AudioDictateConfig | None = None,
        *,
        deps: _Deps | None = None,
        jsonl_writer: _JsonlWriter | None = None,
    ) -> None:
        self._config = config or AudioDictateConfig()
        self._deps = deps or _default_deps()

        if self._config.device_override is not None:
            self._config = self._config.model_copy(
                update={
                    "asr": self._config.asr.model_copy(
                        update={"device": self._config.device_override}
                    )
                }
            )
        if self._config.dry_run and not self._config.inject.dry_run:
            self._config = self._config.model_copy(
                update={"inject": self._config.inject.model_copy(update={"dry_run": True})}
            )

        self._asr_cm: ContextManager[Any] | None = None
        self._asr: Any | None = None
        self._cleaner_cm: ContextManager[Any] | None = None
        self._cleaner: Any | None = None
        self._primary_hk: Any | None = None
        self._force_hk: Any | None = None
        self._persistent_mic_cm: ContextManager[Any] | None = None
        self._persistent_mic: Any | None = None

        self._state_lock = threading.RLock()
        self._subscribers: list[Callable[[UtteranceProcessed], None]] = []
        self._status_subscribers: list[Callable[[PipelineStatusEvent], None]] = []
        self._last_status: PipelineStatusEvent | None = None
        self._utterance_counter = 0
        self._active_ptt: _ActivePTT | None = None
        self._pending: dict[int, _PendingForcePaste] = {}
        self._dispatch_threads: list[threading.Thread] = []

        self._vad_active = threading.Event()
        self._vad_shutdown = threading.Event()
        self._vad_consumer: threading.Thread | None = None

        self._warmup_ms: float = 0.0
        self._mic_open_ms: float = 0.0
        self._mic_open_reported = False
        self._ollama_ok: bool | None = None

        self._jsonl = jsonl_writer or _JsonlWriter(self._config.jsonl_dir)
        self._entered = False
        self._closed = False

    @property
    def config(self) -> AudioDictateConfig:
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
                logger.exception("audio_dictate status subscriber raised")

    def _notify(self, event: UtteranceProcessed) -> None:
        with self._state_lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                logger.exception("audio_dictate subscriber raised")

    def _notify_status(self, event: PipelineStatusEvent) -> None:
        with self._state_lock:
            self._last_status = event
            subs = list(self._status_subscribers)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                logger.exception("audio_dictate status subscriber raised")

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
                pipeline="audio",
                mode=mode,
                utterance_id=utterance_id,
                hotkey_binding=self._config.hotkey.binding,
                force_paste_binding=self._config.force_paste_binding,
                ollama_ok=self._ollama_ok,
                ollama_model=self._config.cleanup.model,
                cuda_status=_cuda_status(getattr(self._asr, "device", self._config.asr.device)),
                message=message,
                clipboard_restore_deadline_ns=clipboard_restore_deadline_ns,
                pending_force_paste=pending_force_paste,
                created_at_ns=self._deps.now_ns(),
            )
        )

    # --- Active force-paste policy helpers --------------------------------

    @property
    def _active_force_paste_mode(self) -> ForcePasteMode:
        return (
            self._config.force_paste_mode_ptt
            if self._config.trigger_mode == "push_to_talk"
            else self._config.force_paste_mode_vad
        )

    # --- Context management -----------------------------------------------

    def __enter__(self) -> "AudioDictatePipeline":
        if self._entered:
            raise RuntimeError("AudioDictatePipeline is not re-entrant")
        self._entered = True

        self._asr_cm = self._deps.asr_factory(self._config.asr)
        self._asr = self._asr_cm.__enter__()
        try:
            result = self._asr.warm_up()
            self._warmup_ms = float(getattr(result, "latency_ms", 0.0))
            logger.info("audio_dictate: ASR warm-up complete (%.1f ms)", self._warmup_ms)
        except Exception:
            logger.warning("audio_dictate: ASR warm-up failed", exc_info=True)

        self._cleaner_cm = self._deps.cleaner_factory(self._config.cleanup)
        self._cleaner = self._cleaner_cm.__enter__()
        try:
            if hasattr(self._cleaner, "is_available"):
                probe = bool(self._cleaner.is_available())
                self._ollama_ok = probe
                logger.info("audio_dictate: cleanup reachable=%s", probe)
        except Exception:
            self._ollama_ok = False
            logger.warning("audio_dictate: cleanup probe failed", exc_info=True)

        if self._should_preopen_mic():
            t0 = self._deps.perf_counter()
            self._persistent_mic_cm = self._deps.mic_factory(self._config.mic)
            self._persistent_mic = self._persistent_mic_cm.__enter__()
            self._mic_open_ms = (self._deps.perf_counter() - t0) * 1000.0
            logger.info(
                "audio_dictate: microphone opened (%.1f ms, preopen)", self._mic_open_ms
            )

        if self._config.trigger_mode == "vad":
            self._vad_consumer = threading.Thread(
                target=self._vad_consumer_loop,
                name="sabi-audio-vad-consumer",
                daemon=True,
            )
            self._vad_consumer.start()

        self._primary_hk = self._deps.hotkey_factory(self._config.hotkey)
        self._primary_hk.bus.subscribe_start(self.on_trigger_start)
        self._primary_hk.bus.subscribe_stop(self.on_trigger_stop)
        self._primary_hk.start()

        if self._active_force_paste_mode == "listener":
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
            "audio_dictate: pipeline ready (mode=%s, binding=%s, "
            "force_paste=%s, dry_run=%s)",
            self._config.trigger_mode,
            self._config.hotkey.binding,
            self._active_force_paste_mode,
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

        self._vad_active.clear()
        self._vad_shutdown.set()

        with self._state_lock:
            active = self._active_ptt
            self._active_ptt = None
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
            active.end_event.set()
            if active.guard_timer is not None:
                active.guard_timer.cancel()
            if active.capture_thread is not None:
                _safe_join(active.capture_thread, timeout=1.0)
            self._close_per_trigger_mic(active)

        if self._vad_consumer is not None:
            _safe_join(self._vad_consumer, timeout=2.0)
            self._vad_consumer = None

        for thread in dispatch_threads:
            _safe_join(thread, timeout=2.0)

        for hk in (self._primary_hk, self._force_hk):
            if hk is not None:
                try:
                    hk.stop()
                except Exception:
                    logger.exception("audio_dictate: hotkey.stop failed")
        self._primary_hk = None
        self._force_hk = None

        if self._persistent_mic_cm is not None:
            try:
                self._persistent_mic_cm.__exit__(None, None, None)
            except Exception:
                logger.exception("audio_dictate: persistent mic close failed")
            self._persistent_mic_cm = None
            self._persistent_mic = None

        for cm_attr in ("_cleaner_cm", "_asr_cm"):
            cm = getattr(self, cm_attr, None)
            if cm is not None:
                try:
                    cm.__exit__(None, None, None)
                except Exception:
                    logger.exception("audio_dictate: %s close failed", cm_attr)
                setattr(self, cm_attr, None)
        self._cleaner = None
        self._asr = None

        self._entered = False

    # --- Mic lifecycle helpers --------------------------------------------

    def _should_preopen_mic(self) -> bool:
        """Preopen whenever VAD is on, or PTT without per-trigger open."""
        if self._config.trigger_mode == "vad":
            return True
        return not self._config.ptt_open_per_trigger

    def _close_per_trigger_mic(self, active: _ActivePTT) -> None:
        if active.mic_cm is None:
            return
        try:
            active.mic_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("audio_dictate: per-trigger mic close failed")
        active.mic_cm = None
        active.mic = None

    # --- Trigger handlers (PTT + VAD) -------------------------------------

    def on_trigger_start(self, event: TriggerEvent) -> None:
        """Dispatch to the mode-specific start handler."""
        if self._config.trigger_mode == "push_to_talk":
            self._on_ptt_start(event)
        else:
            self._on_vad_toggle_on(event)

    def on_trigger_stop(self, event: TriggerEvent) -> None:
        """Dispatch to the mode-specific stop handler."""
        if self._config.trigger_mode == "push_to_talk":
            self._on_ptt_stop(event)
        else:
            self._on_vad_toggle_off(event)

    # --- PTT flow ---------------------------------------------------------

    def _on_ptt_start(self, event: TriggerEvent) -> None:
        with self._state_lock:
            if self._active_ptt is not None:
                logger.warning(
                    "audio_dictate: PTT start while already active (id=%s); dropping old",
                    self._active_ptt.utterance_id,
                )
                self._active_ptt.end_event.set()
            self._utterance_counter += 1
            utterance_id = self._utterance_counter
            active = _ActivePTT(
                utterance_id=utterance_id,
                started_at_ns=event.started_at_ns,
                t0_perf=self._deps.perf_counter(),
                start_event=threading.Event(),
                end_event=threading.Event(),
            )
            self._active_ptt = active

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
            if self._config.ptt_open_per_trigger:
                t_open = self._deps.perf_counter()
                cm = self._deps.mic_factory(self._config.mic)
                active.mic_cm = cm
                active.mic = cm.__enter__()
                active.mic_open_ms = (self._deps.perf_counter() - t_open) * 1000.0
            else:
                active.mic = self._persistent_mic
                active.mic_open_ms = 0.0
        except Exception as exc:
            logger.exception("audio_dictate: failed to open microphone")
            with self._state_lock:
                self._active_ptt = None
            self._emit_error(
                utterance_id, event.started_at_ns, f"mic_open_failed: {exc}"
            )
            return

        thread = threading.Thread(
            target=self._ptt_capture_worker,
            args=(active,),
            name=f"sabi-audio-capture-{utterance_id}",
            daemon=True,
        )
        active.capture_thread = thread
        thread.start()

        active.start_event.set()

        max_ms = self._config.mic.max_utterance_ms
        if max_ms > 0:
            timer = threading.Timer(max_ms / 1000.0, active.end_event.set)
            timer.daemon = True
            active.guard_timer = timer
            timer.start()

    def _ptt_capture_worker(self, active: _ActivePTT) -> None:
        """Call push_to_talk_segment and stash the returned utterance."""
        mic = active.mic
        assert mic is not None
        try:
            active.utterance = mic.push_to_talk_segment(
                active.start_event, active.end_event
            )
        except Exception as exc:
            logger.exception("audio_dictate: PTT capture raised")
            active.capture_error = f"capture_error: {exc}"

    def _on_ptt_stop(self, event: TriggerEvent) -> None:
        with self._state_lock:
            active = self._active_ptt
            self._active_ptt = None
        if active is None:
            return

        active.end_event.set()
        if active.guard_timer is not None:
            active.guard_timer.cancel()
            active.guard_timer = None
        if active.capture_thread is not None:
            _safe_join(active.capture_thread, timeout=2.0)

        utt = active.utterance
        self._jsonl.write(
            {
                "event_type": "trigger_stop",
                "utterance_id": active.utterance_id,
                "ts_ns": event.started_at_ns if event is not None else time.time_ns(),
                "trigger_id": event.trigger_id,
                "duration_ms": _utterance_duration_ms(utt),
                "vad_coverage": float(utt.vad_coverage) if utt else 0.0,
                "peak_dbfs": float(utt.peak_dbfs) if utt else float("-inf"),
            }
        )
        self._emit_status("decoding", utterance_id=active.utterance_id)

        if self._config.ptt_open_per_trigger:
            self._close_per_trigger_mic(active)

        thread = threading.Thread(
            target=self._dispatch_ptt,
            args=(active,),
            name=f"sabi-audio-dispatch-{active.utterance_id}",
            daemon=True,
        )
        with self._state_lock:
            self._dispatch_threads = [t for t in self._dispatch_threads if t.is_alive()]
            self._dispatch_threads.append(thread)
        thread.start()

    def _dispatch_ptt(self, active: _ActivePTT) -> None:
        try:
            self._dispatch_ptt_inner(active)
        except Exception as exc:
            logger.exception("audio_dictate: PTT dispatch crashed")
            self._emit_error(
                active.utterance_id, active.started_at_ns, f"dispatch_crash: {exc}"
            )

    def _dispatch_ptt_inner(self, active: _ActivePTT) -> None:
        if active.capture_error:
            self._emit_error(
                active.utterance_id, active.started_at_ns, active.capture_error
            )
            return
        utt = active.utterance
        mic_open_ms, warmup_ms = self._consume_one_shot_stage_budgets(active.mic_open_ms)
        self._process_utterance(
            utterance_id=active.utterance_id,
            started_at_ns=active.started_at_ns,
            t0_perf=active.t0_perf,
            utt=utt,
            mic_open_ms=mic_open_ms,
            warmup_ms=warmup_ms,
        )

    # --- VAD flow ---------------------------------------------------------

    def _on_vad_toggle_on(self, event: TriggerEvent) -> None:
        if self._vad_active.is_set():
            return
        with self._state_lock:
            was_active = self._vad_active.is_set()
        self._vad_active.set()
        self._jsonl.write(
            {
                "event_type": "vad_activated",
                "ts_ns": event.started_at_ns,
                "trigger_id": event.trigger_id,
                "reason": event.reason,
            }
        )
        self._emit_status("recording", message="VAD active")
        if not was_active:
            logger.info("audio_dictate: VAD activated")

    def _on_vad_toggle_off(self, event: TriggerEvent) -> None:
        if not self._vad_active.is_set():
            return
        self._vad_active.clear()
        self._jsonl.write(
            {
                "event_type": "vad_deactivated",
                "ts_ns": event.started_at_ns,
                "trigger_id": event.trigger_id,
                "reason": event.reason,
            }
        )
        self._emit_status("idle", message="VAD inactive")
        logger.info("audio_dictate: VAD deactivated")

    def _vad_consumer_loop(self) -> None:
        """Pull utterances off the mic's VAD queue; dispatch while active."""
        mic = self._persistent_mic
        assert mic is not None
        while not self._vad_shutdown.is_set():
            try:
                utt = mic.next_utterance(timeout=0.1)
            except Exception:
                logger.exception("audio_dictate: mic.next_utterance raised")
                utt = None
            if utt is None:
                continue
            if not self._vad_active.is_set():
                continue  # drop stale utterance captured while deactivated
            with self._state_lock:
                self._utterance_counter += 1
                uid = self._utterance_counter
            thread = threading.Thread(
                target=self._dispatch_vad,
                args=(uid, utt),
                name=f"sabi-audio-dispatch-{uid}",
                daemon=True,
            )
            with self._state_lock:
                self._dispatch_threads = [
                    t for t in self._dispatch_threads if t.is_alive()
                ]
                self._dispatch_threads.append(thread)
            thread.start()

    def _dispatch_vad(self, utterance_id: int, utt: Utterance) -> None:
        try:
            self._dispatch_vad_inner(utterance_id, utt)
        except Exception as exc:
            logger.exception("audio_dictate: VAD dispatch crashed")
            self._emit_error(
                utterance_id, int(utt.start_ts_ns), f"dispatch_crash: {exc}"
            )

    def _dispatch_vad_inner(self, utterance_id: int, utt: Utterance) -> None:
        mic_open_ms, warmup_ms = self._consume_one_shot_stage_budgets(0.0)
        self._process_utterance(
            utterance_id=utterance_id,
            started_at_ns=int(utt.start_ts_ns),
            t0_perf=self._deps.perf_counter(),
            utt=utt,
            mic_open_ms=mic_open_ms,
            warmup_ms=warmup_ms,
        )

    # --- Shared processing chain ------------------------------------------

    def _consume_one_shot_stage_budgets(self, ptt_open_ms: float) -> tuple[float, float]:
        """Return (mic_open_ms, warmup_ms) for this utterance and zero them after.

        PTT + ``ptt_open_per_trigger=True`` reports ``mic_open_ms`` on every
        utterance; all other modes report it once.
        """
        with self._state_lock:
            if self._config.ptt_open_per_trigger:
                mic_open_ms = ptt_open_ms
            elif not self._mic_open_reported:
                mic_open_ms = self._mic_open_ms
                self._mic_open_reported = True
            else:
                mic_open_ms = 0.0
            warmup_ms = self._warmup_ms
            self._warmup_ms = 0.0
        return mic_open_ms, warmup_ms

    def _process_utterance(
        self,
        *,
        utterance_id: int,
        started_at_ns: int,
        t0_perf: float,
        utt: Utterance | None,
        mic_open_ms: float,
        warmup_ms: float,
    ) -> None:
        duration_ms = _utterance_duration_ms(utt)
        vad_coverage = float(utt.vad_coverage) if utt is not None else 0.0
        peak_dbfs = float(utt.peak_dbfs) if utt is not None else float("-inf")
        capture_ms = duration_ms

        # Gate 1: silence / empty audio (mirrors the plan's
        # `samples.size == 0 or peak_dbfs <= silence_peak_dbfs` rule).
        silence_floor = float(self._config.asr.silence_peak_dbfs)
        if utt is None or utt.samples.size == 0 or peak_dbfs <= silence_floor:
            self._emit_final(
                utterance_id=utterance_id,
                started_at_ns=started_at_ns,
                t0_perf=t0_perf,
                decision="withheld_silence",
                text_raw="",
                text_final="",
                confidence=0.0,
                used_fallback=False,
                mic_open_ms=mic_open_ms,
                warmup_ms=warmup_ms,
                capture_ms=capture_ms,
                vad_ms=0.0,
                asr_ms=0.0,
                cleanup_ms=0.0,
                inject_ms=0.0,
                duration_ms=duration_ms,
                vad_coverage=vad_coverage,
                peak_dbfs=peak_dbfs,
                error=None,
            )
            return

        # Gate 2: below VAD coverage floor (mostly silence).
        if vad_coverage < self._config.vad_coverage_floor:
            logger.info(
                "audio_dictate: utterance %s withheld (vad_coverage=%.2f < %.2f)",
                utterance_id,
                vad_coverage,
                self._config.vad_coverage_floor,
            )
            self._emit_final(
                utterance_id=utterance_id,
                started_at_ns=started_at_ns,
                t0_perf=t0_perf,
                decision="withheld_silence",
                text_raw="",
                text_final="",
                confidence=0.0,
                used_fallback=False,
                mic_open_ms=mic_open_ms,
                warmup_ms=warmup_ms,
                capture_ms=capture_ms,
                vad_ms=0.0,
                asr_ms=0.0,
                cleanup_ms=0.0,
                inject_ms=0.0,
                duration_ms=duration_ms,
                vad_coverage=vad_coverage,
                peak_dbfs=peak_dbfs,
                error=None,
            )
            return

        assert self._asr is not None
        self._emit_status("decoding", utterance_id=utterance_id)
        asr_t0 = self._deps.perf_counter()
        try:
            asr_result: ASRResult = self._asr.transcribe(utt)
        except Exception as exc:
            logger.exception("audio_dictate: ASR transcribe failed")
            self._emit_final(
                utterance_id=utterance_id,
                started_at_ns=started_at_ns,
                t0_perf=t0_perf,
                decision="error",
                text_raw="",
                text_final="",
                confidence=0.0,
                used_fallback=False,
                mic_open_ms=mic_open_ms,
                warmup_ms=warmup_ms,
                capture_ms=capture_ms,
                vad_ms=0.0,
                asr_ms=(self._deps.perf_counter() - asr_t0) * 1000.0,
                cleanup_ms=0.0,
                inject_ms=0.0,
                duration_ms=duration_ms,
                vad_coverage=vad_coverage,
                peak_dbfs=peak_dbfs,
                error=f"asr_error: {exc}",
            )
            return
        asr_ms = getattr(asr_result, "latency_ms", None)
        if asr_ms is None:
            asr_ms = (self._deps.perf_counter() - asr_t0) * 1000.0

        # Gate 3: empty transcription.
        if not asr_result.text.strip():
            self._emit_final(
                utterance_id=utterance_id,
                started_at_ns=started_at_ns,
                t0_perf=t0_perf,
                decision="withheld_empty",
                text_raw="",
                text_final="",
                confidence=float(asr_result.confidence),
                used_fallback=False,
                mic_open_ms=mic_open_ms,
                warmup_ms=warmup_ms,
                capture_ms=capture_ms,
                vad_ms=0.0,
                asr_ms=float(asr_ms),
                cleanup_ms=0.0,
                inject_ms=0.0,
                duration_ms=duration_ms,
                vad_coverage=vad_coverage,
                peak_dbfs=peak_dbfs,
                error=None,
            )
            return

        # Cleanup.
        assert self._cleaner is not None
        self._emit_status("cleaning", utterance_id=utterance_id)
        cleanup_ctx = CleanupContext(source="asr", register_hint="dictation")
        cleanup_t0 = self._deps.perf_counter()
        try:
            cleaned: CleanedText = self._cleaner.cleanup(asr_result.text, cleanup_ctx)
        except Exception as exc:
            logger.warning("audio_dictate: cleanup raised; using raw ASR text", exc_info=True)
            cleaned = CleanedText(
                text=asr_result.text,
                latency_ms=(self._deps.perf_counter() - cleanup_t0) * 1000.0,
                used_fallback=True,
                reason=f"cleanup_exception: {exc}",
            )

        decision = self._route_decision(asr_result.confidence)
        if decision == "withheld_low_confidence":
            self._schedule_force_paste(
                utterance_id=utterance_id,
                started_at_ns=started_at_ns,
                t0_perf=t0_perf,
                cleaned=cleaned,
                asr_result=asr_result,
                duration_ms=duration_ms,
                vad_coverage=vad_coverage,
                peak_dbfs=peak_dbfs,
                mic_open_ms=mic_open_ms,
                warmup_ms=warmup_ms,
                capture_ms=capture_ms,
            )
            return

        self._emit_status("pasting", utterance_id=utterance_id)
        inject_ms, inject_decision, inject_error, restore_deadline = self._perform_paste(
            cleaned.text, base_decision=decision
        )
        if restore_deadline is not None:
            self._emit_status(
                "pasting",
                utterance_id=utterance_id,
                clipboard_restore_deadline_ns=restore_deadline,
            )
        self._emit_final(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            t0_perf=t0_perf,
            decision=inject_decision,
            text_raw=asr_result.text,
            text_final=cleaned.text,
            confidence=float(asr_result.confidence),
            used_fallback=cleaned.used_fallback,
            mic_open_ms=mic_open_ms,
            warmup_ms=warmup_ms,
            capture_ms=capture_ms,
            vad_ms=0.0,
            asr_ms=float(asr_ms),
            cleanup_ms=float(cleaned.latency_ms),
            inject_ms=inject_ms,
            duration_ms=duration_ms,
            vad_coverage=vad_coverage,
            peak_dbfs=peak_dbfs,
            error=inject_error,
        )

    def _route_decision(self, confidence: float) -> PasteDecision:
        """Return the initial paste decision based on confidence + active mode."""
        mode = self._active_force_paste_mode
        if mode == "always":
            return "pasted"
        if confidence >= self._config.confidence_floor:
            return "pasted"
        return "withheld_low_confidence"

    def _perform_paste(
        self,
        text: str,
        *,
        base_decision: PasteDecision,
    ) -> tuple[float, PasteDecision, str | None, int | None]:
        """Run paste/dry-run and return latency, decision, error, restore deadline."""
        if self._config.dry_run:
            logger.info("audio_dictate dry-run transcript: %s", text)
            return 0.0, "dry_run", None, None
        try:
            cfg = self._config.inject
            result = self._deps.paste_fn(text, cfg)
        except Exception as exc:
            logger.exception("audio_dictate: paste failed")
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
        utterance_id: int,
        started_at_ns: int,
        t0_perf: float,
        cleaned: CleanedText,
        asr_result: ASRResult,
        duration_ms: float,
        vad_coverage: float,
        peak_dbfs: float,
        mic_open_ms: float,
        warmup_ms: float,
        capture_ms: float,
    ) -> None:
        """Stash a pending paste and start the ``force_paste_window_ms`` timer."""

        def _on_expiry() -> None:
            with self._state_lock:
                entry = self._pending.pop(utterance_id, None)
            if entry is None:
                return
            self._emit_final(
                utterance_id=utterance_id,
                started_at_ns=started_at_ns,
                t0_perf=t0_perf,
                decision="withheld_low_confidence",
                text_raw=asr_result.text,
                text_final=cleaned.text,
                confidence=float(asr_result.confidence),
                used_fallback=cleaned.used_fallback,
                mic_open_ms=entry.mic_open_ms,
                warmup_ms=entry.warmup_ms,
                capture_ms=entry.capture_ms,
                vad_ms=0.0,
                asr_ms=float(asr_result.latency_ms),
                cleanup_ms=float(cleaned.latency_ms),
                inject_ms=0.0,
                duration_ms=entry.duration_ms,
                vad_coverage=entry.vad_coverage,
                peak_dbfs=entry.peak_dbfs,
                error=None,
            )

        timer = threading.Timer(self._config.force_paste_window_ms / 1000.0, _on_expiry)
        timer.daemon = True
        entry = _PendingForcePaste(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            t0_perf=t0_perf,
            text_final=cleaned.text,
            cleaned=cleaned,
            asr_result=asr_result,
            duration_ms=duration_ms,
            vad_coverage=vad_coverage,
            peak_dbfs=peak_dbfs,
            mic_open_ms=mic_open_ms,
            warmup_ms=warmup_ms,
            capture_ms=capture_ms,
            timer=timer,
        )
        with self._state_lock:
            self._pending[utterance_id] = entry
        timer.start()
        self._emit_status(
            "idle",
            utterance_id=utterance_id,
            message=f"{self._config.force_paste_binding.upper()} to paste anyway",
            pending_force_paste=True,
        )
        logger.info(
            "audio_dictate: utterance %s withheld (confidence=%.2f); "
            "press %s within %d ms to paste",
            utterance_id,
            asr_result.confidence,
            self._config.force_paste_binding,
            self._config.force_paste_window_ms,
        )

    def _handle_force_paste(self, event: TriggerEvent) -> None:
        """Force-paste hotkey callback: paste the most-recent pending utterance."""
        if self._active_force_paste_mode != "listener":
            return
        with self._state_lock:
            if not self._pending:
                logger.info("audio_dictate: force-paste pressed with no pending utterance")
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

        self._emit_final(
            utterance_id=entry.utterance_id,
            started_at_ns=entry.started_at_ns,
            t0_perf=entry.t0_perf,
            decision=decision,
            text_raw=entry.asr_result.text,
            text_final=entry.text_final,
            confidence=float(entry.asr_result.confidence),
            used_fallback=entry.cleaned.used_fallback,
            mic_open_ms=entry.mic_open_ms,
            warmup_ms=entry.warmup_ms,
            capture_ms=entry.capture_ms,
            vad_ms=0.0,
            asr_ms=float(entry.asr_result.latency_ms),
            cleanup_ms=float(entry.cleaned.latency_ms),
            inject_ms=inject_ms,
            duration_ms=entry.duration_ms,
            vad_coverage=entry.vad_coverage,
            peak_dbfs=entry.peak_dbfs,
            error=error,
        )

    # --- Emission helpers -------------------------------------------------

    def _emit_final(
        self,
        *,
        utterance_id: int,
        started_at_ns: int,
        t0_perf: float,
        decision: PasteDecision,
        text_raw: str,
        text_final: str,
        confidence: float,
        used_fallback: bool,
        mic_open_ms: float,
        warmup_ms: float,
        capture_ms: float,
        vad_ms: float,
        asr_ms: float,
        cleanup_ms: float,
        inject_ms: float,
        duration_ms: float,
        vad_coverage: float,
        peak_dbfs: float,
        error: str | None,
    ) -> None:
        ended_at_ns = self._deps.now_ns()
        total_ms = (self._deps.perf_counter() - t0_perf) * 1000.0
        latencies = {
            "mic_open_ms": float(mic_open_ms),
            "warmup_ms": float(warmup_ms),
            "capture_ms": float(capture_ms),
            "vad_ms": float(vad_ms),
            "asr_ms": float(asr_ms),
            "cleanup_ms": float(cleanup_ms),
            "inject_ms": float(inject_ms),
            "total_ms": total_ms,
        }
        processed = UtteranceProcessed(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            ended_at_ns=ended_at_ns,
            text_raw=text_raw,
            text_final=text_final,
            confidence=confidence,
            used_fallback=used_fallback,
            decision=decision,
            latencies=latencies,
            duration_ms=duration_ms,
            vad_coverage=vad_coverage,
            peak_dbfs=peak_dbfs,
            trigger_mode=self._config.trigger_mode,
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
                "mic_open_ms": 0.0,
                "warmup_ms": 0.0,
                "capture_ms": 0.0,
                "vad_ms": 0.0,
                "asr_ms": 0.0,
                "cleanup_ms": 0.0,
                "inject_ms": 0.0,
                "total_ms": 0.0,
            },
            duration_ms=0.0,
            vad_coverage=0.0,
            peak_dbfs=float("-inf"),
            trigger_mode=self._config.trigger_mode,
            error=reason,
        )
        self._finalize(processed)

    def _finalize(self, processed: UtteranceProcessed) -> None:
        """Write JSONL + latency-log row, then notify subscribers."""
        peak = processed.peak_dbfs if processed.peak_dbfs != float("-inf") else None
        self._jsonl.write(
            {
                "event_type": "utterance_processed",
                "utterance_id": processed.utterance_id,
                "ts_ns": processed.ended_at_ns,
                "started_at_ns": processed.started_at_ns,
                "pipeline": processed.pipeline,
                "trigger_mode": processed.trigger_mode,
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
                "duration_ms": processed.duration_ms,
                "vad_coverage": processed.vad_coverage,
                "peak_dbfs": peak,
                "error": processed.error,
            }
        )

        compute_type = getattr(self._asr, "compute_type", None) or "unknown"
        device = getattr(self._asr, "device", None) or "unknown"
        lat = processed.latencies
        breakdown = (
            f"open={lat['mic_open_ms']:.0f} "
            f"warm={lat['warmup_ms']:.0f} "
            f"cap={lat['capture_ms']:.0f} "
            f"asr={lat['asr_ms']:.0f} "
            f"clean={lat['cleanup_ms']:.0f} "
            f"inject={lat['inject_ms']:.0f}"
        )
        notes = (
            f"mode={processed.trigger_mode} decision={processed.decision} "
            f"confidence={processed.confidence:.2f} "
            f"compute_type={compute_type} device={device} "
            f"prompt={self._config.cleanup.prompt_version} "
            f"fallback={processed.used_fallback} [{breakdown}]"
        )
        if processed.error:
            notes += f" error={processed.error}"
        try:
            self._deps.latency_writer(
                "TICKET-012",
                self._config.hardware_label,
                "pipeline",
                processed.latencies["total_ms"],
                1,
                notes,
            )
        except Exception:
            logger.exception("audio_dictate: failed to append latency row")

        self._notify(processed)
        self._emit_status("idle", utterance_id=processed.utterance_id)


# --- Helpers --------------------------------------------------------------


def _safe_join(thread: threading.Thread, *, timeout: float) -> None:
    """Join ``thread`` while tolerating the race where ``close()`` runs before
    ``thread.start()`` has been called.

    The pipeline appends dispatch threads to ``_dispatch_threads`` under a
    lock and then calls ``thread.start()``; a shutdown in between would
    otherwise raise ``RuntimeError('cannot join thread before it is
    started')``.
    """
    try:
        thread.join(timeout=timeout)
    except RuntimeError:
        logger.debug(
            "audio_dictate: skipped join for thread %r (not yet started)",
            thread.name,
        )


def _utterance_duration_ms(utt: Utterance | None) -> float:
    if utt is None:
        return 0.0
    try:
        return float(utt.duration_s) * 1000.0
    except Exception:
        return 0.0


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


def load_audio_dictate_config(path: Path | None = None) -> AudioDictateConfig:
    """Load :class:`AudioDictateConfig` from TOML (or defaults).

    Accepts a file that omits any/all of the ``[mic]``, ``[asr]``,
    ``[cleanup]``, ``[inject]``, ``[hotkey]``, ``[pipeline]`` sections.
    Every present field overlays the corresponding nested model via
    :meth:`pydantic.BaseModel.model_copy`.
    """
    target = path if path is not None else DEFAULT_CONFIG_PATH
    cfg = AudioDictateConfig()
    if not target.is_file():
        return cfg
    with target.open("rb") as f:
        data = tomllib.load(f)

    updates: dict[str, Any] = {
        "mic": _update_from_section(cfg.mic, data.get("mic")),
        "asr": _update_from_section(cfg.asr, data.get("asr")),
        "cleanup": _update_from_section(cfg.cleanup, data.get("cleanup")),
        "inject": _update_from_section(cfg.inject, data.get("inject")),
        "hotkey": _update_from_section(cfg.hotkey, data.get("hotkey")),
    }
    pipeline = data.get("pipeline") or {}
    pipeline_overrides = {
        k: v for k, v in pipeline.items() if k in AudioDictateConfig.model_fields
    }
    if "jsonl_dir" in pipeline_overrides and isinstance(
        pipeline_overrides["jsonl_dir"], str
    ):
        pipeline_overrides["jsonl_dir"] = Path(pipeline_overrides["jsonl_dir"])
    updates.update(pipeline_overrides)

    # Reconstruct through the constructor so the model validator re-runs
    # (``model_copy(update=...)`` skips validators in pydantic v2).
    return AudioDictateConfig.model_validate({**cfg.model_dump(), **updates})


# --- CLI entry point ------------------------------------------------------


def run_audio_dictate(
    config: AudioDictateConfig | None = None,
    *,
    deps: _Deps | None = None,
    stop_event: threading.Event | None = None,
    ui: UiMode = "tui",
) -> int:
    """Run the pipeline until ``stop_event`` is set or Ctrl+C arrives."""
    cfg = config or AudioDictateConfig()
    stop = stop_event if stop_event is not None else threading.Event()
    ui_mode = normalize_ui_mode(ui)

    active_force = (
        cfg.force_paste_mode_ptt
        if cfg.trigger_mode == "push_to_talk"
        else cfg.force_paste_mode_vad
    )
    print(
        "sabi dictate: mode={mode}  binding={binding}  "
        "force_paste={fmode}({fbind})  dry_run={dry}".format(
            mode=cfg.trigger_mode,
            binding=cfg.hotkey.binding,
            fmode=active_force,
            fbind=cfg.force_paste_binding,
            dry=cfg.dry_run,
        )
    )
    if cfg.trigger_mode == "push_to_talk":
        print("Hold the hotkey to dictate. Ctrl+C to exit.")
    else:
        print(
            "Press the hotkey once to start VAD streaming; press again to stop. "
            "Ctrl+C to exit."
        )

    status_tui = None
    if ui_mode == "tui":
        from sabi.ui.status_tui import StatusTUI

        status_tui = StatusTUI()
        status_tui.handle_status(_initial_audio_status(cfg))
        status_tui.start()

    pipeline = AudioDictatePipeline(cfg, deps=deps)
    if status_tui is not None:
        pipeline.subscribe_status(status_tui.handle_status)
        pipeline.subscribe(status_tui.handle_utterance)
    else:
        pipeline.subscribe(_print_audio_event)

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


def _initial_audio_status(cfg: AudioDictateConfig) -> PipelineStatusEvent:
    return PipelineStatusEvent(
        pipeline="audio",
        mode="idle",
        hotkey_binding=cfg.hotkey.binding,
        force_paste_binding=cfg.force_paste_binding,
        ollama_ok=None,
        ollama_model=cfg.cleanup.model,
        cuda_status=_cuda_status(cfg.asr.device),
        created_at_ns=time.monotonic_ns(),
    )


def _print_audio_event(ev: UtteranceProcessed) -> None:
    line = (
        f"[{ev.decision.upper()}] id={ev.utterance_id} "
        f"text={ev.text_final!r} conf={ev.confidence:.2f} "
        f"dur_ms={ev.duration_ms:.0f} total_ms={ev.latencies['total_ms']:.0f}"
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
    "AudioDictateConfig",
    "AudioDictatePipeline",
    "PasteDecision",
    "TriggerMode",
    "UtteranceProcessed",
    "load_audio_dictate_config",
    "run_audio_dictate",
]
