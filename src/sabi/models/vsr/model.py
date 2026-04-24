"""Chaplin / Auto-AVSR VSR wrapper (TICKET-005).

Responsibilities:

* Validate incoming lip crops against the TICKET-004 contract
  (96x96 ``uint8`` grayscale, ``ndim == 2``).
* Apply Chaplin's exact ``VideoTransform`` pipeline (``/255`` -> centre crop 88
  -> ``Normalize(0.421, 0.165)``) before calling ``AVSR.infer``.
* Lazy-load the vendored ``AVSR`` on first ``predict`` so unit tests and CLI
  help do not pay the cost of instantiating the transformer stack.
* Rewrite Chaplin's ``LRS3_V_WER19.1.ini`` to use absolute weight paths, so
  ``ConfigParser`` inside Chaplin always finds the files no matter what the
  current working directory is.
"""

from __future__ import annotations

import logging
import tempfile
import time
import tomllib
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Iterator, Literal

import numpy as np
from pydantic import BaseModel, Field

from sabi.models.vsr._chaplin_path import DEFAULT_INI, ensure_on_path
from sabi.models.vsr.constants import (
    CENTER_CROP,
    LIP_H,
    LIP_W,
    LRS3_MEAN,
    LRS3_STD,
    TARGET_V_FPS,
)
from sabi.models.vsr.download import DEFAULT_DEST_ROOT as DEFAULT_WEIGHTS_ROOT
from sabi.models.vsr.download import DEFAULT_MANIFEST

if TYPE_CHECKING:  # pragma: no cover - import for type hints only
    from sabi.capture.lip_roi import LipFrame

logger = logging.getLogger(__name__)

Device = Literal["auto", "cuda", "cpu"]
Precision = Literal["fp16", "fp32"]


class VSRInputError(ValueError):
    """Raised when ``predict`` receives frames that violate the LipFrame contract."""


class VSRModelConfig(BaseModel):
    """Configuration for :class:`VSRModel`.

    Defaults line up with Chaplin's ``configs/LRS3_V_WER19.1.ini``.
    """

    ini_path: Path = Field(
        default_factory=lambda: DEFAULT_INI,
        description="Chaplin ini (LRS3_V_WER19.1.ini) to parse for model + decode params.",
    )
    weights_root: Path = Field(
        default_factory=lambda: DEFAULT_WEIGHTS_ROOT,
        description="Where downloaded weights live (see scripts/download_vsr_weights.py).",
    )
    manifest_path: Path = Field(
        default_factory=lambda: DEFAULT_MANIFEST,
        description="TOML manifest used to map ini keys -> weights_root files.",
    )
    device: Device = "auto"
    precision: Precision = "fp32"
    max_frames: int = Field(default=300, ge=1, description="Safety cap per predict() call.")
    input_fps: float = Field(
        default=float(TARGET_V_FPS),
        gt=0,
        description="FPS of the incoming lip stream (TICKET-004 default is 25).",
    )

    model_config = {"arbitrary_types_allowed": True}


@dataclass(frozen=True)
class VSRResult:
    """Single-utterance prediction from :meth:`VSRModel.predict`."""

    text: str
    confidence: float
    per_token_scores: tuple[float, ...] | None
    latency_ms: float


# Map manifest `name` -> (section, key) inside Chaplin's ini.
_MANIFEST_TO_INI: dict[str, tuple[str, str]] = {
    "vsr_model": ("model", "model_path"),
    "vsr_model_conf": ("model", "model_conf"),
    "lm_model": ("model", "rnnlm"),
    "lm_model_conf": ("model", "rnnlm_conf"),
}


def _resolve_device(requested: Device) -> str:
    import torch

    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("device='cuda' requested but torch.cuda.is_available() is False")
        return "cuda:0"
    if torch.cuda.is_available():
        return "cuda:0"
    logger.warning(
        "CUDA not available; Chaplin VSR will run on CPU (well above the 200 ms budget)."
    )
    return "cpu"


