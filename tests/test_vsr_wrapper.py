"""TICKET-005: VSRModel wrapper tests (no real Chaplin import, no weights).

All tests monkeypatch the Chaplin entry points (:class:`AVSR`,
``VideoTransform``) and the runtime-ini + path helpers so they exercise the
wrapper logic without cloning models or touching CUDA. An optional integration
test gated on ``CHAPLIN_INTEGRATION=1`` is intentionally omitted here to keep
CI fast; enable it alongside weight downloads when needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sabi.models.vsr import model as vsr_model
from sabi.models.vsr.model import (
    VSRInputError,
    VSRModel,
    VSRModelConfig,
    VSRResult,
)


class _FakeAVSR:
    """Stands in for Chaplin's ``pipelines.model.AVSR``."""

    last_instance: "_FakeAVSR | None" = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[Any] = []
        self.transcript = "hello world"
        _FakeAVSR.last_instance = self

    def infer(self, data: Any) -> str:
        self.calls.append(data)
        return self.transcript


class _FakeVideoTransform:
    """Stand-in for Chaplin's ``VideoTransform`` - records input shape and speed rate."""

    def __init__(self, speed_rate: float = 1.0) -> None:
        self.speed_rate = speed_rate

    def __call__(self, tensor: Any) -> Any:
        self.last_input_shape = tuple(tensor.shape)
        return tensor  # passthrough is fine for the fake AVSR


