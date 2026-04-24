"""TICKET-011: SilentDictatePipeline tests.

Every hardware-touching component is replaced with a fake injected via
``SilentDictatePipeline(..., deps=_Deps(...))`` so the full flow runs
without a webcam, CUDA, Ollama, clipboard, or real keyboard hook.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from sabi.capture.lip_roi import LipFrame
from sabi.cleanup.ollama import CleanedText
from sabi.input.hotkey import HotkeyConfig, TriggerBus, TriggerEvent
from sabi.models.vsr.model import VSRResult
from sabi.output.inject import InjectConfig, InjectResult
from sabi.pipelines.silent_dictate import (
    SilentDictateConfig,
    SilentDictatePipeline,
    UtteranceProcessed,
    _Deps,
    load_silent_dictate_config,
)


# --- Fakes ----------------------------------------------------------------


class FakeWebcam:
    """Minimal context manager with a pre-seeded frame queue."""

    def __init__(self, frames: list[tuple[int, np.ndarray]]) -> None:
        self._q: queue.Queue[tuple[int, np.ndarray]] = queue.Queue()
        for item in frames:
            self._q.put(item)
        self._last: tuple[int, np.ndarray] | None = None
        self.entered = False
        self.exited = False

    def __enter__(self) -> "FakeWebcam":
        self.entered = True
        return self

    def __exit__(self, *a: Any) -> None:
        self.exited = True

    def get_latest(self, timeout: float | None = None) -> tuple[int, np.ndarray]:
        try:
            item = self._q.get(timeout=timeout)
        except queue.Empty:
            if self._last is not None:
                return self._last
            raise TimeoutError("FakeWebcam: no frames and no previous")
        self._last = item
        return item


class WebcamFactory:
    """Hands out a fresh :class:`FakeWebcam` per ``__call__`` (per-trigger)."""

    def __init__(self, frame_batches: list[list[tuple[int, np.ndarray]]]) -> None:
        self._batches = list(frame_batches)
        self.instances: list[FakeWebcam] = []

    def __call__(self, _cfg: Any) -> FakeWebcam:
        frames = self._batches.pop(0) if self._batches else []
        cam = FakeWebcam(frames)
        self.instances.append(cam)
        return cam


class FakeROI:
    """Deterministic LipROI replacement driven by a face-present pattern."""

    def __init__(self, pattern: list[bool]) -> None:
        self._pattern = list(pattern)
        self._idx = 0
        self.calls = 0

    def __enter__(self) -> "FakeROI":
        return self

    def __exit__(self, *a: Any) -> None:
        pass

    def process_frame(self, ts_ns: int, _frame_rgb: np.ndarray) -> LipFrame | None:
        self.calls += 1
        if self._idx < len(self._pattern):
            present = self._pattern[self._idx]
            self._idx += 1
        elif self._pattern:
            present = self._pattern[-1]
        else:
            present = True
        if not present:
            return None
        crop = np.zeros((96, 96), dtype=np.uint8)
        return LipFrame(
            timestamp_ns=ts_ns,
            crop=crop,
            confidence=0.9,
            face_present=True,
            bbox=(0.0, 0.0, 96.0, 0.0),
        )


class FakeVSR:
    def __init__(
        self,
        text: str = "hello world",
        confidence: float = 0.9,
        latency_ms: float = 12.0,
    ) -> None:
        self.device = "cpu"
        self.calls: list[list[LipFrame]] = []
        self._text = text
        self._confidence = confidence
        self._latency_ms = latency_ms

    def __enter__(self) -> "FakeVSR":
        return self

    def __exit__(self, *a: Any) -> None:
        pass

    def predict(self, frames: Any) -> VSRResult:
        self.calls.append(list(frames))
        return VSRResult(
            text=self._text,
            confidence=self._confidence,
            per_token_scores=None,
            latency_ms=self._latency_ms,
        )


class FakeCleaner:
    def __init__(
        self,
        *,
        used_fallback: bool = False,
        latency_ms: float = 5.0,
        available: bool = True,
        transform: Callable[[str], str] | None = None,
    ) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._fallback = used_fallback
        self._latency_ms = latency_ms
        self._available = available
        self._transform = transform or (lambda s: s)

    def __enter__(self) -> "FakeCleaner":
        return self

    def __exit__(self, *a: Any) -> None:
        pass

    def is_available(self) -> bool:
        return self._available

    def cleanup(self, text: str, ctx: Any) -> CleanedText:
        self.calls.append((text, ctx))
        return CleanedText(
            text=self._transform(text),
            latency_ms=self._latency_ms,
            used_fallback=self._fallback,
            reason="fallback" if self._fallback else None,
        )


class FakePaste:
    def __init__(self, *, latency_ms: float = 2.0, error: str | None = None) -> None:
        self.calls: list[tuple[str, InjectConfig]] = []
        self._latency_ms = latency_ms
        self._error = error

    def __call__(self, text: str, cfg: InjectConfig) -> InjectResult:
        self.calls.append((text, cfg))
        return InjectResult(
            text=text,
            length=len(text),
            latency_ms=self._latency_ms,
            error=self._error,
        )


class FakeHotkey:
    """Stand-in for :class:`HotkeyController`; exposes a real TriggerBus."""

    def __init__(self, cfg: HotkeyConfig) -> None:
        self.config = cfg
        self.bus = TriggerBus()
        self.started = False
        self.stopped = False

    def start(self) -> "FakeHotkey":
        self.started = True
        return self

    def stop(self) -> None:
        self.stopped = True
        self.bus.shutdown()


class HotkeyFactory:
    """Return a primary vs force-paste FakeHotkey based on binding."""

    def __init__(self, primary_binding: str) -> None:
        self._primary_binding = primary_binding
        self.primary: FakeHotkey | None = None
        self.force: FakeHotkey | None = None

    def __call__(self, cfg: HotkeyConfig) -> FakeHotkey:
        hk = FakeHotkey(cfg)
        if cfg.binding == self._primary_binding:
            self.primary = hk
        else:
            self.force = hk
        return hk


class LatencyRecorder:
    def __init__(self) -> None:
        self.rows: list[tuple[Any, ...]] = []

    def __call__(
        self,
        ticket: str,
        hardware: str,
        stage: str,
        latency_ms: float,
        samples: int,
        notes: str,
        **_kwargs: Any,
    ) -> None:
        self.rows.append((ticket, hardware, stage, latency_ms, samples, notes))


# --- Fixtures -------------------------------------------------------------


@pytest.fixture
def base_frames() -> list[tuple[int, np.ndarray]]:
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    return [(i * 40_000_000, rgb) for i in range(8)]


def _build(
    *,
    cfg: SilentDictateConfig,
    frame_batches: list[list[tuple[int, np.ndarray]]] | None = None,
    roi: FakeROI | None = None,
    vsr: FakeVSR | None = None,
    cleaner: FakeCleaner | None = None,
    paste: FakePaste | None = None,
    latency: LatencyRecorder | None = None,
) -> tuple[SilentDictatePipeline, dict[str, Any]]:
    webcam_factory = WebcamFactory(frame_batches or [])
    roi_ = roi or FakeROI([True] * 32)
    vsr_ = vsr or FakeVSR()
    cleaner_ = cleaner or FakeCleaner()
    paste_ = paste or FakePaste()
    hotkey_factory = HotkeyFactory(primary_binding=cfg.hotkey.binding)
    latency_ = latency or LatencyRecorder()

    deps = _Deps(
        webcam_factory=webcam_factory,
        roi_factory=lambda _c: roi_,
        vsr_factory=lambda _c: vsr_,
        cleaner_factory=lambda _c: cleaner_,
        hotkey_factory=hotkey_factory,
        paste_fn=paste_,
        latency_writer=latency_,
    )
    pipeline = SilentDictatePipeline(cfg, deps=deps)
    return pipeline, {
        "webcam_factory": webcam_factory,
        "roi": roi_,
        "vsr": vsr_,
        "cleaner": cleaner_,
        "paste": paste_,
        "hotkey_factory": hotkey_factory,
        "latency": latency_,
    }


def _drain_bus(bus: TriggerBus, *, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not bus._queue.empty():
        if time.monotonic() > deadline:
            raise TimeoutError("bus did not drain")
        time.sleep(0.005)
    time.sleep(0.02)


def _wait_for(pred: Callable[[], bool], *, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def _wait_events(events: list[Any], count: int, *, timeout: float = 3.0) -> None:
    if not _wait_for(lambda: len(events) >= count, timeout=timeout):
        raise TimeoutError(f"only got {len(events)} events, expected {count}")


def _wait_dispatch(pipeline: SilentDictatePipeline, *, timeout: float = 3.0) -> None:
    """Wait for at least one dispatch thread to appear, then for it to finish."""
    deadline = time.monotonic() + timeout

    def _saw_dispatch() -> bool:
        with pipeline._state_lock:
            return bool(pipeline._dispatch_threads)

    # Either a dispatch thread appeared or the utterance counter moved.
    _wait_for(_saw_dispatch, timeout=timeout)
    while True:
        with pipeline._state_lock:
            threads = list(pipeline._dispatch_threads)
        alive = [t for t in threads if t.is_alive()]
        if not alive:
            return
        remaining = max(0.01, deadline - time.monotonic())
        for t in alive:
            t.join(timeout=remaining)
        if time.monotonic() > deadline:
            return


def _fire_trigger(
    hk: FakeHotkey,
    *,
    mode: str = "push_to_talk",
    hold_ms: int = 120,
) -> tuple[TriggerEvent, TriggerEvent]:
    start = TriggerEvent(
        trigger_id=hk.bus.next_trigger_id(),
        mode=mode,  # type: ignore[arg-type]
        started_at_ns=time.monotonic_ns(),
        reason="hotkey",
    )
    hk.bus.emit_start(start)
    time.sleep(hold_ms / 1000.0)
    stop = TriggerEvent(
        trigger_id=start.trigger_id,
        mode=mode,  # type: ignore[arg-type]
        started_at_ns=start.started_at_ns,
        reason="hotkey",
    )
    hk.bus.emit_stop(stop)
    return start, stop


def _fire_force_paste(hk: FakeHotkey) -> TriggerEvent:
    ev = TriggerEvent(
        trigger_id=hk.bus.next_trigger_id(),
        mode="push_to_talk",
        started_at_ns=time.monotonic_ns(),
        reason="hotkey",
    )
    hk.bus.emit_start(ev)
    return ev


# --- Tests ----------------------------------------------------------------


def test_happy_path_pastes_and_logs(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        force_paste_mode="never",  # short-circuit listener setup
    )
    pipeline, bag = _build(cfg=cfg, frame_batches=[base_frames])
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        primary = bag["hotkey_factory"].primary
        assert primary is not None
        _fire_trigger(primary, hold_ms=80)
        _drain_bus(primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    ev = events[0]
    assert ev.decision == "pasted"
    assert ev.text_final == "hello world"
    assert ev.frame_count == len(base_frames)
    assert 0.99 <= ev.face_present_ratio <= 1.0
    assert bag["paste"].calls == [("hello world", cfg.inject)]
    assert bag["vsr"].calls  # VSR was invoked

    rows = bag["latency"].rows
    assert len(rows) == 1
    assert rows[0][0] == "TICKET-011"
    assert "decision=pasted" in rows[0][5]

    jsonl_files = sorted(tmp_path.glob("silent_dictate_*.jsonl"))
    assert jsonl_files, "JSONL file not created"
    payload = [json.loads(line) for line in jsonl_files[0].read_text("utf-8").splitlines()]
    types = [p["event_type"] for p in payload]
    assert "trigger_start" in types
    assert "trigger_stop" in types
    assert "utterance_processed" in types
    utter = next(p for p in payload if p["event_type"] == "utterance_processed")
    assert set(utter["latencies"].keys()) == {
        "capture_open_ms",
        "capture_ms",
        "roi_ms",
        "vsr_ms",
        "cleanup_ms",
        "inject_ms",
        "total_ms",
    }


def test_ollama_fallback_still_pastes(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        force_paste_mode="never",
    )
    pipeline, bag = _build(
        cfg=cfg,
        frame_batches=[base_frames],
        cleaner=FakeCleaner(used_fallback=True, available=False),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=80)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "pasted"
    assert events[0].used_fallback is True
    assert bag["paste"].calls and bag["paste"].calls[0][0] == "hello world"


def test_occluded_camera_withholds_paste(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        occlusion_threshold=0.6,
        force_paste_mode="never",
    )
    pattern = [True, True] + [False] * 12  # ~14% face-present
    pipeline, bag = _build(cfg=cfg, frame_batches=[base_frames], roi=FakeROI(pattern))
    events: list[UtteranceProcessed] = []
    with caplog.at_level("ERROR"):
        with pipeline as p:
            p.subscribe(events.append)
            _fire_trigger(bag["hotkey_factory"].primary, hold_ms=80)
            _drain_bus(bag["hotkey_factory"].primary.bus)
            _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "withheld_occluded"
    assert bag["paste"].calls == []
    assert any("camera could not see your mouth" in m for m in caplog.messages)


def test_empty_capture_withholds(tmp_path: Path) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        force_paste_mode="never",
    )
    pipeline, bag = _build(cfg=cfg, frame_batches=[[]])
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "withheld_empty"
    assert events[0].frame_count == 0
    assert bag["paste"].calls == []
    assert bag["vsr"].calls == []


def test_low_confidence_listener_withholds_after_timeout(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        confidence_floor=0.9,
        force_paste_mode="listener",
        force_paste_window_ms=80,
    )
    pipeline, bag = _build(
        cfg=cfg,
        frame_batches=[base_frames],
        vsr=FakeVSR(text="hello", confidence=0.2),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=50)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)
        time.sleep(0.2)  # let the 80 ms timer expire

    assert len(events) == 1
    assert events[0].decision == "withheld_low_confidence"
    assert events[0].text_final == "hello"
    assert bag["paste"].calls == []


def test_force_paste_hit_triggers_paste(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        confidence_floor=0.9,
        force_paste_mode="listener",
        force_paste_window_ms=1000,
    )
    pipeline, bag = _build(
        cfg=cfg,
        frame_batches=[base_frames],
        vsr=FakeVSR(text="force me", confidence=0.15),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=50)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)
        # Utterance is now pending; fire F12 within the window.
        assert bag["hotkey_factory"].force is not None
        _fire_force_paste(bag["hotkey_factory"].force)
        _drain_bus(bag["hotkey_factory"].force.bus)

    assert len(events) == 1
    assert events[0].decision == "force_pasted"
    assert events[0].text_final == "force me"
    assert bag["paste"].calls and bag["paste"].calls[0][0] == "force me"

    jsonl_files = sorted(tmp_path.glob("silent_dictate_*.jsonl"))
    payload = [json.loads(line) for line in jsonl_files[0].read_text("utf-8").splitlines()]
    types = [p["event_type"] for p in payload]
    assert "force_paste_hit" in types


def test_force_paste_always_mode_ignores_confidence_floor(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        confidence_floor=0.99,
        force_paste_mode="always",
    )
    pipeline, bag = _build(
        cfg=cfg,
        frame_batches=[base_frames],
        vsr=FakeVSR(text="bypass", confidence=0.1),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=60)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "pasted"
    assert bag["paste"].calls and bag["paste"].calls[0][0] == "bypass"


def test_dry_run_prints_and_skips_paste(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        dry_run=True,
        force_paste_mode="never",
    )
    pipeline, bag = _build(
        cfg=cfg,
        frame_batches=[base_frames],
        vsr=FakeVSR(text="dry text", confidence=0.9),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=60)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "dry_run"
    assert bag["paste"].calls == []
    out = capsys.readouterr().out
    assert "dry text" in out


def test_latency_keys_present_and_monotonic(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    """All six per-stage keys plus total_ms populate, total_ms > 0."""
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        force_paste_mode="never",
    )
    pipeline, bag = _build(
        cfg=cfg,
        frame_batches=[base_frames],
        vsr=FakeVSR(latency_ms=33.0),
        cleaner=FakeCleaner(latency_ms=7.0),
        paste=FakePaste(latency_ms=4.0),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=60)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    lat = events[0].latencies
    for key in ("capture_open_ms", "capture_ms", "roi_ms", "vsr_ms", "cleanup_ms", "inject_ms", "total_ms"):
        assert key in lat, f"missing latency key: {key}"
        assert lat[key] >= 0.0
    assert lat["vsr_ms"] == 33.0
    assert lat["cleanup_ms"] == 7.0
    assert lat["inject_ms"] == 4.0
    assert lat["total_ms"] > 0.0


def test_config_overlay_from_toml(tmp_path: Path) -> None:
    toml_path = tmp_path / "silent_dictate.toml"
    toml_path.write_text(
        """
