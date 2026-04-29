"""Model asset cache sidecar handlers."""

from __future__ import annotations

from typing import Any

from sabi.runtime.asset_cache import AssetCache
from sabi.sidecar.dispatcher import Notify, SidecarDispatcher

DEFAULT_MANIFESTS = ("vsr", "asr", "cleanup")
FIRST_LAUNCH_MANIFESTS = ("vsr", "asr")


def _manifest_names(params: dict[str, Any], *, first_launch_default: bool = False) -> list[str]:
    if isinstance(params.get("manifests"), list):
        return [str(item) for item in params["manifests"]]
    if params.get("manifest"):
        return [str(params["manifest"])]
    return list(FIRST_LAUNCH_MANIFESTS if first_launch_default else DEFAULT_MANIFESTS)


def cache_status(params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    cache = AssetCache()
    manifests = [cache.status(name) for name in _manifest_names(params)]
    return {"root": str(cache.root), "manifests": manifests}


def cache_verify(params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    cache = AssetCache()
    manifests = [cache.verify(name) for name in _manifest_names(params)]
    ok = all(item["status"] in {"present", "unsupported"} for item in manifests)
    return {"ok": ok, "manifests": manifests}


def cache_download(params: dict[str, Any], notify: Notify) -> dict[str, Any]:
    cache = AssetCache()
    force = bool(params.get("force", False))
    names = _manifest_names(params, first_launch_default=True)
    manifests = []

    for name in names:
        def _progress(payload: dict[str, Any]) -> None:
            notify("cache.download.progress", payload)

        result = cache.ensure(name, force=force, progress=_progress)
        manifests.append(result)

    return {"ok": all(item["status"] == "present" for item in manifests), "manifests": manifests}


def cache_clear(params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    cache = AssetCache()
    manifests = [cache.clear(name) for name in _manifest_names(params)]
    return {"ok": True, "manifests": manifests}


def register_cache_handlers(dispatcher: SidecarDispatcher) -> None:
    dispatcher.register("cache.status", cache_status)
    dispatcher.register("cache.verify", cache_verify)
    dispatcher.register("cache.download", cache_download)
    dispatcher.register("cache.clear", cache_clear)
