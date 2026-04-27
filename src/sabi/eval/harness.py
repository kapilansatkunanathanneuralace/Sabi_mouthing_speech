"""Offline latency + WER evaluation harness (TICKET-014)."""

from __future__ import annotations

import importlib.util
import json
import math
import platform
import subprocess
import time
import wave
from collections import defaultdict
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

from sabi.capture.lip_roi import LipFrame, LipROIConfig, LipROIDetector
from sabi.capture.microphone import Utterance
from sabi.cleanup.ollama import (
    CleanedText,
    CleanupConfig,
    CleanupContext,
    PromptVersion,
    TextCleaner,
)
from sabi.fusion import FusionCombiner
from sabi.models.asr import ASRModel, ASRModelConfig, ASRResult
from sabi.models.latency import LATENCY_LOG, append_latency_row
from sabi.models.vsr.model import VSRModel, VSRModelConfig, VSRResult
from sabi.pipelines.audio_dictate import (
    AudioDictateConfig,
)
from sabi.pipelines.audio_dictate import (
    UtteranceProcessed as AudioUtteranceProcessed,
)
from sabi.pipelines.fused_dictate import (
    FusedDictateConfig,
)
from sabi.pipelines.fused_dictate import (
    UtteranceProcessed as FusedUtteranceProcessed,
)
from sabi.pipelines.silent_dictate import (
    SilentDictateConfig,
)
from sabi.pipelines.silent_dictate import (
    UtteranceProcessed as SilentUtteranceProcessed,
)

PipelineChoice = Literal["both", "silent", "audio", "fused"]
PipelineName = Literal["silent", "audio", "fused"]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
EVAL_INSTALL_MESSAGE = "Install eval dependencies with: pip install -e .[eval]"


class MissingEvalDependencyError(RuntimeError):
    """Raised when an optional eval dependency is unavailable."""


