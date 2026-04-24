"""``sabi asr-smoke`` helper (TICKET-007).

Loads a wav file (16 kHz mono, int16 or float), feeds it through
:class:`ASRModel`, prints the transcript + latency, and appends one row
to ``reports/latency-log.md`` with ``stage=asr``. Optionally computes WER
against a sibling ``.txt`` ground truth when ``jiwer`` is installed.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import torch
from scipy.io import wavfile

from sabi.capture.microphone import Utterance
from sabi.models.asr import ASRModel, ASRModelConfig, ASRResult
from sabi.models.latency import append_latency_row

logger = logging.getLogger(__name__)


def _load_wav_mono_16k(path: Path) -> np.ndarray:
    """Return a ``float32`` mono buffer. Raises if the wav is not 16 kHz mono."""
    sr, data = wavfile.read(str(path))
    if sr != 16000:
        raise ValueError(
            f"{path.name}: expected 16 kHz sample rate, got {sr}. "
            "Re-encode with e.g. ffmpeg -i in.wav -ar 16000 -ac 1 out.wav.",
        )
    if data.ndim > 1:
        if data.shape[1] != 1:
            raise ValueError(
                f"{path.name}: expected mono audio, got {data.shape[1]} channels.",
            )
        data = data[:, 0]
    if data.dtype == np.int16:
        samples = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        samples = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        samples = (data.astype(np.float32) - 128.0) / 128.0
    elif data.dtype in (np.float32, np.float64):
        samples = data.astype(np.float32, copy=False)
    else:
        raise ValueError(f"unsupported wav dtype: {data.dtype}")
    return np.ascontiguousarray(samples, dtype=np.float32)


def _compute_dbfs(samples: np.ndarray) -> tuple[float, float]:
    if samples.size == 0:
        return (-math.inf, -math.inf)
    abs_samples = np.abs(samples)
    peak_lin = float(abs_samples.max())
    peak_db = 20.0 * math.log10(peak_lin) if peak_lin > 0 else -math.inf
    mean_sq = float(np.mean(samples.astype(np.float64) ** 2))
    mean_db = 10.0 * math.log10(mean_sq) if mean_sq > 0 else -math.inf
    return peak_db, mean_db


def _utterance_from_samples(samples: np.ndarray, sample_rate: int = 16000) -> Utterance:
    peak_db, mean_db = _compute_dbfs(samples)
    duration_ns = int(samples.shape[0] * 1e9 / max(sample_rate, 1))
    return Utterance(
        samples=samples,
        start_ts_ns=0,
        end_ts_ns=duration_ns,
        sample_rate=sample_rate,
        peak_dbfs=peak_db,
        mean_dbfs=mean_db,
        vad_coverage=1.0,
    )


def _wer(reference: str, hypothesis: str) -> float | None:
    try:
        import jiwer
    except ModuleNotFoundError:
        logger.info("jiwer not installed; skipping WER computation")
        return None
    return float(jiwer.wer(reference, hypothesis))


def run_asr_smoke(
    wav_path: Path,
    asr_config: ASRModelConfig,
    wer_gate: float | None = 0.10,
    warmup: bool = True,
    latency_gate_ms: float | None = None,
) -> ASRResult:
    """End-to-end smoke: load wav, run ASR, log latency, compute optional WER.

    ``wer_gate`` and ``latency_gate_ms`` are informational - we log but do
    not raise so the smoke still produces a latency row even on regressions
    (same policy as :func:`sabi.models.vsr.smoke.run_vsr_smoke`).
    """
    samples = _load_wav_mono_16k(wav_path)
    utterance = _utterance_from_samples(samples, sample_rate=asr_config.sample_rate)
    logger.info(
        "loaded %s: %d samples (%.2f s), peak=%.1f dBFS",
        wav_path,
        samples.shape[0],
        utterance.duration_s,
        utterance.peak_dbfs,
    )

    with ASRModel(asr_config) as model:
        warmup_ms: float | None = None
        if warmup:
            warm_result = model.warm_up()
            warmup_ms = warm_result.latency_ms
            logger.info("warm_up complete (%.1f ms)", warmup_ms)

        result = model.transcribe(utterance)

    hardware = "cuda" if torch.cuda.is_available() else "cpu"
    notes = (
        f"wav={wav_path.name} lang={result.language} "
        f"cp={model.compute_type or 'auto'} "
        f"conf={result.confidence:.2f}"
    )
    if warmup_ms is not None:
        notes += f" warmup_ms={warmup_ms:.1f}"
    append_latency_row(
        "TICKET-007",
        hardware,
        "asr",
        result.latency_ms,
        samples.shape[0],
        notes,
    )

    print(f"text     : {result.text!r}")
    print(f"segments : {len(result.segments)}")
    if result.per_word_confidence:
        print(f"words    : {len(result.per_word_confidence)}")
    print(
        f"latency  : {result.latency_ms:.1f} ms ({hardware}, "
        f"compute_type={model.compute_type})",
    )
    print(f"conf     : {result.confidence:.3f} (avg_logprob={result.avg_logprob:.3f})")

    if warmup_ms is not None and result.latency_ms > 0:
        steady = result.latency_ms
        delta_ratio = abs(warmup_ms - steady) / steady
        print(f"warmup   : {warmup_ms:.1f} ms (delta={delta_ratio * 100:.0f}%)")
        if delta_ratio > 0.20:
            logger.warning(
                "warmup latency (%.1f ms) differs from steady-state (%.1f ms) "
                "by more than 20%%; first-call JIT overhead may still be present.",
                warmup_ms,
                steady,
            )

    if latency_gate_ms is not None and result.latency_ms > latency_gate_ms:
        logger.warning(
            "ASR latency %.1f ms exceeds gate %.1f ms (%s).",
            result.latency_ms,
            latency_gate_ms,
            hardware,
        )

    ref_path = wav_path.with_suffix(".txt")
    if ref_path.is_file():
        reference = ref_path.read_text(encoding="utf-8").strip()
        wer = _wer(reference, result.text)
        if wer is not None:
            print(f"reference: {reference!r}")
            print(f"WER      : {wer * 100:.1f}%")
            if wer_gate is not None and wer > wer_gate:
                logger.warning(
                    "WER %.1f%% exceeds acceptance gate %.0f%%",
                    wer * 100,
                    wer_gate * 100,
                )

    return result


__all__ = ["run_asr_smoke"]
