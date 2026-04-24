"""TICKET-012: AudioDictatePipeline tests.

Every hardware-touching component is replaced with a fake injected via
``AudioDictatePipeline(..., deps=_Deps(...))`` so the full flow runs
without a microphone, CUDA, Ollama, clipboard, or real keyboard hook.
"""

from __future__ import annotations

import json
import math
import queue
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from sabi.capture.microphone import MicConfig, Utterance
from sabi.cleanup.ollama import CleanedText
from sabi.input.hotkey import HotkeyConfig, TriggerBus, TriggerEvent
from sabi.models.asr import ASRModelConfig, ASRResult
from sabi.output.inject import InjectConfig, InjectResult
from sabi.pipelines.audio_dictate import (
    AudioDictateConfig,
    AudioDictatePipeline,
    UtteranceProcessed,
    _Deps,
    load_audio_dictate_config,
)


# --- Fakes ----------------------------------------------------------------


def _make_utterance(
    *,
    text: str = "hello world",
    peak_dbfs: float = -20.0,
    mean_dbfs: float = -30.0,
    vad_coverage: float = 0.9,
    sample_rate: int = 16000,
    duration_s: float = 0.5,
    start_ts_ns: int | None = None,
) -> Utterance:
    samples = np.zeros(int(sample_rate * duration_s), dtype=np.float32)
    start = start_ts_ns if start_ts_ns is not None else time.time_ns()
    return Utterance(
        samples=samples,
        start_ts_ns=start,
        end_ts_ns=start + int(duration_s * 1e9),
        sample_rate=sample_rate,
        peak_dbfs=peak_dbfs,
        mean_dbfs=mean_dbfs,
        vad_coverage=vad_coverage,
    )


class FakeMicrophone:
    """Context manager with pre-seeded PTT and VAD utterance queues."""

    def __init__(
        self,
        *,
        ptt_utterances: list[Utterance] | None = None,
        ptt_default: Utterance | None = None,
    ) -> None:
        self._ptt_utterances: list[Utterance] = list(ptt_utterances or [])
        self._ptt_default = ptt_default or _make_utterance()
        self._vad_queue: queue.Queue[Utterance] = queue.Queue()
        self.enter_count = 0
        self.exit_count = 0
        self.ptt_calls = 0

    def enqueue_vad(self, utt: Utterance) -> None:
        self._vad_queue.put(utt)

    def __enter__(self) -> "FakeMicrophone":
        self.enter_count += 1
        return self

    def __exit__(self, *a: Any) -> None:
        self.exit_count += 1

    def push_to_talk_segment(
        self,
        start_evt: Any,
        end_evt: Any,
    ) -> Utterance:
        self.ptt_calls += 1
        start_evt.wait()
        end_evt.wait()
        if self._ptt_utterances:
            return self._ptt_utterances.pop(0)
        return self._ptt_default

    def next_utterance(self, timeout: float | None = None) -> Utterance | None:
        try:
            return self._vad_queue.get(timeout=timeout)
        except queue.Empty:
            return None


class MicFactory:
    """Hands out a fresh :class:`FakeMicrophone` per ``__call__``."""

    def __init__(self, mics: list[FakeMicrophone]) -> None:
        self._mics = list(mics)
        self.instances: list[FakeMicrophone] = []

    def __call__(self, _cfg: Any) -> FakeMicrophone:
        if self._mics:
            mic = self._mics.pop(0)
        else:
            mic = FakeMicrophone()
        self.instances.append(mic)
        return mic


class FakeASR:
    """Scripted faster-whisper replacement."""

    def __init__(
        self,
        *,
        text: str = "hello world",
        confidence: float = 0.9,
        latency_ms: float = 42.0,
        warmup_latency_ms: float = 10.0,
    ) -> None:
        self.device = "cpu"
        self.compute_type = "int8"
        self.transcribe_calls: list[Utterance] = []
        self.warm_up_calls = 0
        self._text = text
        self._confidence = confidence
        self._latency_ms = latency_ms
        self._warmup_latency_ms = warmup_latency_ms

    def __enter__(self) -> "FakeASR":
        return self

    def __exit__(self, *a: Any) -> None:
        pass

    def warm_up(self) -> ASRResult:
        self.warm_up_calls += 1
        return ASRResult(
            text="",
            segments=[],
            confidence=0.0,
            per_word_confidence=[],
            avg_logprob=0.0,
            latency_ms=self._warmup_latency_ms,
            language="en",
            device=self.device,
        )

    def transcribe(self, utt: Utterance) -> ASRResult:
        self.transcribe_calls.append(utt)
        return ASRResult(
            text=self._text,
            segments=[],
            confidence=self._confidence,
            per_word_confidence=[],
            avg_logprob=math.log(max(self._confidence, 1e-6)),
            latency_ms=self._latency_ms,
            language="en",
            device=self.device,
        )


