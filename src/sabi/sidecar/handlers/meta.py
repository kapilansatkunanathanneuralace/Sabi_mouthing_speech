"""Meta sidecar handlers."""

from __future__ import annotations

from importlib import metadata
from typing import Any

from sabi.sidecar.dispatcher import Notify, SidecarDispatcher
from sabi.sidecar.protocol import SIDECAR_PROTOCOL_VERSION


def _app_version() -> str:
    try:
        return metadata.version("sabi")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def meta_version(_params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    return {
        "protocol_version": SIDECAR_PROTOCOL_VERSION,
        "app_version": _app_version(),
    }


def meta_shutdown(_params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    return {"ok": True, "_shutdown": True}


def register_meta_handlers(dispatcher: SidecarDispatcher) -> None:
    dispatcher.register("meta.version", meta_version)
    dispatcher.register("meta.shutdown", meta_shutdown)
