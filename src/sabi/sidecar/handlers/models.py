"""Model asset sidecar handlers."""

from __future__ import annotations

from typing import Any

from sabi.runtime.asset_cache import AssetCache
from sabi.sidecar.dispatcher import Notify, SidecarDispatcher


def models_download_vsr(params: dict[str, Any], notify: Notify) -> dict[str, Any]:
    force = bool(params.get("force", False))
    cache = AssetCache()

    def _progress(payload: dict[str, Any]) -> None:
        notify("models.download_vsr.progress", payload)

    status = cache.ensure("vsr", force=force, progress=_progress)
    ok = status["status"] == "present"
    return {"ok": ok, "exit_code": 0 if ok else 1, "manifest": status}


def register_model_handlers(dispatcher: SidecarDispatcher) -> None:
    dispatcher.register("models.download_vsr", models_download_vsr)
