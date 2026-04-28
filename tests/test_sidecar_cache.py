from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from sabi.sidecar.dispatcher import SidecarDispatcher
from sabi.sidecar.handlers.cache import register_cache_handlers


def _install_manifest(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    source = tmp_path / "source.bin"
    source.write_bytes(b"sidecar cache")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir()
    (manifest_root / "fixture.toml").write_text(
        "\n".join(
            [
                "[manifest]",
                'name = "fixture"',
                'kind = "test"',
                'description = "Test manifest"',
                "",
                "[[files]]",
                'name = "payload"',
                'kind = "test"',
                'relative_path = "payload.bin"',
                f'url = "{source.as_uri()}"',
                f'sha256 = "{digest}"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SABI_MANIFESTS_DIR", str(manifest_root))
    monkeypatch.setenv("SABI_MODELS_DIR", str(tmp_path / "models"))


def test_cache_methods_download_verify_and_clear(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    _install_manifest(tmp_path, monkeypatch)
    dispatcher = SidecarDispatcher()
    register_cache_handlers(dispatcher)
    notifications = []

    status = asyncio.run(
        dispatcher.dispatch(
            {"jsonrpc": "2.0", "id": 1, "method": "cache.status", "params": {"manifest": "fixture"}}
        )
    )
    assert status.response is not None
    assert status.response["result"]["manifests"][0]["status"] == "missing"

    downloaded = asyncio.run(
        dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "cache.download",
                "params": {"manifest": "fixture"},
            },
            notify=lambda method, params=None: notifications.append((method, params)),
        )
    )
    assert downloaded.response is not None
    assert downloaded.response["result"]["ok"] is True
    assert any(method == "cache.download.progress" for method, _params in notifications)

    verified = asyncio.run(
        dispatcher.dispatch(
            {"jsonrpc": "2.0", "id": 3, "method": "cache.verify", "params": {"manifest": "fixture"}}
        )
    )
    assert verified.response is not None
    assert verified.response["result"]["ok"] is True

    cleared = asyncio.run(
        dispatcher.dispatch(
            {"jsonrpc": "2.0", "id": 4, "method": "cache.clear", "params": {"manifest": "fixture"}}
        )
    )
    assert cleared.response is not None
    assert cleared.response["result"]["manifests"][0]["status"] == "missing"