@pytest.fixture
def stub_chaplin(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch every Chaplin-facing seam in :mod:`sabi.models.vsr.model`."""
    fake_ini = Path("fake.ini")

    def _fake_ensure_on_path() -> Path:
        return Path("/fake/chaplin")

    def _fake_build_runtime_ini(ini_path, manifest_path, weights_root) -> Path:  # noqa: ANN001
        return fake_ini

    class _FakeParser:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def read(self, *_a: Any, **_kw: Any) -> None:  # pragma: no cover - trivial
            pass

        def get(self, section: str, key: str) -> str:
            return {
                ("input", "modality"): "video",
                ("model", "model_path"): "/fake/model.pth",
                ("model", "model_conf"): "/fake/model.json",
                ("model", "rnnlm"): "/fake/lm.pth",
                ("model", "rnnlm_conf"): "/fake/lm.json",
            }[(section, key)]

        def getfloat(self, section: str, key: str) -> float:
            return {
                ("input", "v_fps"): 25.0,
                ("model", "v_fps"): 25.0,
                ("decode", "penalty"): 0.0,
                ("decode", "ctc_weight"): 0.1,
                ("decode", "lm_weight"): 0.3,
            }[(section, key)]

        def getint(self, section: str, key: str) -> int:
            return {("decode", "beam_size"): 40}[(section, key)]

    import sys
    import types

    fake_pipelines = types.ModuleType("pipelines")
    fake_pipelines_data = types.ModuleType("pipelines.data")
    fake_pipelines_model = types.ModuleType("pipelines.model")
    fake_pipelines_transforms = types.ModuleType("pipelines.data.transforms")
    fake_pipelines_model.AVSR = _FakeAVSR
    fake_pipelines_transforms.VideoTransform = _FakeVideoTransform
    fake_pipelines.data = fake_pipelines_data  # type: ignore[attr-defined]
    fake_pipelines_data.transforms = fake_pipelines_transforms  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pipelines", fake_pipelines)
    monkeypatch.setitem(sys.modules, "pipelines.data", fake_pipelines_data)
    monkeypatch.setitem(sys.modules, "pipelines.model", fake_pipelines_model)
    monkeypatch.setitem(sys.modules, "pipelines.data.transforms", fake_pipelines_transforms)

    monkeypatch.setattr(vsr_model, "ensure_on_path", _fake_ensure_on_path)
    monkeypatch.setattr(vsr_model, "_build_runtime_ini", _fake_build_runtime_ini)
    monkeypatch.setattr(vsr_model, "ConfigParser", _FakeParser)

    _FakeAVSR.last_instance = None
    return {
        "AVSR": _FakeAVSR,
        "VideoTransform": _FakeVideoTransform,
        "ini": fake_ini,
    }


def _grey_frame() -> np.ndarray:
    return np.full((96, 96), 128, dtype=np.uint8)


def test_predict_returns_result_with_latency(stub_chaplin: dict[str, Any]) -> None:
    cfg = VSRModelConfig(device="cpu", precision="fp32")
    with VSRModel(cfg) as vsr:
        result = vsr.predict([_grey_frame() for _ in range(5)])
    assert isinstance(result, VSRResult)
    assert result.text == "hello world"
    assert result.confidence == pytest.approx(1.0)
    assert result.latency_ms >= 0.0
    assert result.per_token_scores is None
    avsr = stub_chaplin["AVSR"].last_instance
    assert avsr is not None
    assert avsr.kwargs["device"] == "cpu"


def test_auto_device_selects_cuda_when_available(
    stub_chaplin: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    with VSRModel(VSRModelConfig(device="auto")) as vsr:
        vsr.predict([_grey_frame()])
    avsr = stub_chaplin["AVSR"].last_instance
    assert avsr is not None
    assert avsr.kwargs["device"] == "cuda:0"


def test_auto_device_falls_back_to_cpu_without_cuda(
    stub_chaplin: dict[str, Any], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with caplog.at_level("WARNING", logger="sabi.models.vsr.model"):
        with VSRModel(VSRModelConfig(device="auto")) as vsr:
            vsr.predict([_grey_frame()])
    avsr = stub_chaplin["AVSR"].last_instance
    assert avsr is not None
    assert avsr.kwargs["device"] == "cpu"
    assert any("CUDA not available" in rec.message for rec in caplog.records)


def test_fp16_on_cpu_still_runs_without_autocast(
    stub_chaplin: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    called: list[str] = []

    class _Guard:
        def __enter__(self) -> "_Guard":
            called.append("enter")
            return self

        def __exit__(self, *a: Any) -> None:
            called.append("exit")

    monkeypatch.setattr(torch, "autocast", lambda *a, **kw: _Guard())
    with VSRModel(VSRModelConfig(device="cpu", precision="fp16")) as vsr:
        vsr.predict([_grey_frame()])
    assert called == []  # autocast skipped on CPU per wrapper logic


def test_fp16_on_cuda_uses_autocast(
    stub_chaplin: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    opened: list[dict[str, Any]] = []

    class _Guard:
        def __enter__(self) -> "_Guard":
            return self

        def __exit__(self, *a: Any) -> None:
            return None

    def _autocast(*args: Any, **kwargs: Any) -> _Guard:
        opened.append({"args": args, "kwargs": kwargs})
        return _Guard()

    monkeypatch.setattr(torch, "autocast", _autocast)
    with VSRModel(VSRModelConfig(device="cuda", precision="fp16")) as vsr:
        vsr.predict([_grey_frame()])
    assert opened, "autocast should have been entered exactly once"
    assert opened[0]["kwargs"]["device_type"] == "cuda"
    assert opened[0]["kwargs"]["dtype"] is torch.float16


@pytest.mark.parametrize(
    "frame,msg_fragment",
    [
        (np.zeros((96, 96, 3), dtype=np.uint8), "expected 2-D grayscale"),
        (np.zeros((64, 64), dtype=np.uint8), "shape (64, 64)"),
        (np.zeros((96, 96), dtype=np.float32), "dtype"),
    ],
)
def test_bad_frames_raise_vsr_input_error(
    stub_chaplin: dict[str, Any], frame: np.ndarray, msg_fragment: str
) -> None:
    with VSRModel(VSRModelConfig(device="cpu")) as vsr:
        with pytest.raises(VSRInputError) as excinfo:
            vsr.predict([frame])
    assert msg_fragment in str(excinfo.value)


def test_empty_input_raises(stub_chaplin: dict[str, Any]) -> None:
    with VSRModel(VSRModelConfig(device="cpu")) as vsr:
        with pytest.raises(VSRInputError, match="zero lip frames"):
            vsr.predict([])


def test_max_frames_cap(stub_chaplin: dict[str, Any]) -> None:
    cfg = VSRModelConfig(device="cpu", max_frames=3)
    with VSRModel(cfg) as vsr:
        with pytest.raises(VSRInputError, match="max_frames"):
            vsr.predict([_grey_frame() for _ in range(5)])


def test_predict_streaming_yields_one_result_per_batch(
    stub_chaplin: dict[str, Any],
) -> None:
    batches = [[_grey_frame()] * 3, [_grey_frame()] * 2]
    with VSRModel(VSRModelConfig(device="cpu")) as vsr:
        results = list(vsr.predict_streaming(batches))
    assert len(results) == 2
    assert all(r.text == "hello world" for r in results)


def test_lip_frame_objects_accepted(stub_chaplin: dict[str, Any]) -> None:
    from sabi.capture.lip_roi import LipFrame

    frames = [
        LipFrame(
            timestamp_ns=i,
            crop=_grey_frame(),
            confidence=1.0,
            face_present=True,
            bbox=(0.0, 0.0, 96.0, 0.0),
        )
        for i in range(4)
    ]
    with VSRModel(VSRModelConfig(device="cpu")) as vsr:
        result = vsr.predict(frames)
    assert result.text == "hello world"
