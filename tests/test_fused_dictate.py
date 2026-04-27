"""TICKET-017: fused dictation pipeline tests."""

from __future__ import annotations

import json
import math
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sabi.capture.lip_roi import LipFrame
from sabi.capture.microphone import Utterance
from sabi.cleanup.ollama import CleanedText
from sabi.fusion import FusedResult
from sabi.input.hotkey import HotkeyConfig, TriggerBus, TriggerEvent
from sabi.models.asr import ASRResult
from sabi.models.vsr.model import VSRResult
from sabi.output.inject import InjectConfig, InjectResult
from sabi.pipelines.fused_dictate import (
    FusedDictateConfig,
    FusedDictatePipeline,
    _Deps,
    load_fused_dictate_config,
)

LATENCY_KEYS = {
    "capture_ms",
    "roi_ms",
    "vsr_ms",
    "asr_ms",
    "fusion_ms",
    "cleanup_ms",
    "inject_ms",
    "warmup_ms",
    "capture_open_ms",
    "mic_open_ms",
    "total_ms",
}


class _Ctx(AbstractContextManager[Any]):
    def __init__(self, value: Any) -> None:
        self.value = value

    def __enter__(self) -> Any:
        return self.value

    def __exit__(self, *exc: Any) -> None:
        return None


class FakeWebcam:
    def __init__(self) -> None:
        self.frames = [
            (i, np.zeros((32, 32, 3), dtype=np.uint8)) for i in range(1, 8)
        ]
        self.idx = 0

    def get_latest(self, timeout: float | None = None) -> tuple[int, np.ndarray]:
        if self.idx < len(self.frames):
            item = self.frames[self.idx]
            self.idx += 1
            return item
        time.sleep(0.005)
        raise TimeoutError("no frame")


class FakeROI:
    def __init__(self, *, missing: bool = False) -> None:
        self.missing = missing

    def process_frame(self, ts_ns: int, _frame: np.ndarray) -> LipFrame | None:
        if self.missing:
            return None
        return LipFrame(
            timestamp_ns=ts_ns,
            crop=np.zeros((96, 96), dtype=np.uint8),
            confidence=0.9,
            face_present=True,
            bbox=(0, 0, 1, 1),
        )


class FakeVSR:
    def __init__(self, text: str = "hello world", confidence: float = 0.7) -> None:
        self.result = VSRResult(
            text=text,
            confidence=confidence,
            per_token_scores=None,
            latency_ms=12.0,
        )
        self.calls = 0

    def predict(self, frames: list[LipFrame]) -> VSRResult:
        assert frames
        self.calls += 1
        return self.result


class FakeASR:
    def __init__(self, text: str = "hello world", confidence: float = 0.8) -> None:
        self.result = ASRResult(text=text, confidence=confidence, latency_ms=18.0)
        self.calls = 0

    def transcribe(self, utt: Utterance) -> ASRResult:
        assert utt.samples.size > 0
        self.calls += 1
        return self.result


class FakeMic:
    def __init__(self, utterance: Utterance) -> None:
        self.utterance = utterance

    def push_to_talk_segment(self, start_event: Any, end_event: Any) -> Utterance:
        start_event.wait(timeout=1.0)
        end_event.wait(timeout=1.0)
        return self.utterance


class FakeCombiner:
    def __init__(self, result: FusedResult | None = None) -> None:
        self.result = result
        self.calls: list[tuple[ASRResult | None, VSRResult | None]] = []

    def combine(self, asr: ASRResult | None, vsr: VSRResult | None) -> FusedResult:
        self.calls.append((asr, vsr))
        if self.result is not None:
            return self.result
        if asr is None and vsr is None:
            return _fused("", 0.0, "auto", "both empty")
        if asr is None:
            return _fused(vsr.text, vsr.confidence, "vsr_primary", "asr silent")
        if vsr is None:
            return _fused(asr.text, asr.confidence, "audio_primary", "vsr no-face")
        return _fused("hello fused", 0.9, "audio_primary", "auto -> audio_primary")


class FakeCleaner:
    def __init__(self, used_fallback: bool = False, available: bool = True) -> None:
        self.used_fallback = used_fallback
        self.available = available
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return self.available

    def cleanup(self, text: str, _ctx: Any) -> CleanedText:
        self.calls.append(text)
        return CleanedText(text=text, latency_ms=5.0, used_fallback=self.used_fallback)


