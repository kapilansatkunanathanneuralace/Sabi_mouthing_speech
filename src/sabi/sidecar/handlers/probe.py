"""Probe sidecar handlers."""

from __future__ import annotations

from typing import Any

from sabi.sidecar.dispatcher import Notify, SidecarDispatcher


def probe_run(params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    from sabi.probe import collect_probe_results

    camera_index = int(params.get("camera_index", 0))
    return {"probe": collect_probe_results(camera_index=camera_index)}


def register_probe_handlers(dispatcher: SidecarDispatcher) -> None:
    dispatcher.register("probe.run", probe_run)