def _load_manifest(path: Path) -> dict[str, dict]:
    """Return ``{name: entry}`` dict for manifest ``[[files]]`` entries."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    return {entry["name"]: entry for entry in data.get("files", [])}


def _build_runtime_ini(
    ini_path: Path,
    manifest_path: Path,
    weights_root: Path,
) -> Path:
    """Copy the Chaplin ini, rewriting model paths to absolute paths.

    Chaplin's :class:`ConfigParser` reads paths verbatim, so if we simply pass
    its upstream ini, it resolves them relative to the current working
    directory. We produce a temp ini with absolute paths so inference works
    regardless of CWD.
    """
    config = ConfigParser()
    if not ini_path.is_file():
        raise FileNotFoundError(f"Chaplin ini not found: {ini_path}")
    config.read(ini_path)
    manifest = _load_manifest(manifest_path)
    for name, (section, key) in _MANIFEST_TO_INI.items():
        entry = manifest.get(name)
        if entry is None or not config.has_option(section, key):
            continue
        abs_path = (weights_root / entry["relative_path"]).resolve()
        if not abs_path.is_file():
            raise FileNotFoundError(
                f"weight '{name}' missing at {abs_path}. Run `python -m sabi download-vsr`."
            )
        config.set(section, key, str(abs_path))

    tmp = Path(tempfile.mkstemp(prefix="sabi_vsr_", suffix=".ini")[1])
    with tmp.open("w", encoding="utf-8") as f:
        config.write(f)
    return tmp


def _stack_frames(frames: list[np.ndarray]) -> np.ndarray:
    """Validate + stack a list of lip crops into an ``(T, 96, 96) uint8`` array."""
    if not frames:
        raise VSRInputError("predict() received zero lip frames")
    for i, frame in enumerate(frames):
        if not isinstance(frame, np.ndarray):
            raise VSRInputError(f"frame {i} is {type(frame).__name__}, expected np.ndarray")
        if frame.dtype != np.uint8:
            raise VSRInputError(f"frame {i} dtype={frame.dtype}, expected uint8")
        if frame.ndim != 2:
            raise VSRInputError(
                f"frame {i} has shape {frame.shape}; expected 2-D grayscale (H, W). "
                "Did you forget to set LipROIConfig(grayscale=True)?"
            )
        if frame.shape != (LIP_H, LIP_W):
            raise VSRInputError(f"frame {i} shape {frame.shape} != expected ({LIP_H}, {LIP_W})")
    return np.stack(frames, axis=0)


class VSRModel:
    """High-level VSR wrapper over Chaplin's :class:`AVSR` (TICKET-005).

    Use as a context manager so the underlying torch model is loaded once per
    session and released on exit::

        with VSRModel(VSRModelConfig()) as vsr:
            result = vsr.predict(frames)
    """

    def __init__(self, config: VSRModelConfig | None = None) -> None:
        self._config = config or VSRModelConfig()
        self._avsr = None  # populated on first predict()
        self._device: str | None = None
        self._speed_rate: float = 1.0
        self._video_transform = None
        self._runtime_ini: Path | None = None

    @property
    def config(self) -> VSRModelConfig:
        return self._config

    @property
    def device(self) -> str | None:
        return self._device

    def __enter__(self) -> VSRModel:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def close(self) -> None:
        self._avsr = None
        self._video_transform = None
        if self._runtime_ini is not None and self._runtime_ini.exists():
            try:
                self._runtime_ini.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass
        self._runtime_ini = None

    def _ensure_loaded(self) -> None:
        if self._avsr is not None:
            return
        ensure_on_path()
        import torch
        from pipelines.data.transforms import VideoTransform  # type: ignore[import-not-found]
        from pipelines.model import AVSR  # type: ignore[import-not-found]

        self._device = _resolve_device(self._config.device)

        runtime_ini = _build_runtime_ini(
            self._config.ini_path,
            self._config.manifest_path,
            self._config.weights_root,
        )
        self._runtime_ini = runtime_ini

        parser = ConfigParser()
        parser.read(runtime_ini)
        modality = parser.get("input", "modality")
        input_fps = parser.getfloat("input", "v_fps")
        model_fps = parser.getfloat("model", "v_fps")
        self._speed_rate = input_fps / model_fps if model_fps else 1.0

        self._avsr = AVSR(
            modality=modality,
            model_path=parser.get("model", "model_path"),
            model_conf=parser.get("model", "model_conf"),
            rnnlm=parser.get("model", "rnnlm") or None,
            rnnlm_conf=parser.get("model", "rnnlm_conf") or None,
            penalty=parser.getfloat("decode", "penalty"),
            ctc_weight=parser.getfloat("decode", "ctc_weight"),
            lm_weight=parser.getfloat("decode", "lm_weight"),
            beam_size=parser.getint("decode", "beam_size"),
            device=self._device,
        )
        self._video_transform = VideoTransform(speed_rate=self._speed_rate)
        _ = torch  # keep the module imported for predict()

    def _preprocess(self, stacked: np.ndarray):
        """Replicate Chaplin's VideoTransform on a ``(T, 96, 96)`` uint8 stack."""
        import torch

        tensor = torch.from_numpy(stacked)  # uint8 (T, H, W)
        assert self._video_transform is not None
        return self._video_transform(tensor)  # -> float (1, T, 88, 88)

    def predict(self, frames: Iterable["LipFrame | np.ndarray"]) -> VSRResult:
        """Run VSR on a single utterance and return a :class:`VSRResult`.

        Accepts either :class:`sabi.capture.lip_roi.LipFrame` instances or raw
        ``np.ndarray`` crops so tests and smoke utilities do not have to build
        the dataclass just to call ``predict``.
        """
        frames_list: list[np.ndarray] = []
        for item in frames:
            if isinstance(item, np.ndarray):
                frames_list.append(item)
            elif hasattr(item, "crop"):
                frames_list.append(item.crop)
            else:
                raise VSRInputError(
                    f"predict() got unsupported element type: {type(item).__name__}"
                )
        if len(frames_list) > self._config.max_frames:
            raise VSRInputError(
                f"predict() received {len(frames_list)} frames > "
                f"max_frames={self._config.max_frames}"
            )
        stacked = _stack_frames(frames_list)

        self._ensure_loaded()
        assert self._avsr is not None

        import torch

        data = self._preprocess(stacked)
        start = time.monotonic()
        with torch.inference_mode():
            use_autocast = self._config.precision == "fp16" and self._device != "cpu"
            if use_autocast:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    text = self._avsr.infer(data)
            else:
                text = self._avsr.infer(data)
        latency_ms = (time.monotonic() - start) * 1000.0

        confidence = 1.0 if text else 0.0
        return VSRResult(
            text=text or "",
            confidence=float(confidence),
            per_token_scores=None,
            latency_ms=float(latency_ms),
        )

    def predict_streaming(
        self,
        batches: Iterable[Iterable["LipFrame | np.ndarray"]],
    ) -> Iterator[VSRResult]:
        """Thin wrapper: one :meth:`predict` per utterance-sized batch.

        Utterance boundary detection is the caller's responsibility per
        TICKET-011; this method exists so downstream code can stay ergonomic
        when it already knows the boundaries.
        """
        for batch in batches:
            yield self.predict(batch)


__all__ = [
    "VSRInputError",
    "VSRModel",
    "VSRModelConfig",
    "VSRResult",
    "LIP_H",
    "LIP_W",
    "CENTER_CROP",
    "LRS3_MEAN",
    "LRS3_STD",
]
