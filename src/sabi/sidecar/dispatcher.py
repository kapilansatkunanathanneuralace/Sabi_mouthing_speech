"""Method registry and dispatcher for the Sabi JSON-RPC sidecar."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from sabi.sidecar.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    JsonRpcRequest,
    error_response,
    notification,
    success_response,
)

logger = logging.getLogger(__name__)

Notify = Callable[[str, dict[str, Any] | list[Any] | None], None]
Handler = Callable[[dict[str, Any], Notify], Any | Awaitable[Any]]


@dataclass(frozen=True)
class DispatchResult:
    response: dict[str, Any] | None
    shutdown: bool = False


class SidecarDispatcher:
    """Dispatch JSON-RPC requests to registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    def notify_payload(
        self,
        sink: Callable[[dict[str, Any]], None],
    ) -> Notify:
        def _notify(method: str, params: dict[str, Any] | list[Any] | None = None) -> None:
            sink(notification(method, params))

        return _notify

    async def dispatch(
        self,
        payload: dict[str, Any],
        *,
        notify: Notify | None = None,
    ) -> DispatchResult:
        try:
            request = JsonRpcRequest.model_validate(payload)
        except ValidationError as exc:
            return DispatchResult(
                error_response(None, INVALID_REQUEST, "Invalid Request", exc.errors()),
            )
        if request.jsonrpc != "2.0":
            return DispatchResult(
                error_response(request.id, INVALID_REQUEST, "Invalid JSON-RPC version"),
            )
        handler = self._handlers.get(request.method)
        if handler is None:
            return DispatchResult(
                error_response(request.id, METHOD_NOT_FOUND, f"Method not found: {request.method}"),
            )
        if request.params is None:
            params: dict[str, Any] = {}
        elif isinstance(request.params, dict):
            params = request.params
        else:
            return DispatchResult(
                error_response(request.id, INVALID_PARAMS, "Params must be object")
            )

        try:
            result = handler(params, notify or (lambda _method, _params=None: None))
            if inspect.isawaitable(result):
                result = await result
        except ValueError as exc:
            return DispatchResult(error_response(request.id, INVALID_PARAMS, str(exc)))
        except Exception as exc:  # noqa: BLE001 - sidecar must not crash per request
            logger.exception("sidecar handler failed: %s", request.method)
            return DispatchResult(error_response(request.id, INTERNAL_ERROR, str(exc)))

        shutdown = bool(isinstance(result, dict) and result.pop("_shutdown", False))
        return DispatchResult(success_response(request.id, result), shutdown=shutdown)


def make_default_dispatcher() -> SidecarDispatcher:
    from sabi.sidecar.handlers import register_handlers

    dispatcher = SidecarDispatcher()
    register_handlers(dispatcher)
    return dispatcher