[webcam]
device_index = 2
target_fps = 30.0

[vsr]
device = "cpu"
precision = "fp16"

[hotkey]
binding = "ctrl+shift+f9"
min_hold_ms = 42

[pipeline]
confidence_floor = 0.5
force_paste_binding = "f11"
force_paste_window_ms = 999
force_paste_mode = "always"
keep_camera_open = true
dry_run = true
hardware_label = "wsl"
""",
        encoding="utf-8",
    )
    cfg = load_silent_dictate_config(toml_path)

    assert cfg.webcam.device_index == 2
    assert cfg.webcam.target_fps == 30.0
    assert cfg.vsr.device == "cpu"
    assert cfg.vsr.precision == "fp16"
    assert cfg.hotkey.binding == "ctrl+shift+f9"
    assert cfg.hotkey.min_hold_ms == 42
    assert cfg.confidence_floor == 0.5
    assert cfg.force_paste_binding == "f11"
    assert cfg.force_paste_window_ms == 999
    assert cfg.force_paste_mode == "always"
    assert cfg.keep_camera_open is True
    assert cfg.dry_run is True
    assert cfg.hardware_label == "wsl"


def test_duplicate_bindings_rejected() -> None:
    with pytest.raises(ValueError, match="must differ"):
        SilentDictateConfig(
            hotkey=HotkeyConfig(binding="f12"),
            force_paste_binding="F12",
        )


def test_close_is_idempotent(
    tmp_path: Path,
    base_frames: list[tuple[int, np.ndarray]],
) -> None:
    cfg = SilentDictateConfig(
        jsonl_dir=tmp_path,
        hotkey=HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        force_paste_mode="never",
    )
    pipeline, bag = _build(cfg=cfg, frame_batches=[base_frames])
    with pipeline as p:
        _fire_trigger(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)
    pipeline.close()  # second close must not raise
