"""Dictation pipeline session handlers for the sidecar."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, is_dataclass
from typing import Any, Literal

from pydantic import BaseModel

from sabi.input.hotkey import TriggerEvent
from sabi.sidecar.dispatcher import Notify, SidecarDispatcher

PipelineKind = Literal["silent", "audio", "fused"]


def _to_payload(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


class DictationSessionManager:
    """Own at most one long-running dictation pipeline for the sidecar."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._ready: threading.Event | None = None
        self._stop: threading.Event | None = None
        self._kind: PipelineKind | None = None
        self._pipeline: Any | None = None
        self._active_trigger: TriggerEvent | None = None
        self._next_trigger_id = 1
        self._last_status: dict[str, Any] | None = None

    def start(self, kind: PipelineKind, params: dict[str, Any], notify: Notify) -> dict[str, Any]:
        dry_run = bool(params.get("dry_run", True))
        old_thread: threading.Thread | None = None
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._kind != kind:
                old_thread = self._stop_session_locked()
            if self._thread is None or not self._thread.is_alive():
                ready = threading.Event()
                stop = threading.Event()
                thread = threading.Thread(
                    target=self._run,
                    args=(kind, dry_run, ready, stop, notify),
                    name=f"sabi-sidecar-{kind}",
                    daemon=True,
                )
                self._thread = thread
                self._ready = ready
                self._stop = stop
                self._kind = kind
                self._last_status = {"pipeline": kind, "mode": "starting"}
                thread.start()
                notify(f"dictation.{kind}.status", {"pipeline": kind, "mode": "starting"})
            else:
                ready = self._ready

        if old_thread is not None:
            old_thread.join(timeout=3.0)
        if ready is None or not ready.wait(timeout=60.0):
            raise TimeoutError(f"dictation {kind} pipeline did not become ready")
        self._trigger_start(kind)
        return {"pipeline": kind, "running": True, "capturing": True, "dry_run": dry_run}

    def stop(self, kind: PipelineKind, _params: dict[str, Any], notify: Notify) -> dict[str, Any]:
        stopped_capture = self._trigger_stop(kind)
        notify(
            f"dictation.{kind}.status",
            {"pipeline": kind, "mode": "stopped" if stopped_capture else "idle"},
        )
        return {"pipeline": kind, "running": self._is_running(kind), "capturing": False}

    def shutdown(self, kind: PipelineKind, _params: dict[str, Any], notify: Notify) -> dict[str, Any]:
        with self._lock:
            if self._thread is None or self._stop is None or self._kind != kind:
                return {"pipeline": kind, "running": False}
            thread = self._stop_session_locked()
        thread.join(timeout=3.0)
        running = thread.is_alive()
        if not running:
            with self._lock:
                self._last_status = {"pipeline": kind, "mode": "idle"}
        notify(
            f"dictation.{kind}.status",
            {"pipeline": kind, "mode": "stopped", "running": running},
        )
        return {"pipeline": kind, "running": running}

    def _stop_session_locked(self) -> threading.Thread:
        thread = self._thread
        if self._stop is not None:
            self._stop.set()
        self._thread = None
        self._ready = None
        self._stop = None
        self._kind = None
        self._pipeline = None
        self._active_trigger = None
        if thread is None:
            raise RuntimeError("dictation session was not running")
        return thread

    def _is_running(self, kind: PipelineKind) -> bool:
        with self._lock:
            return (
                self._thread is not None
                and self._thread.is_alive()
                and (self._kind == kind or kind == self._kind)
            )

    def _trigger_start(self, kind: PipelineKind) -> None:
        with self._lock:
            pipeline = self._pipeline
            if pipeline is None or self._kind != kind:
                raise ValueError(f"dictation pipeline is not ready: {kind}")
            if self._active_trigger is not None:
                return
            event = TriggerEvent(
                trigger_id=self._next_trigger_id,
                mode="push_to_talk",
                started_at_ns=time.monotonic_ns(),
                reason="cli",
            )
            self._next_trigger_id += 1
            self._active_trigger = event
        try:
            pipeline.on_trigger_start(event)
        except Exception:
            with self._lock:
                if self._active_trigger == event:
                    self._active_trigger = None
            raise

    def _trigger_stop(self, kind: PipelineKind) -> bool:
        with self._lock:
            pipeline = self._pipeline
            event = self._active_trigger
            self._active_trigger = None
            if pipeline is None or self._kind != kind or event is None:
                return False
            stop_event = TriggerEvent(
                trigger_id=event.trigger_id,
                mode=event.mode,
                started_at_ns=event.started_at_ns,
                reason="cli",
            )
        pipeline.on_trigger_stop(stop_event)
        return True

    def status(
        self,
        kind: PipelineKind,
        _params: dict[str, Any],
        _notify: Notify,
    ) -> dict[str, Any]:
        with self._lock:
            running = (
                self._thread is not None
                and self._thread.is_alive()
                and (self._kind == kind or kind == self._kind)
            )
            return {
                "pipeline": kind,
                "running": running,
                "active_pipeline": self._kind,
                "last_status": self._last_status,
            }

    def _remember_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_status = payload

    def _run(
        self,
        kind: PipelineKind,
        dry_run: bool,
        ready: threading.Event,
        stop: threading.Event,
        notify: Notify,
    ) -> None:
        pipeline: Any | None = None
        try:
            pipeline = self._make_pipeline(kind, dry_run)

            def _status(event: Any) -> None:
                payload = _to_payload(event)
                self._remember_status(payload)
                notify(f"dictation.{kind}.status", payload)

            def _final(event: Any) -> None:
                notify(f"dictation.{kind}.utterance", _to_payload(event))

            pipeline.subscribe_status(_status)
            pipeline.subscribe(_final)
            with pipeline:
                with self._lock:
                    self._pipeline = pipeline
                ready.set()
                while not stop.wait(timeout=0.5):
                    pass
        except Exception as exc:  # noqa: BLE001 - keep sidecar process alive
            notify(f"dictation.{kind}.error", {"pipeline": kind, "error": str(exc)})
        finally:
            with self._lock:
                if self._pipeline is pipeline:
                    self._pipeline = None
                self._active_trigger = None
            ready.set()
            notify(f"dictation.{kind}.status", {"pipeline": kind, "mode": "idle"})

    def _make_pipeline(self, kind: PipelineKind, dry_run: bool) -> Any:
        if kind == "silent":
            from sabi.pipelines.silent_dictate import SilentDictateConfig, SilentDictatePipeline

            return SilentDictatePipeline(SilentDictateConfig(dry_run=dry_run))
        if kind == "audio":
            from sabi.pipelines.audio_dictate import AudioDictateConfig, AudioDictatePipeline

            return AudioDictatePipeline(AudioDictateConfig(dry_run=dry_run))
        if kind == "fused":
            from sabi.pipelines.fused_dictate import FusedDictateConfig, FusedDictatePipeline

            return FusedDictatePipeline(FusedDictateConfig(dry_run=dry_run))
        raise ValueError(f"unknown pipeline: {kind}")


SESSION_MANAGER = DictationSessionManager()


def register_dictation_handlers(
    dispatcher: SidecarDispatcher,
    manager: DictationSessionManager,
) -> None:
    for kind in ("silent", "audio", "fused"):
        dispatcher.register(
            f"dictation.{kind}.start",
            lambda params, notify, pipeline=kind: manager.start(pipeline, params, notify),
        )
        dispatcher.register(
            f"dictation.{kind}.stop",
            lambda params, notify, pipeline=kind: manager.stop(pipeline, params, notify),
        )
        dispatcher.register(
            f"dictation.{kind}.shutdown",
            lambda params, notify, pipeline=kind: manager.shutdown(pipeline, params, notify),
        )
        dispatcher.register(
            f"dictation.{kind}.status",
            lambda params, notify, pipeline=kind: manager.status(pipeline, params, notify),
        )