class FakePaste:
    def __init__(self) -> None:
        self.calls: list[tuple[str, InjectConfig]] = []

    def __call__(self, text: str, cfg: InjectConfig) -> InjectResult:
        self.calls.append((text, cfg))
        return InjectResult(text=text, length=len(text), latency_ms=3.0)


class FakeHotkey:
    def __init__(self, cfg: HotkeyConfig) -> None:
        self.cfg = cfg
        self.bus = TriggerBus()
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.bus.shutdown(timeout=0.2)


class HotkeyFactory:
    def __init__(self) -> None:
        self.primary: FakeHotkey | None = None
        self.force: FakeHotkey | None = None

    def __call__(self, cfg: HotkeyConfig) -> FakeHotkey:
        hk = FakeHotkey(cfg)
        if cfg.binding == "f12":
            self.force = hk
        else:
            self.primary = hk
        return hk


def _fused(
    text: str,
    confidence: float,
    mode: str = "audio_primary",
    reason: str = "test",
) -> FusedResult:
    words = text.split()
    return FusedResult(
        text=text,
        confidence=confidence,
        source_weights={"asr": 0.5, "vsr": 0.5} if words else {"asr": 0.0, "vsr": 0.0},
        per_word_origin=["both" for _ in words],
        per_word_confidence=[confidence for _ in words],
        mode_used=mode,  # type: ignore[arg-type]
        mode_reason=reason,
        latency_ms=0.25,
    )


def _utterance(*, silent: bool = False) -> Utterance:
    samples = (
        np.zeros(1600, dtype=np.float32)
        if silent
        else np.ones(1600, dtype=np.float32) * 0.1
    )
    return Utterance(
        samples=samples,
        start_ts_ns=0,
        end_ts_ns=100_000_000,
        sample_rate=16000,
        peak_dbfs=-math.inf if silent else -20.0,
        mean_dbfs=-math.inf if silent else -30.0,
        vad_coverage=0.0 if silent else 1.0,
    )


def _build(
    tmp_path: Path,
    *,
    cfg: FusedDictateConfig | None = None,
    roi: FakeROI | None = None,
    mic: FakeMic | None = None,
    combiner: FakeCombiner | None = None,
    cleaner: FakeCleaner | None = None,
) -> tuple[FusedDictatePipeline, dict[str, Any]]:
    cfg = cfg or FusedDictateConfig(jsonl_dir=tmp_path, force_paste_mode_fused="never")
    hotkeys = HotkeyFactory()
    paste = FakePaste()
    latency_rows: list[tuple[Any, ...]] = []
    fake_roi = roi or FakeROI()
    fake_mic = mic or FakeMic(_utterance())
    fake_combiner = combiner or FakeCombiner()
    fake_cleaner = cleaner or FakeCleaner()
    deps = _Deps(
        webcam_factory=lambda _cfg: _Ctx(FakeWebcam()),
        roi_factory=lambda _cfg: _Ctx(fake_roi),
        vsr_factory=lambda _cfg: _Ctx(FakeVSR()),
        mic_factory=lambda _cfg: _Ctx(fake_mic),
        asr_factory=lambda _cfg: _Ctx(FakeASR()),
        combiner_factory=lambda _cfg: fake_combiner,
        cleaner_factory=lambda _cfg: _Ctx(fake_cleaner),
        hotkey_factory=hotkeys,
        paste_fn=paste,
        latency_writer=lambda *row, **_kw: latency_rows.append(row),
    )
    return FusedDictatePipeline(cfg, deps=deps), {
        "hotkeys": hotkeys,
        "paste": paste,
        "latency_rows": latency_rows,
        "combiner": fake_combiner,
        "cleaner": fake_cleaner,
    }


def _fire_ptt(hk: FakeHotkey) -> None:
    start = TriggerEvent(trigger_id=1, mode="push_to_talk", started_at_ns=time.monotonic_ns())
    hk.bus.emit_start(start)
    time.sleep(0.06)
    hk.bus.emit_stop(start)
    time.sleep(0.1)


def _fire_force(hk: FakeHotkey) -> None:
    hk.bus.emit_start(
        TriggerEvent(trigger_id=2, mode="push_to_talk", started_at_ns=time.monotonic_ns())
    )
    time.sleep(0.1)


