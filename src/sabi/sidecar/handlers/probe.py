"""Probe sidecar handlers."""

from __future__ import annotations

from typing import Any

from sabi.sidecar.dispatcher import Notify, SidecarDispatcher


def probe_run(params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    from sabi.probe import collect_probe_results

    camera_index = int(params.get("camera_index", 0))
    audio_device_index = params.get("audio_device_index")
    return {
        "probe": collect_probe_results(
            camera_index=camera_index,
            audio_device_index=None if audio_device_index is None else int(audio_device_index),
        ),
    }


def probe_devices(params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    from sabi.probe import list_probe_devices

    max_camera_index = int(params.get("max_camera_index", 4))
    return list_probe_devices(max_camera_index=max_camera_index)


def register_probe_handlers(dispatcher: SidecarDispatcher) -> None:
    dispatcher.register("probe.run", probe_run)
    dispatcher.register("probe.devices", probe_devices)
