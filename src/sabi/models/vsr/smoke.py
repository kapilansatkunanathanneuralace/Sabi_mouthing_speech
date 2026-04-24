"""``sabi vsr-smoke`` helper (TICKET-005).

Runs the TICKET-004 lip detector over a recorded video, feeds the crops to
:class:`VSRModel`, prints the transcript + latency, and appends one line to
``reports/latency-log.md``. Optionally computes word error rate against a
ground-truth ``.txt`` sitting next to the video when ``jiwer`` is installed.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from sabi.capture.lip_roi import LipROIConfig, LipROIDetector
from sabi.models.latency import append_latency_row
from sabi.models.vsr.model import VSRModel, VSRModelConfig, VSRResult

logger = logging.getLogger(__name__)


def _decode_lip_frames(
    video_path: Path,
    lip_config: LipROIConfig,
) -> tuple[list[np.ndarray], float]:
    """Return (crops, fps). Skips frames without a detected face."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    crops: list[np.ndarray] = []
    try:
        with LipROIDetector(lip_config) as detector:
            index = 0
            while True:
                ok, frame_bgr = cap.read()
                if not ok:
                    break
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                ts_ns = int(index * 1_000_000_000 / max(fps, 1e-3))
                result = detector.process_frame(ts_ns, frame_rgb)
                if result is not None:
                    crops.append(result.crop)
                index += 1
    finally:
        cap.release()
    return crops, float(fps)


def _wer(reference: str, hypothesis: str) -> float | None:
    try:
        import jiwer
    except ModuleNotFoundError:
        logger.info("jiwer not installed; skipping WER computation")
        return None
    return float(jiwer.wer(reference, hypothesis))


def run_vsr_smoke(
    video_path: Path,
    vsr_config: VSRModelConfig,
    lip_config: LipROIConfig,
    wer_gate: float | None = 0.30,
) -> VSRResult:
    """End-to-end smoke: decode, run VSR, log latency, compute optional WER.

    ``wer_gate`` is informational; we log and ``return`` the result either way
    so the caller decides whether to fail-hard. When the sibling ``.txt``
    ground truth is missing, WER is skipped silently.
    """
    if not torch.cuda.is_available():
        logger.warning(
            "torch.cuda.is_available() is False; Chaplin VSR will run on CPU and "
            "miss the 200 ms roadmap budget by a wide margin."
        )

    logger.info("decoding %s", video_path)
    t0 = time.monotonic()
    crops, fps = _decode_lip_frames(video_path, lip_config)
    decode_ms = (time.monotonic() - t0) * 1000.0
    logger.info("decoded %d lip crops in %.1f ms (video fps=%.2f)", len(crops), decode_ms, fps)
    if not crops:
        raise RuntimeError(f"no face detected in {video_path}")

    with VSRModel(vsr_config) as vsr:
        result = vsr.predict(crops)

    hardware = "cuda" if torch.cuda.is_available() else "cpu"
    notes = f"video={video_path.name} fps={fps:.1f}"
    append_latency_row(
        "TICKET-005",
        hardware,
        "vsr-smoke",
        result.latency_ms,
        len(crops),
        notes,
    )

    print(f"text     : {result.text!r}")
    print(f"frames   : {len(crops)}")
    print(f"latency  : {result.latency_ms:.1f} ms ({hardware})")

    ref_path = video_path.with_suffix(".txt")
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
