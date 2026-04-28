"""Eval sidecar handlers."""

from __future__ import annotations

from typing import Any

from sabi.sidecar.dispatcher import Notify, SidecarDispatcher


def eval_run(params: dict[str, Any], _notify: Notify) -> dict[str, Any]:
    """Accept eval requests for desktop QA tooling.

    Full eval orchestration stays in the CLI for now; this typed response gives
    Electron a stable method to call while later packaging tickets expand the UX.
    """

    return {
        "accepted": True,
        "pipeline": params.get("pipeline"),
        "dataset": params.get("dataset"),
        "message": "eval.run accepted; full desktop orchestration is deferred",
    }


def register_eval_handlers(dispatcher: SidecarDispatcher) -> None:
    dispatcher.register("eval.run", eval_run)