def require_eval_dependencies() -> None:
    """Validate optional eval extras for the CLI path."""

    missing = [
        name
        for name in ("jiwer", "pandas", "tabulate")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        joined = ", ".join(missing)
        raise MissingEvalDependencyError(
            f"Missing eval dependencies: {joined}. {EVAL_INSTALL_MESSAGE}"
        )


@dataclass(frozen=True)
class EvalConfig:
    dataset_path: Path
    runs: int = 3
    warmups: int = 1
    pipeline: PipelineChoice = "both"
    out_path: Path | None = None
    output_dir: Path = DEFAULT_REPORT_DIR
    hardware_label: str = "windows"
    latency_log_path: Path = LATENCY_LOG
    cleanup_prompts: tuple[PromptVersion, ...] = ("v1",)
    silent_config: SilentDictateConfig = field(default_factory=SilentDictateConfig)
    audio_config: AudioDictateConfig = field(default_factory=AudioDictateConfig)
    fused_config: FusedDictateConfig = field(default_factory=FusedDictateConfig)

    @property
    def selected_pipelines(self) -> tuple[PipelineName, ...]:
        if self.pipeline == "both":
            return ("silent", "audio")
        return (self.pipeline,)

    @property
    def report_path(self) -> Path:
        if self.out_path is not None:
            return self.out_path
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.output_dir / f"poc-eval-{stamp}.md"


@dataclass(frozen=True)
class EvalPhrase:
    id: str
    text: str
    video_path: Path | None = None
    audio_path: Path | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvalRecord:
    phrase: EvalPhrase
    pipeline: PipelineName
    run_index: int
    event: SilentUtteranceProcessed | AudioUtteranceProcessed | FusedUtteranceProcessed
    raw_wer: float
    cleaned_wer: float
    prompt_version: PromptVersion = "v1"


@dataclass(frozen=True)
class EvalResult:
    config: EvalConfig
    report_path: Path
    records: tuple[EvalRecord, ...]
    stage_stats: dict[tuple[str, str], dict[str, float]]
    summary_stats: dict[str, dict[str, float]]


def load_phrases(dataset_path: Path) -> list[EvalPhrase]:
    """Load ``phrases.jsonl`` from a dataset directory or JSONL file."""

    path = dataset_path if dataset_path.is_file() else dataset_path / "phrases.jsonl"
    base = path.parent
    if not path.is_file():
        raise FileNotFoundError(f"eval phrases file not found: {path}")
    phrases: list[EvalPhrase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        data = json.loads(line)
        phrase_id = str(data["id"])
        text = str(data["text"])
        phrases.append(
            EvalPhrase(
                id=phrase_id,
                text=text,
                video_path=_resolve_optional_path(base, data.get("video_path")),
                audio_path=_resolve_optional_path(base, data.get("audio_path")),
                tags=tuple(str(t) for t in data.get("tags", []) or []),
            )
        )
    if not phrases:
        raise ValueError(f"eval phrases file is empty: {path}")
    return phrases


def _resolve_optional_path(base: Path, value: object) -> Path | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else base / path


def load_video_frames(path: Path) -> list[tuple[int, np.ndarray]]:
    """Decode an mp4 into ``(timestamp_ns, frame_rgb)`` tuples."""

    if not path.is_file():
        raise FileNotFoundError(f"video clip not found: {path}")
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"could not open video clip: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    frames: list[tuple[int, np.ndarray]] = []
    idx = 0
    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            ts_ns = int((idx / max(fps, 1e-6)) * 1_000_000_000)
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            frames.append((ts_ns, frame_rgb))
            idx += 1
    finally:
        cap.release()
    if not frames:
        raise ValueError(f"video clip contains no frames: {path}")
    return frames


def load_wav_utterance(path: Path) -> Utterance:
    """Load a 16 kHz PCM wav into the audio pipeline's ``Utterance`` shape."""

    if not path.is_file():
        raise FileNotFoundError(f"audio clip not found: {path}")
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frame_count = wav.getnframes()
        payload = wav.readframes(frame_count)
    if sample_width != 2:
        raise ValueError(f"expected 16-bit PCM wav, got sample width {sample_width}")
    if sample_rate != 16000:
        raise ValueError(f"expected 16 kHz wav, got {sample_rate} Hz")
    raw = np.frombuffer(payload, dtype="<i2")
    if channels > 1:
        raw = raw.reshape(-1, channels).mean(axis=1).astype(np.int16)
    samples = (raw.astype(np.float32) / 32768.0).astype(np.float32)
    peak_dbfs, mean_dbfs = _compute_dbfs(samples)
    duration_ns = int(samples.shape[0] * 1_000_000_000 / max(sample_rate, 1))
    return Utterance(
        samples=samples,
        start_ts_ns=0,
        end_ts_ns=duration_ns,
        sample_rate=sample_rate,
        peak_dbfs=peak_dbfs,
        mean_dbfs=mean_dbfs,
        vad_coverage=1.0,
    )


def _compute_dbfs(samples: np.ndarray) -> tuple[float, float]:
    if samples.size == 0:
        return -math.inf, -math.inf
    abs_samples = np.abs(samples)
    peak = float(abs_samples.max())
    peak_db = 20.0 * math.log10(peak) if peak > 0 else -math.inf
    mean_sq = float(np.mean(samples.astype(np.float64) ** 2))
    mean_db = 10.0 * math.log10(mean_sq) if mean_sq > 0 else -math.inf
    return peak_db, mean_db


LipROIFactory = Callable[[LipROIConfig], AbstractContextManager[Any]]
VSRFactory = Callable[[VSRModelConfig], AbstractContextManager[Any]]
ASRFactory = Callable[[ASRModelConfig], AbstractContextManager[Any]]
CleanerFactory = Callable[[CleanupConfig], AbstractContextManager[Any]]


class SilentOfflineRunner:
    def __init__(
        self,
        config: SilentDictateConfig | None = None,
        *,
        lip_roi_factory: LipROIFactory | None = None,
        vsr_factory: VSRFactory | None = None,
        cleaner_factory: CleanerFactory | None = None,
        video_loader: Callable[[Path], list[tuple[int, np.ndarray]]] = load_video_frames,
    ) -> None:
        self.config = config or SilentDictateConfig(dry_run=True)
        self._lip_roi_factory = lip_roi_factory or (lambda cfg: LipROIDetector(cfg))
        self._vsr_factory = vsr_factory or (lambda cfg: VSRModel(cfg))
        self._cleaner_factory = cleaner_factory or (lambda cfg: TextCleaner(cfg))
        self._video_loader = video_loader
        self._utterance_counter = 0

    def run(self, phrase: EvalPhrase, run_index: int) -> SilentUtteranceProcessed:
        if phrase.video_path is None:
            raise FileNotFoundError(f"phrase {phrase.id} has no video_path")
        self._utterance_counter += 1
        utterance_id = self._utterance_counter
        started_at_ns = time.monotonic_ns()
        t0 = time.perf_counter()
        frames_rgb = self._video_loader(phrase.video_path)

        lip_frames: list[LipFrame] = []
        face_present = 0
        face_missing = 0
        roi_ms = 0.0
        with self._lip_roi_factory(self.config.lip_roi) as roi:
            for ts_ns, frame_rgb in frames_rgb:
                roi_t0 = time.perf_counter()
                lip = roi.process_frame(ts_ns, frame_rgb)
                roi_ms += (time.perf_counter() - roi_t0) * 1000.0
                if lip is None:
                    face_missing += 1
                else:
                    face_present += 1
                    lip_frames.append(lip)

        total_frames = face_present + face_missing
        face_ratio = (face_present / total_frames) if total_frames else 0.0
        capture_ms = _frame_capture_ms(frames_rgb)
        if not lip_frames:
            return self._silent_event(
                utterance_id,
                started_at_ns,
                t0,
                "",
                "",
                0.0,
                False,
                "withheld_empty",
                capture_ms,
                roi_ms,
                0.0,
                0.0,
                len(lip_frames),
                face_ratio,
                None,
            )
        if face_ratio < self.config.occlusion_threshold:
            return self._silent_event(
                utterance_id,
                started_at_ns,
                t0,
                "",
                "",
                0.0,
                False,
                "withheld_occluded",
                capture_ms,
                roi_ms,
                0.0,
                0.0,
                len(lip_frames),
                face_ratio,
                "camera could not see your mouth",
            )

        with self._vsr_factory(self.config.vsr) as vsr:
            vsr_result: VSRResult = vsr.predict(lip_frames)
        cleanup_ctx = CleanupContext(source="vsr", register_hint="dictation")
        with self._cleaner_factory(self.config.cleanup) as cleaner:
            cleaned: CleanedText = cleaner.cleanup(vsr_result.text, cleanup_ctx)
        decision = (
            "withheld_low_confidence"
            if vsr_result.confidence < self.config.confidence_floor
            else "dry_run"
        )
        return self._silent_event(
            utterance_id,
            started_at_ns,
            t0,
            vsr_result.text,
            cleaned.text,
            float(vsr_result.confidence),
            cleaned.used_fallback,
            decision,
            capture_ms,
            roi_ms,
            float(vsr_result.latency_ms),
            float(cleaned.latency_ms),
            len(lip_frames),
            face_ratio,
            None,
        )

    def _silent_event(
        self,
        utterance_id: int,
        started_at_ns: int,
        t0: float,
        text_raw: str,
        text_final: str,
        confidence: float,
        used_fallback: bool,
        decision: str,
        capture_ms: float,
        roi_ms: float,
        vsr_ms: float,
        cleanup_ms: float,
        frame_count: int,
        face_ratio: float,
        error: str | None,
    ) -> SilentUtteranceProcessed:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return SilentUtteranceProcessed(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            ended_at_ns=time.monotonic_ns(),
            text_raw=text_raw,
            text_final=text_final,
            confidence=confidence,
            used_fallback=used_fallback,
            decision=decision,  # type: ignore[arg-type]
            latencies={
                "capture_open_ms": 0.0,
                "capture_ms": capture_ms,
                "roi_ms": roi_ms,
                "vsr_ms": vsr_ms,
                "cleanup_ms": cleanup_ms,
                "inject_ms": 0.0,
                "total_ms": total_ms,
            },
            frame_count=frame_count,
            face_present_ratio=face_ratio,
            error=error,
        )


class AudioOfflineRunner:
    def __init__(
        self,
        config: AudioDictateConfig | None = None,
        *,
        asr_factory: ASRFactory | None = None,
        cleaner_factory: CleanerFactory | None = None,
        audio_loader: Callable[[Path], Utterance] = load_wav_utterance,
    ) -> None:
        self.config = config or AudioDictateConfig(dry_run=True)
        self._asr_factory = asr_factory or (lambda cfg: ASRModel(cfg))
        self._cleaner_factory = cleaner_factory or (lambda cfg: TextCleaner(cfg))
        self._audio_loader = audio_loader
        self._utterance_counter = 0

    def run(self, phrase: EvalPhrase, run_index: int) -> AudioUtteranceProcessed:
        if phrase.audio_path is None:
            raise FileNotFoundError(f"phrase {phrase.id} has no audio_path")
        self._utterance_counter += 1
        utterance_id = self._utterance_counter
        utt = self._audio_loader(phrase.audio_path)
        started_at_ns = int(utt.start_ts_ns)
        t0 = time.perf_counter()
        capture_ms = float(utt.duration_s) * 1000.0

        if utt.samples.size == 0 or utt.peak_dbfs <= self.config.asr.silence_peak_dbfs:
            return self._audio_event(
                utterance_id,
                started_at_ns,
                t0,
                "",
                "",
                0.0,
                False,
                "withheld_silence",
                capture_ms,
                0.0,
                0.0,
                utt,
                None,
            )

        with self._asr_factory(self.config.asr) as asr:
            asr_result: ASRResult = asr.transcribe(utt)
        if not asr_result.text.strip():
            return self._audio_event(
                utterance_id,
                started_at_ns,
                t0,
                asr_result.text,
                "",
                float(asr_result.confidence),
                False,
                "withheld_empty",
                capture_ms,
                float(asr_result.latency_ms),
                0.0,
                utt,
                None,
            )

        cleanup_ctx = CleanupContext(source="asr", register_hint="dictation")
        with self._cleaner_factory(self.config.cleanup) as cleaner:
            cleaned: CleanedText = cleaner.cleanup(asr_result.text, cleanup_ctx)
        decision = (
            "withheld_low_confidence"
            if asr_result.confidence < self.config.confidence_floor
            else "dry_run"
        )
        return self._audio_event(
            utterance_id,
            started_at_ns,
            t0,
            asr_result.text,
            cleaned.text,
            float(asr_result.confidence),
            cleaned.used_fallback,
            decision,
            capture_ms,
            float(asr_result.latency_ms),
            float(cleaned.latency_ms),
            utt,
            None,
        )

    def _audio_event(
        self,
        utterance_id: int,
        started_at_ns: int,
        t0: float,
        text_raw: str,
        text_final: str,
        confidence: float,
        used_fallback: bool,
        decision: str,
        capture_ms: float,
        asr_ms: float,
        cleanup_ms: float,
        utt: Utterance,
        error: str | None,
    ) -> AudioUtteranceProcessed:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return AudioUtteranceProcessed(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            ended_at_ns=time.monotonic_ns(),
            text_raw=text_raw,
            text_final=text_final,
            confidence=confidence,
            used_fallback=used_fallback,
            decision=decision,  # type: ignore[arg-type]
            latencies={
                "mic_open_ms": 0.0,
                "warmup_ms": 0.0,
                "capture_ms": capture_ms,
                "vad_ms": 0.0,
                "asr_ms": asr_ms,
                "cleanup_ms": cleanup_ms,
                "inject_ms": 0.0,
                "total_ms": total_ms,
            },
            duration_ms=capture_ms,
            vad_coverage=float(utt.vad_coverage),
            peak_dbfs=float(utt.peak_dbfs),
            trigger_mode=self.config.trigger_mode,
            error=error,
        )


class FusedOfflineRunner:
    def __init__(
        self,
        config: FusedDictateConfig | None = None,
        *,
        lip_roi_factory: LipROIFactory | None = None,
        vsr_factory: VSRFactory | None = None,
        asr_factory: ASRFactory | None = None,
        cleaner_factory: CleanerFactory | None = None,
        video_loader: Callable[[Path], list[tuple[int, np.ndarray]]] = load_video_frames,
        audio_loader: Callable[[Path], Utterance] = load_wav_utterance,
    ) -> None:
        self.config = config or FusedDictateConfig(dry_run=True)
        self._lip_roi_factory = lip_roi_factory or (lambda cfg: LipROIDetector(cfg))
        self._vsr_factory = vsr_factory or (lambda cfg: VSRModel(cfg))
        self._asr_factory = asr_factory or (lambda cfg: ASRModel(cfg))
        self._cleaner_factory = cleaner_factory or (lambda cfg: TextCleaner(cfg))
        self._video_loader = video_loader
        self._audio_loader = audio_loader
        self._combiner = FusionCombiner(self.config.fusion)
        self._utterance_counter = 0

    def run(self, phrase: EvalPhrase, run_index: int) -> FusedUtteranceProcessed:
        if phrase.video_path is None:
            raise FileNotFoundError(f"phrase {phrase.id} has no video_path")
        if phrase.audio_path is None:
            raise FileNotFoundError(f"phrase {phrase.id} has no audio_path")
        self._utterance_counter += 1
        utterance_id = self._utterance_counter
        started_at_ns = time.monotonic_ns()
        t0 = time.perf_counter()

        frames_rgb = self._video_loader(phrase.video_path)
        lip_frames: list[LipFrame] = []
        face_present = 0
        face_missing = 0
        roi_ms = 0.0
        with self._lip_roi_factory(self.config.lip_roi) as roi:
            for ts_ns, frame_rgb in frames_rgb:
                roi_t0 = time.perf_counter()
                lip = roi.process_frame(ts_ns, frame_rgb)
                roi_ms += (time.perf_counter() - roi_t0) * 1000.0
                if lip is None:
                    face_missing += 1
                else:
                    face_present += 1
                    lip_frames.append(lip)

        utt = self._audio_loader(phrase.audio_path)
        face_total = face_present + face_missing
        face_ratio = face_present / face_total if face_total else 0.0
        asr_silent = utt.samples.size == 0 or utt.peak_dbfs <= self.config.asr.silence_peak_dbfs
        vsr_no_face = not lip_frames or face_ratio < self.config.occlusion_threshold
        asr_result: ASRResult | None = None
        vsr_result: VSRResult | None = None
        asr_ms = 0.0
        vsr_ms = 0.0
        if not vsr_no_face:
            with self._vsr_factory(self.config.vsr) as vsr:
                vsr_result = vsr.predict(lip_frames)
                vsr_ms = float(vsr_result.latency_ms)
        if not asr_silent:
            with self._asr_factory(self.config.asr) as asr:
                asr_result = asr.transcribe(utt)
                asr_ms = float(asr_result.latency_ms)

        fused = self._combiner.combine(asr_result, vsr_result)
        if vsr_no_face and not asr_silent:
            from dataclasses import replace

            fused = replace(fused, mode_reason="vsr no-face")
        if asr_silent and not vsr_no_face:
            from dataclasses import replace

            fused = replace(fused, mode_reason="asr silent")
        if not fused.text.strip():
            cleaned = CleanedText(text="", latency_ms=0.0, used_fallback=False)
            decision = "error"
            error = "neither modality captured input"
        else:
            with self._cleaner_factory(self.config.cleanup) as cleaner:
                cleaned = cleaner.cleanup(
                    fused.text,
                    CleanupContext(source="fused", register_hint="dictation"),
                )
            decision = (
                "withheld_low_confidence"
                if fused.confidence < self.config.paste_floor_confidence
                else "dry_run"
            )
            error = None

        total_ms = (time.perf_counter() - t0) * 1000.0
        capture_ms = max(_frame_capture_ms(frames_rgb), float(utt.duration_s * 1000.0))
        latencies = {
            "capture_ms": capture_ms,
            "roi_ms": roi_ms,
            "vsr_ms": vsr_ms,
            "asr_ms": asr_ms,
            "fusion_ms": fused.latency_ms,
            "cleanup_ms": cleaned.latency_ms,
            "inject_ms": 0.0,
            "warmup_ms": 0.0,
            "capture_open_ms": 0.0,
            "mic_open_ms": 0.0,
            "total_ms": total_ms,
        }
        return FusedUtteranceProcessed(
            utterance_id=utterance_id,
            started_at_ns=started_at_ns,
            ended_at_ns=time.monotonic_ns(),
            text_raw=fused.text,
            text_final=cleaned.text,
            confidence=float(fused.confidence),
            used_fallback=cleaned.used_fallback,
            decision=decision,  # type: ignore[arg-type]
            latencies=latencies,
            fusion={
                "mode_used": fused.mode_used,
                "mode_reason": fused.mode_reason,
                "source_weights": fused.source_weights,
                "per_word_origin": fused.per_word_origin,
                "confidence": fused.confidence,
            },
            asr={
                "text": "" if asr_result is None else asr_result.text,
                "confidence": 0.0 if asr_result is None else asr_result.confidence,
                "latency_ms": asr_ms,
            },
            vsr={
                "text": "" if vsr_result is None else vsr_result.text,
                "confidence": 0.0 if vsr_result is None else vsr_result.confidence,
                "latency_ms": vsr_ms,
            },
            frame_count=len(lip_frames),
            face_present_ratio=face_ratio,
            duration_ms=float(utt.duration_s * 1000.0),
            vad_coverage=float(utt.vad_coverage),
            peak_dbfs=float(utt.peak_dbfs),
            error=error,
        )


def _frame_capture_ms(frames: list[tuple[int, np.ndarray]]) -> float:
    if len(frames) < 2:
        return 0.0
    return max(0.0, (frames[-1][0] - frames[0][0]) / 1_000_000.0)


def _with_cleanup_prompt(config: Any, prompt_version: PromptVersion) -> Any:
    cleanup = config.cleanup.model_copy(update={"prompt_version": prompt_version})
    return config.model_copy(update={"cleanup": cleanup})


def _runner_for_prompt(
    runner: Any | None,
    runner_cls: type,
    config: Any,
    prompt_version: PromptVersion,
) -> Any:
    prompt_config = _with_cleanup_prompt(config, prompt_version)
    if runner is None:
        return runner_cls(prompt_config)
    if hasattr(runner, "config"):
        runner.config = _with_cleanup_prompt(runner.config, prompt_version)
    return runner


def run_eval(
    config: EvalConfig,
    *,
    silent_runner: SilentOfflineRunner | None = None,
    audio_runner: AudioOfflineRunner | None = None,
    fused_runner: FusedOfflineRunner | None = None,
) -> EvalResult:
    """Run the offline evaluation and write report + latency summary rows."""

    started = time.perf_counter()
    phrases = load_phrases(config.dataset_path)
    records: list[EvalRecord] = []

    for prompt_version in config.cleanup_prompts:
        silent = _runner_for_prompt(
            silent_runner,
            SilentOfflineRunner,
            config.silent_config,
            prompt_version,
        )
        audio = _runner_for_prompt(
            audio_runner,
            AudioOfflineRunner,
            config.audio_config,
            prompt_version,
        )
        fused = _runner_for_prompt(
            fused_runner,
            FusedOfflineRunner,
            config.fused_config,
            prompt_version,
        )
        for phrase in phrases:
            for pipeline in config.selected_pipelines:
                if pipeline == "silent":
                    runner = silent
                elif pipeline == "audio":
                    runner = audio
                else:
                    runner = fused
                for warmup_idx in range(config.warmups):
                    runner.run(phrase, warmup_idx)
                for run_index in range(config.runs):
                    event = runner.run(phrase, run_index)
                    records.append(
                        EvalRecord(
                            phrase=phrase,
                            pipeline=pipeline,
                            run_index=run_index,
                            event=event,
                            raw_wer=compute_wer(phrase.text, event.text_raw),
                            cleaned_wer=compute_wer(phrase.text, event.text_final),
                            prompt_version=prompt_version,
                        )
                    )

    stage_stats = aggregate_stage_stats(records)
    summary_stats = aggregate_summary_stats(records)
    report_path = config.report_path
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    report = render_report(config, records, stage_stats, summary_stats, elapsed_ms=elapsed_ms)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    append_eval_latency_rows(config, stage_stats, records)
    return EvalResult(
        config=config,
        report_path=report_path,
        records=tuple(records),
        stage_stats=stage_stats,
        summary_stats=summary_stats,
    )


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute WER via jiwer when available, with a small local fallback."""

    try:
        from jiwer import wer

        return float(wer(reference, hypothesis))
    except Exception:
        ref = _normalize_words(reference)
        hyp = _normalize_words(hypothesis)
        if not ref:
            return 0.0 if not hyp else 1.0
        return _edit_distance(ref, hyp) / float(len(ref))


def _normalize_words(text: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return [w for w in cleaned.split() if w]


def _edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, aw in enumerate(a, start=1):
        cur = [i]
        for j, bw in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (aw != bw)))
        prev = cur
    return prev[-1]


def percentile_stats(values: Iterable[float]) -> dict[str, float]:
    vals = sorted(float(v) for v in values)
    if not vals:
        return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "p50": _percentile(vals, 0.50),
        "p90": _percentile(vals, 0.90),
        "p95": _percentile(vals, 0.95),
        "p99": _percentile(vals, 0.99),
        "max": max(vals),
    }


def _percentile(sorted_values: list[float], q: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[int(pos)]
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def aggregate_stage_stats(records: Iterable[EvalRecord]) -> dict[tuple[str, str], dict[str, float]]:
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    records = list(records)
    ab_mode = _has_prompt_ab(records)
    for rec in records:
        pipeline_label = _record_group_label(rec, ab_mode=ab_mode)
        for stage, value in rec.event.latencies.items():
            buckets[(pipeline_label, stage)].append(float(value))
    return {key: percentile_stats(values) for key, values in sorted(buckets.items())}


def aggregate_summary_stats(records: Iterable[EvalRecord]) -> dict[str, dict[str, float]]:
    records = list(records)
    ab_mode = _has_prompt_ab(records)
    grouped: dict[str, list[EvalRecord]] = defaultdict(list)
    for rec in records:
        grouped[_record_group_label(rec, ab_mode=ab_mode)].append(rec)
    out: dict[str, dict[str, float]] = {}
    for pipeline, items in grouped.items():
        total_stats = percentile_stats(r.event.latencies.get("total_ms", 0.0) for r in items)
        out[pipeline] = {
            "raw_wer": sum(r.raw_wer for r in items) / len(items),
            "cleaned_wer": sum(r.cleaned_wer for r in items) / len(items),
            **{f"total_{key}": value for key, value in total_stats.items()},
        }
    return out


def _has_prompt_ab(records: Iterable[EvalRecord]) -> bool:
    return len({rec.prompt_version for rec in records}) > 1


def _record_group_label(rec: EvalRecord, *, ab_mode: bool) -> str:
    if not ab_mode:
        return rec.pipeline
    return f"cleanup-{rec.prompt_version}"


def render_report(
    config: EvalConfig,
    records: list[EvalRecord],
    stage_stats: dict[tuple[str, str], dict[str, float]],
    summary_stats: dict[str, dict[str, float]],
    *,
    elapsed_ms: float,
) -> str:
    lines = [
        "# Sabi PoC Eval Report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Git SHA: {_git_sha()}",
        f"- Hardware: {_hardware_summary()}",
        f"- Ollama model: {config.audio_config.cleanup.model}",
        f"- VSR config: {config.silent_config.vsr.ini_path.name}",
        f"- ASR model: {config.audio_config.asr.model_size}",
        f"- Cleanup prompts: {', '.join(config.cleanup_prompts)}",
        f"- Runs per phrase: {config.runs}",
        f"- Warmups per phrase: {config.warmups}",
        f"- Total eval time: {elapsed_ms:.1f} ms",
        "",
        "## Summary",
        "",
        _summary_table(summary_stats),
        "",
        *(_prompt_comparison_section(records) if _has_prompt_ab(records) else []),
        "## Per-Stage Latency",
        "",
        _stage_table(stage_stats),
        "",
        "## Phrase Results",
        "",
        _phrase_table(records),
        "",
        "## Known Failure Modes",
        "",
        _failure_section(records),
        "",
    ]
    return "\n".join(lines)


def _summary_table(summary_stats: dict[str, dict[str, float]]) -> str:
    rows = []
    for pipeline, stats in sorted(summary_stats.items()):
        rows.append(
            [
                pipeline,
                f"{stats['raw_wer']:.3f}",
                f"{stats['cleaned_wer']:.3f}",
                f"{stats['total_p50']:.1f}",
                f"{stats['total_p95']:.1f}",
                f"{stats['total_max']:.1f}",
            ]
        )
    return _markdown_table(
        ["pipeline", "raw_wer", "cleaned_wer", "total_p50_ms", "total_p95_ms", "total_max_ms"],
        rows,
    )


def _stage_table(stage_stats: dict[tuple[str, str], dict[str, float]]) -> str:
    rows = []
    for (pipeline, stage), stats in sorted(stage_stats.items()):
        rows.append(
            [
                pipeline,
                stage,
                f"{stats['p50']:.1f}",
                f"{stats['p90']:.1f}",
                f"{stats['p95']:.1f}",
                f"{stats['p99']:.1f}",
                f"{stats['max']:.1f}",
            ]
        )
    return _markdown_table(["pipeline", "stage", "p50", "p90", "p95", "p99", "max"], rows)


def _phrase_table(records: list[EvalRecord]) -> str:
    if _has_prompt_ab(records):
        return _phrase_ab_table(records)
    rows = []
    for rec in records:
        rows.append(
            [
                rec.phrase.id,
                rec.pipeline,
                str(rec.run_index),
                _cell(rec.event.text_raw),
                _cell(rec.event.text_final),
                f"{rec.raw_wer:.3f}",
                f"{rec.cleaned_wer:.3f}",
                f"{rec.event.confidence:.2f}",
                f"{rec.event.latencies.get('total_ms', 0.0):.1f}",
                rec.event.decision,
            ]
        )
    return _markdown_table(
        [
            "id",
            "pipeline",
            "run",
            "raw_text",
            "cleaned_text",
            "raw_wer",
            "cleaned_wer",
            "confidence",
            "total_ms",
            "decision",
        ],
        rows,
    )


def _phrase_ab_table(records: list[EvalRecord]) -> str:
    grouped: dict[tuple[str, str, int], dict[str, EvalRecord]] = defaultdict(dict)
    for rec in records:
        grouped[(rec.phrase.id, rec.pipeline, rec.run_index)][rec.prompt_version] = rec
    rows = []
    for (phrase_id, pipeline, run_index), by_version in sorted(grouped.items()):
        v1 = by_version.get("v1")
        v2 = by_version.get("v2")
        base = v1 or v2
        assert base is not None
        raw_wer = base.raw_wer
        cleaned_v1 = v1.cleaned_wer if v1 is not None else None
        cleaned_v2 = v2.cleaned_wer if v2 is not None else None
        delta = (
            None
            if cleaned_v1 is None or cleaned_v2 is None
            else cleaned_v2 - cleaned_v1
        )
        rows.append(
            [
                phrase_id,
                pipeline,
                str(run_index),
                _cell(base.event.text_raw),
                _cell(v1.event.text_final if v1 is not None else ""),
                _cell(v2.event.text_final if v2 is not None else ""),
                f"{raw_wer:.3f}",
                "-" if cleaned_v1 is None else f"{cleaned_v1:.3f}",
                "-" if cleaned_v2 is None else f"{cleaned_v2:.3f}",
                "-" if delta is None else f"{delta:.3f}",
                f"{base.event.confidence:.2f}",
                f"{base.event.latencies.get('total_ms', 0.0):.1f}",
                base.event.decision,
            ]
        )
    return _markdown_table(
        [
            "id",
            "pipeline",
            "run",
            "raw_text",
            "cleaned_text_v1",
            "cleaned_text_v2",
            "raw_wer",
            "cleaned_wer_v1",
            "cleaned_wer_v2",
            "wer_delta_v2_minus_v1",
            "confidence",
            "total_ms",
            "decision",
        ],
        rows,
    )


def _prompt_comparison_section(records: list[EvalRecord]) -> list[str]:
    grouped: dict[tuple[str, str, int], dict[str, EvalRecord]] = defaultdict(dict)
    for rec in records:
        grouped[(rec.phrase.id, rec.pipeline, rec.run_index)][rec.prompt_version] = rec
    pairs = [(v["v1"], v["v2"]) for v in grouped.values() if "v1" in v and "v2" in v]
    if not pairs:
        verdict = "No paired v1/v2 records were available for comparison."
    else:
        v1_wer = sum(a.cleaned_wer for a, _ in pairs) / len(pairs)
        v2_wer = sum(b.cleaned_wer for _, b in pairs) / len(pairs)
        delta = v2_wer - v1_wer
        improved = sum(1 for a, b in pairs if b.cleaned_wer < a.cleaned_wer)
        v1_clean = [a.event.latencies.get("cleanup_ms", 0.0) for a, _ in pairs]
        v2_clean = [b.event.latencies.get("cleanup_ms", 0.0) for _, b in pairs]
        latency_delta = percentile_stats(v2_clean)["p50"] - percentile_stats(v1_clean)["p50"]
        verdict = (
            f"v2 changes aggregate cleaned WER by {delta:.3f} versus v1 "
            f"and improves {improved} of {len(pairs)} paired phrases; "
            f"median cleanup latency changes by {latency_delta:+.1f} ms."
        )
    return ["## Prompt Comparison", "", verdict, ""]


def _failure_section(records: list[EvalRecord]) -> str:
    failures = []
    for rec in records:
        event = rec.event
        if (
            event.error
            or event.decision not in {"dry_run", "pasted"}
            or event.used_fallback
            or event.confidence < 0.4
        ):
            reason = event.error or event.decision
            if event.used_fallback:
                reason += " cleanup: bypassed"
            failures.append(f"- {rec.phrase.id} / {rec.pipeline} / run {rec.run_index}: {reason}")
    if not failures:
        return "- None observed."
    return "\n".join(failures)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        rows = [["-" for _ in headers]]
    header = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_cell(str(cell)) for cell in row) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip() or "-"


def append_eval_latency_rows(
    config: EvalConfig,
    stage_stats: dict[tuple[str, str], dict[str, float]],
    records: list[EvalRecord],
) -> None:
    counts: dict[str, int] = defaultdict(int)
    for rec in records:
        counts[rec.pipeline] += 1
    for (pipeline, stage), stats in stage_stats.items():
        append_latency_row(
            "TICKET-014",
            config.hardware_label,
            f"{pipeline}:{stage}",
            stats["p50"],
            counts[pipeline],
            f"pipeline={pipeline} stage={stage}",
            p95_ms=stats["p95"],
            log_path=config.latency_log_path,
        )


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _hardware_summary() -> str:
    return f"{platform.system()} {platform.release()} / Python {platform.python_version()}"


__all__ = [
    "AudioOfflineRunner",
    "EVAL_INSTALL_MESSAGE",
    "EvalConfig",
    "EvalPhrase",
    "EvalRecord",
    "EvalResult",
    "FusedOfflineRunner",
    "MissingEvalDependencyError",
    "SilentOfflineRunner",
    "aggregate_stage_stats",
    "aggregate_summary_stats",
    "compute_wer",
    "load_phrases",
    "load_video_frames",
    "load_wav_utterance",
    "percentile_stats",
    "require_eval_dependencies",
    "run_eval",
]
