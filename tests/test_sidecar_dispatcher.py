from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sabi.sidecar.dispatcher import SidecarDispatcher
from sabi.sidecar.handlers.dictation import DictationSessionManager, register_dictation_handlers
from sabi.sidecar.handlers.meta import register_meta_handlers
from sabi.sidecar.handlers.models import register_model_handlers
from sabi.sidecar.protocol import METHOD_NOT_FOUND


def test_meta_version_dispatches() -> None:
    dispatcher = SidecarDispatcher()
    register_meta_handlers(dispatcher)

    result = asyncio.run(
        dispatcher.dispatch({"jsonrpc": "2.0", "id": 1, "method": "meta.version"})
    )

    assert result.response is not None
    assert result.response["id"] == 1
    assert result.response["result"]["protocol_version"] == "1.0.0"


def test_unknown_method_returns_method_not_found() -> None:
    dispatcher = SidecarDispatcher()

    result = asyncio.run(
        dispatcher.dispatch({"jsonrpc": "2.0", "id": 2, "method": "missing.method"})
    )

    assert result.response is not None
    assert result.response["error"]["code"] == METHOD_NOT_FOUND


def test_shutdown_sets_dispatch_flag() -> None:
    dispatcher = SidecarDispatcher()
    register_meta_handlers(dispatcher)

    result = asyncio.run(
        dispatcher.dispatch({"jsonrpc": "2.0", "id": 3, "method": "meta.shutdown"})
    )

    assert result.shutdown is True
    assert result.response is not None
    assert result.response["result"] == {"ok": True}


def test_models_download_vsr_streams_notifications(monkeypatch) -> None:  # noqa: ANN001
    from sabi.sidecar.handlers import models

    class FakeCache:
        def ensure(self, manifest: str, *, force: bool, progress):  # noqa: ANN001
            assert manifest == "vsr"
            assert force is True
            progress({"name": "vsr_model", "status": "verified"})
            return {"status": "present"}

    monkeypatch.setattr(models, "AssetCache", lambda: FakeCache())
    dispatcher = SidecarDispatcher()
    register_model_handlers(dispatcher)
    notifications = []

    result = asyncio.run(
        dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "models.download_vsr",
                "params": {"force": True},
            },
            notify=lambda method, params=None: notifications.append((method, params)),
        )
    )

    assert result.response is not None
    assert result.response["result"] == {
        "ok": True,
        "exit_code": 0,
        "manifest": {"status": "present"},
    }
    assert notifications == [
        ("models.download_vsr.progress", {"name": "vsr_model", "status": "verified"})
    ]


@dataclass
class _FakeEvent:
    pipeline: str = "silent"
    mode: str = "idle"


class _FakePipeline:
    last_config = None
    starts = 0
    stops = 0

    def __init__(self, config) -> None:  # noqa: ANN001
        self.config = config
        _FakePipeline.last_config = config
        self._status = None

    def subscribe_status(self, callback) -> None:  # noqa: ANN001
        self._status = callback

    def subscribe(self, _callback) -> None:  # noqa: ANN001
        return None

    def __enter__(self) -> "_FakePipeline":
        if self._status is not None:
            self._status(_FakeEvent())
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def on_trigger_start(self, _event) -> None:  # noqa: ANN001
        _FakePipeline.starts += 1

    def on_trigger_stop(self, _event) -> None:  # noqa: ANN001
        _FakePipeline.stops += 1


def test_dictation_start_defaults_to_dry_run(monkeypatch) -> None:  # noqa: ANN001
    import sabi.pipelines.silent_dictate as silent

    monkeypatch.setattr(silent, "SilentDictatePipeline", _FakePipeline)
    _FakePipeline.starts = 0
    _FakePipeline.stops = 0
    manager = DictationSessionManager()
    dispatcher = SidecarDispatcher()
    register_dictation_handlers(dispatcher, manager)
    notifications = []

    result = asyncio.run(
        dispatcher.dispatch(
            {"jsonrpc": "2.0", "id": 5, "method": "dictation.silent.start", "params": {}},
            notify=lambda method, params=None: notifications.append((method, params)),
        )
    )
    asyncio.run(
        dispatcher.dispatch(
            {"jsonrpc": "2.0", "id": 6, "method": "dictation.silent.stop", "params": {}},
            notify=lambda method, params=None: notifications.append((method, params)),
        )
    )

    assert result.response is not None
    assert result.response["result"]["dry_run"] is True
    assert result.response["result"]["capturing"] is True
    assert _FakePipeline.last_config.dry_run is True
    assert _FakePipeline.starts == 1
    assert _FakePipeline.stops == 1
    assert any(method == "dictation.silent.status" for method, _params in notifications)