def _wait_event(events: list[Any], count: int = 1) -> None:
    deadline = time.time() + 2.0
    while len(events) < count and time.time() < deadline:
        time.sleep(0.02)


def _jsonl(tmp_path: Path) -> list[dict[str, Any]]:
    files = list(tmp_path.glob("fused_dictate_*.jsonl"))
    assert files
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_happy_path_pastes_fused_text_and_logs(tmp_path: Path) -> None:
    pipeline, bag = _build(tmp_path)
    events = []
    statuses = []
    with pipeline as p:
        p.subscribe(events.append)
        p.subscribe_status(statuses.append)
        _fire_ptt(bag["hotkeys"].primary)
        _wait_event(events)

    assert events[0].pipeline == "fused"
    assert events[0].decision == "pasted"
    assert events[0].text_final == "hello fused"
    assert set(events[0].latencies) == LATENCY_KEYS
    assert bag["paste"].calls[0][0] == "hello fused"
    assert bag["latency_rows"][0][0] == "TICKET-017"
    rows = _jsonl(tmp_path)
    processed = [r for r in rows if r["event_type"] == "utterance_processed"][0]
    assert processed["pipeline"] == "fused"
    assert processed["cleanup"]["prompt_version"] == "v1"
    assert {"fusion", "asr", "vsr"} <= set(processed)
    assert {"recording", "decoding", "cleaning", "pasting", "idle"} <= {s.mode for s in statuses}


def test_vsr_no_face_pastes_asr_verbatim(tmp_path: Path) -> None:
    pipeline, bag = _build(tmp_path, roi=FakeROI(missing=True))
    events = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkeys"].primary)
        _wait_event(events)

    assert events[0].text_final == "hello world"
    assert events[0].fusion["mode_reason"] == "vsr no-face"
    assert bag["combiner"].calls[0][1] is None


def test_asr_silent_pastes_vsr_verbatim(tmp_path: Path) -> None:
    pipeline, bag = _build(tmp_path, mic=FakeMic(_utterance(silent=True)))
    events = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkeys"].primary)
        _wait_event(events)

    assert events[0].text_final == "hello world"
    assert events[0].fusion["mode_reason"] == "asr silent"
    assert bag["combiner"].calls[0][0] is None


def test_both_empty_emits_pipeline_error_without_paste(tmp_path: Path) -> None:
    pipeline, bag = _build(
        tmp_path,
        roi=FakeROI(missing=True),
        mic=FakeMic(_utterance(silent=True)),
    )
    events = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkeys"].primary)
        _wait_event(events)

    assert events[0].decision == "error"
    assert events[0].error == "neither modality captured input"
    assert bag["paste"].calls == []
    assert any(r["event_type"] == "pipeline_error" for r in _jsonl(tmp_path))


def test_force_paste_listener_pastes_after_f12(tmp_path: Path) -> None:
    cfg = FusedDictateConfig(
        jsonl_dir=tmp_path,
        paste_floor_confidence=0.8,
        force_paste_mode_fused="listener",
        force_paste_window_ms=1000,
    )
    pipeline, bag = _build(tmp_path, cfg=cfg, combiner=FakeCombiner(_fused("maybe text", 0.2)))
    events = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkeys"].primary)
        assert bag["paste"].calls == []
        _fire_force(bag["hotkeys"].force)
        _wait_event(events)

    assert events[0].decision == "force_pasted"
    assert bag["paste"].calls[0][0] == "maybe text"
    assert any(r["event_type"] == "force_paste_hit" for r in _jsonl(tmp_path))


def test_ollama_fallback_still_pastes(tmp_path: Path) -> None:
    pipeline, bag = _build(tmp_path, cleaner=FakeCleaner(used_fallback=True, available=False))
    events = []
    with pipeline as p:
        p.subscribe(events.append)
        _fire_ptt(bag["hotkeys"].primary)
        _wait_event(events)

    assert events[0].used_fallback is True
    assert bag["paste"].calls[0][0] == events[0].text_final


def test_config_rejects_duplicate_bindings(tmp_path: Path) -> None:
    path = tmp_path / "fused.toml"
    path.write_text(
        "[hotkey]\nbinding = 'f12'\n[pipeline]\nforce_paste_binding = 'f12'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must differ"):
        load_fused_dictate_config(path)