class ScriptedFakeASR(FakeASR):
    """FakeASR whose transcribe walks through a list of canned responses."""

    def __init__(self, scripts: list[tuple[str, float]], latency_ms: float = 42.0) -> None:
        super().__init__(latency_ms=latency_ms)
        self._scripts = list(scripts)

    def transcribe(self, utt: Utterance) -> ASRResult:
        self.transcribe_calls.append(utt)
        if self._scripts:
            text, conf = self._scripts.pop(0)
        else:
            text, conf = ("", 0.0)
        return ASRResult(
            text=text,
            segments=[],
            confidence=conf,
            per_word_confidence=[],
            avg_logprob=math.log(max(conf, 1e-6)),
            latency_ms=self._latency_ms,
            language="en",
            device=self.device,
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


# --- Build helpers --------------------------------------------------------


def _build(
    *,
    cfg: AudioDictateConfig,
    mics: list[FakeMicrophone] | None = None,
    asr: FakeASR | None = None,
    cleaner: FakeCleaner | None = None,
    paste: FakePaste | None = None,
    latency: LatencyRecorder | None = None,
) -> tuple[AudioDictatePipeline, dict[str, Any]]:
    mic_factory = MicFactory(mics or [FakeMicrophone()])
    asr_ = asr or FakeASR()
    cleaner_ = cleaner or FakeCleaner()
    paste_ = paste or FakePaste()
    hotkey_factory = HotkeyFactory(primary_binding=cfg.hotkey.binding)
    latency_ = latency or LatencyRecorder()

    deps = _Deps(
        mic_factory=mic_factory,
        asr_factory=lambda _c: asr_,
        cleaner_factory=lambda _c: cleaner_,
        hotkey_factory=hotkey_factory,
        paste_fn=paste_,
        latency_writer=latency_,
    )
    pipeline = AudioDictatePipeline(cfg, deps=deps)
    return pipeline, {
        "mic_factory": mic_factory,
        "asr": asr_,
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


def _wait_dispatch(pipeline: AudioDictatePipeline, *, timeout: float = 3.0) -> None:
    """Wait for at least one dispatch thread to appear, then for all to finish."""
    deadline = time.monotonic() + timeout

    def _saw_dispatch() -> bool:
        with pipeline._state_lock:
            return bool(pipeline._dispatch_threads)

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


def _fire_ptt(
    hk: FakeHotkey,
    *,
    hold_ms: int = 80,
) -> tuple[TriggerEvent, TriggerEvent]:
    start = TriggerEvent(
        trigger_id=hk.bus.next_trigger_id(),
        mode="push_to_talk",
        started_at_ns=time.monotonic_ns(),
        reason="hotkey",
    )
    hk.bus.emit_start(start)
    time.sleep(hold_ms / 1000.0)
    stop = TriggerEvent(
        trigger_id=start.trigger_id,
        mode="push_to_talk",
        started_at_ns=start.started_at_ns,
        reason="hotkey",
    )
    hk.bus.emit_stop(stop)
    return start, stop


def _fire_vad_on(hk: FakeHotkey) -> TriggerEvent:
    ev = TriggerEvent(
        trigger_id=hk.bus.next_trigger_id(),
        mode="toggle",
        started_at_ns=time.monotonic_ns(),
        reason="hotkey",
    )
    hk.bus.emit_start(ev)
    return ev


def _fire_vad_off(hk: FakeHotkey) -> TriggerEvent:
    ev = TriggerEvent(
        trigger_id=hk.bus.next_trigger_id(),
        mode="toggle",
        started_at_ns=time.monotonic_ns(),
        reason="hotkey",
    )
    hk.bus.emit_stop(ev)
    return ev


def _fire_force_paste(hk: FakeHotkey) -> TriggerEvent:
    ev = TriggerEvent(
        trigger_id=hk.bus.next_trigger_id(),
        mode="push_to_talk",
        started_at_ns=time.monotonic_ns(),
        reason="hotkey",
    )
    hk.bus.emit_start(ev)
    return ev


# --- PTT tests ------------------------------------------------------------


def _ptt_cfg(tmp_path: Path, **overrides: Any) -> AudioDictateConfig:
    base = {
        "jsonl_dir": tmp_path,
        "hotkey": HotkeyConfig(binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0),
        "force_paste_mode_ptt": "never",
        "force_paste_mode_vad": "never",
    }
    base.update(overrides)
    return AudioDictateConfig(**base)


def test_ptt_happy_path_pastes_and_logs(tmp_path: Path) -> None:
    cfg = _ptt_cfg(tmp_path)
    pipeline, bag = _build(cfg=cfg)
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        primary = bag["hotkey_factory"].primary
        assert primary is not None
        _fire_ptt(primary, hold_ms=40)
        _drain_bus(primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    ev = events[0]
    assert ev.decision == "pasted"
    assert ev.text_final == "hello world"
    assert ev.pipeline == "audio"
    assert ev.trigger_mode == "push_to_talk"
    assert bag["paste"].calls == [("hello world", cfg.inject)]
    assert bag["asr"].transcribe_calls

    rows = bag["latency"].rows
    assert len(rows) == 1
    assert rows[0][0] == "TICKET-012"
    assert "decision=pasted" in rows[0][5]
    assert "mode=push_to_talk" in rows[0][5]

    jsonl_files = sorted(tmp_path.glob("audio_dictate_*.jsonl"))
    assert jsonl_files, "JSONL file not created"
    payload = [json.loads(line) for line in jsonl_files[0].read_text("utf-8").splitlines()]
    types = [p["event_type"] for p in payload]
    assert "trigger_start" in types
    assert "trigger_stop" in types
    assert "utterance_processed" in types
    utter = next(p for p in payload if p["event_type"] == "utterance_processed")
    assert set(utter["latencies"].keys()) == {
        "mic_open_ms",
        "warmup_ms",
        "capture_ms",
        "vad_ms",
        "asr_ms",
        "cleanup_ms",
        "inject_ms",
        "total_ms",
    }
    assert utter["pipeline"] == "audio"


def test_ptt_ollama_fallback_still_pastes(tmp_path: Path) -> None:
    cfg = _ptt_cfg(tmp_path)
    pipeline, bag = _build(
        cfg=cfg,
        cleaner=FakeCleaner(used_fallback=True, available=False),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "pasted"
    assert events[0].used_fallback is True
    assert bag["paste"].calls and bag["paste"].calls[0][0] == "hello world"


def test_ptt_silent_utterance_withholds(tmp_path: Path) -> None:
    cfg = _ptt_cfg(tmp_path)
    silent = _make_utterance(peak_dbfs=-80.0, vad_coverage=0.0)
    mic = FakeMicrophone(ptt_default=silent)
    pipeline, bag = _build(cfg=cfg, mics=[mic])
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "withheld_silence"
    assert bag["asr"].transcribe_calls == []
    assert bag["paste"].calls == []


def test_ptt_empty_asr_withholds(tmp_path: Path) -> None:
    cfg = _ptt_cfg(tmp_path)
    pipeline, bag = _build(
        cfg=cfg,
        asr=FakeASR(text="", confidence=0.0),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "withheld_empty"
    assert bag["paste"].calls == []


def test_ptt_low_confidence_listener_withholds_after_timeout(tmp_path: Path) -> None:
    cfg = _ptt_cfg(
        tmp_path,
        confidence_floor=0.95,
        force_paste_mode_ptt="listener",
        force_paste_window_ms=80,
    )
    pipeline, bag = _build(
        cfg=cfg,
        asr=FakeASR(text="hello", confidence=0.2),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)
        _wait_for(lambda: len(events) >= 1, timeout=1.5)

    assert len(events) == 1
    assert events[0].decision == "withheld_low_confidence"
    assert events[0].text_final == "hello"
    assert bag["paste"].calls == []


def test_ptt_force_paste_hit_triggers_paste(tmp_path: Path) -> None:
    cfg = _ptt_cfg(
        tmp_path,
        confidence_floor=0.95,
        force_paste_mode_ptt="listener",
        force_paste_window_ms=1000,
    )
    pipeline, bag = _build(
        cfg=cfg,
        asr=FakeASR(text="force me", confidence=0.15),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)
        # The utterance is pending; fire F12 within the window.
        assert bag["hotkey_factory"].force is not None
        _fire_force_paste(bag["hotkey_factory"].force)
        _drain_bus(bag["hotkey_factory"].force.bus)
        _wait_events(events, 1)

    assert len(events) == 1
    assert events[0].decision == "force_pasted"
    assert events[0].text_final == "force me"
    assert bag["paste"].calls and bag["paste"].calls[0][0] == "force me"

    jsonl_files = sorted(tmp_path.glob("audio_dictate_*.jsonl"))
    payload = [json.loads(line) for line in jsonl_files[0].read_text("utf-8").splitlines()]
    types = [p["event_type"] for p in payload]
    assert "force_paste_hit" in types


def test_ptt_force_paste_always_mode_ignores_floor(tmp_path: Path) -> None:
    cfg = _ptt_cfg(
        tmp_path,
        confidence_floor=0.99,
        force_paste_mode_ptt="always",
    )
    pipeline, bag = _build(
        cfg=cfg,
        asr=FakeASR(text="bypass", confidence=0.1),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "pasted"
    assert bag["paste"].calls and bag["paste"].calls[0][0] == "bypass"


# --- VAD tests ------------------------------------------------------------


def _vad_cfg(tmp_path: Path, **overrides: Any) -> AudioDictateConfig:
    base = {
        "jsonl_dir": tmp_path,
        "trigger_mode": "vad",
        "hotkey": HotkeyConfig(
            mode="toggle", binding="ctrl+alt+space", min_hold_ms=0, cooldown_ms=0
        ),
        "force_paste_mode_ptt": "never",
        "force_paste_mode_vad": "never",
    }
    base.update(overrides)
    return AudioDictateConfig(**base)


def test_vad_three_utterances_all_pasted(tmp_path: Path) -> None:
    cfg = _vad_cfg(tmp_path)
    mic = FakeMicrophone()
    scripted = ScriptedFakeASR(
        scripts=[("hello", 0.9), ("this is vad", 0.9), ("bye", 0.9)]
    )
    pipeline, bag = _build(cfg=cfg, mics=[mic], asr=scripted)
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        primary = bag["hotkey_factory"].primary
        assert primary is not None

        _fire_vad_on(primary)
        _drain_bus(primary.bus)
        assert _wait_for(lambda: pipeline._vad_active.is_set(), timeout=1.0)

        for _ in range(3):
            mic.enqueue_vad(_make_utterance())

        _wait_events(events, 3)

        _fire_vad_off(primary)
        _drain_bus(primary.bus)

    assert len(events) == 3
    assert [e.decision for e in events] == ["pasted", "pasted", "pasted"]
    # Dispatch threads run concurrently, so assert by multiset rather than
    # strict order.
    assert sorted(e.text_final for e in events) == sorted(
        ["hello", "this is vad", "bye"]
    )
    assert sorted(call[0] for call in bag["paste"].calls) == sorted(
        ["hello", "this is vad", "bye"]
    )
    for ev in events:
        assert ev.trigger_mode == "vad"

    jsonl_files = sorted(tmp_path.glob("audio_dictate_*.jsonl"))
    payload = [json.loads(line) for line in jsonl_files[0].read_text("utf-8").splitlines()]
    types = [p["event_type"] for p in payload]
    assert types.count("vad_activated") == 1
    assert types.count("vad_deactivated") == 1
    assert types.count("utterance_processed") == 3


def test_vad_force_paste_always_pastes_low_confidence(tmp_path: Path) -> None:
    cfg = _vad_cfg(
        tmp_path,
        confidence_floor=0.95,
        force_paste_mode_vad="always",
    )
    mic = FakeMicrophone()
    pipeline, bag = _build(
        cfg=cfg,
        mics=[mic],
        asr=FakeASR(text="whisper", confidence=0.1),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        primary = bag["hotkey_factory"].primary
        _fire_vad_on(primary)
        _drain_bus(primary.bus)
        mic.enqueue_vad(_make_utterance())
        _wait_events(events, 1)
        _fire_vad_off(primary)
        _drain_bus(primary.bus)

    assert events[0].decision == "pasted"
    assert bag["paste"].calls == [("whisper", cfg.inject)]


# --- Cross-cutting tests --------------------------------------------------


def test_dry_run_prints_and_skips_paste(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _ptt_cfg(tmp_path, dry_run=True)
    pipeline, bag = _build(
        cfg=cfg,
        asr=FakeASR(text="dry text", confidence=0.9),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert len(events) == 1
    assert events[0].decision == "dry_run"
    assert bag["paste"].calls == []
    out = capsys.readouterr().out
    assert "dry text" in out


def test_latency_keys_present_and_monotonic(tmp_path: Path) -> None:
    cfg = _ptt_cfg(tmp_path)
    pipeline, bag = _build(
        cfg=cfg,
        asr=FakeASR(latency_ms=33.0, warmup_latency_ms=11.0),
        cleaner=FakeCleaner(latency_ms=7.0),
        paste=FakePaste(latency_ms=4.0),
    )
    events: list[UtteranceProcessed] = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=60)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    lat = events[0].latencies
    for key in (
        "mic_open_ms",
        "warmup_ms",
        "capture_ms",
        "vad_ms",
        "asr_ms",
        "cleanup_ms",
        "inject_ms",
        "total_ms",
    ):
        assert key in lat, f"missing latency key: {key}"
        assert lat[key] >= 0.0
    assert lat["warmup_ms"] == 11.0
    assert lat["asr_ms"] == 33.0
    assert lat["cleanup_ms"] == 7.0
    assert lat["inject_ms"] == 4.0
    assert lat["total_ms"] > 0.0


def test_config_overlay_from_toml(tmp_path: Path) -> None:
    toml_path = tmp_path / "audio_dictate.toml"
    toml_path.write_text(
        """
[mic]
sample_rate = 24000
vad_aggressiveness = 3
min_utterance_ms = 250

[asr]
model_size = "medium"
device = "cpu"
beam_size = 5

[cleanup]
base_url = "http://example:1234"

[hotkey]
binding = "ctrl+shift+f9"
min_hold_ms = 42

[pipeline]
trigger_mode = "vad"
confidence_floor = 0.66
vad_coverage_floor = 0.3
force_paste_binding = "f11"
force_paste_window_ms = 999
force_paste_mode_ptt = "never"
force_paste_mode_vad = "listener"
ptt_open_per_trigger = true
dry_run = true
hardware_label = "wsl"
""",
        encoding="utf-8",
    )
    cfg = load_audio_dictate_config(toml_path)

    assert cfg.mic.sample_rate == 24000
    assert cfg.mic.vad_aggressiveness == 3
    assert cfg.mic.min_utterance_ms == 250
    assert cfg.asr.model_size == "medium"
    assert cfg.asr.device == "cpu"
    assert cfg.asr.beam_size == 5
    assert cfg.cleanup.base_url == "http://example:1234"
    assert cfg.hotkey.binding == "ctrl+shift+f9"
    assert cfg.hotkey.min_hold_ms == 42
    assert cfg.trigger_mode == "vad"
    # VAD trigger_mode auto-coerces hotkey.mode to toggle.
    assert cfg.hotkey.mode == "toggle"
    assert cfg.confidence_floor == 0.66
    assert cfg.vad_coverage_floor == 0.3
    assert cfg.force_paste_binding == "f11"
    assert cfg.force_paste_window_ms == 999
    assert cfg.force_paste_mode_ptt == "never"
    assert cfg.force_paste_mode_vad == "listener"
    assert cfg.ptt_open_per_trigger is True
    assert cfg.dry_run is True
    assert cfg.hardware_label == "wsl"


def test_duplicate_bindings_rejected() -> None:
    with pytest.raises(ValueError, match="must differ"):
        AudioDictateConfig(
            hotkey=HotkeyConfig(binding="f12"),
            force_paste_binding="F12",
        )


def test_trigger_mode_coerces_hotkey_mode(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        cfg = AudioDictateConfig(
            trigger_mode="vad",
            hotkey=HotkeyConfig(mode="push_to_talk", binding="ctrl+alt+v"),
        )
    assert cfg.hotkey.mode == "toggle"
    assert any(
        "auto-coercing hotkey.mode" in message for message in caplog.messages
    )

    cfg_ptt = AudioDictateConfig(
        trigger_mode="push_to_talk",
        hotkey=HotkeyConfig(mode="toggle", binding="ctrl+alt+p"),
    )
    assert cfg_ptt.hotkey.mode == "push_to_talk"


def test_ptt_preopens_mic_once_by_default(tmp_path: Path) -> None:
    cfg = _ptt_cfg(tmp_path)
    mic = FakeMicrophone()
    pipeline, bag = _build(cfg=cfg, mics=[mic])
    with pipeline as p:
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    assert mic.enter_count == 1, "mic should be preopened exactly once"
    assert mic.ptt_calls == 2
    assert mic.exit_count == 1


def test_ptt_open_per_trigger_opens_mic_per_call(tmp_path: Path) -> None:
    cfg = _ptt_cfg(tmp_path, ptt_open_per_trigger=True)
    mics = [FakeMicrophone(), FakeMicrophone()]
    pipeline, bag = _build(cfg=cfg, mics=list(mics))
    with pipeline as p:
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)
        _fire_ptt(bag["hotkey_factory"].primary, hold_ms=40)
        _drain_bus(bag["hotkey_factory"].primary.bus)
        _wait_dispatch(p)

    opened = [m for m in mics if m.enter_count == 1]
    assert len(opened) == 2, (
        f"expected 2 mic instances opened, got {[m.enter_count for m in mics]}"
    )
    for m in mics:
        assert m.ptt_calls == 1
        assert m.exit_count == 1
