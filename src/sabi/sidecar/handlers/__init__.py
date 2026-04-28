"""Register sidecar JSON-RPC handlers."""

from __future__ import annotations

from sabi.sidecar.dispatcher import SidecarDispatcher
from sabi.sidecar.handlers.cache import register_cache_handlers
from sabi.sidecar.handlers.dictation import SESSION_MANAGER, register_dictation_handlers
from sabi.sidecar.handlers.eval import register_eval_handlers
from sabi.sidecar.handlers.meta import register_meta_handlers
from sabi.sidecar.handlers.models import register_model_handlers
from sabi.sidecar.handlers.probe import register_probe_handlers


def register_handlers(dispatcher: SidecarDispatcher) -> None:
    register_meta_handlers(dispatcher)
    register_probe_handlers(dispatcher)
    register_cache_handlers(dispatcher)
    register_model_handlers(dispatcher)
    register_dictation_handlers(dispatcher, SESSION_MANAGER)
    register_eval_handlers(dispatcher)
