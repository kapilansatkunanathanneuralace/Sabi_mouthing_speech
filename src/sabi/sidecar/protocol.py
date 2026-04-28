"""JSON-RPC 2.0 protocol models for the Sabi sidecar."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SIDECAR_PROTOCOL_VERSION = "1.0.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

JsonRpcId = int | str | None


class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: JsonRpcId = None
    method: str
    params: dict[str, Any] | list[Any] | None = None

    model_config = ConfigDict(extra="forbid")


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: JsonRpcId = None
    result: Any = None
    error: JsonRpcError | None = None

    model_config = ConfigDict(extra="forbid")


class JsonRpcNotification(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | list[Any] | None = None

    model_config = ConfigDict(extra="forbid")


def success_response(request_id: JsonRpcId, result: Any = None) -> dict[str, Any]:
    return JsonRpcResponse(id=request_id, result=result).model_dump(exclude_none=True)


def error_response(
    request_id: JsonRpcId,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    return JsonRpcResponse(
        id=request_id,
        error=JsonRpcError(code=code, message=message, data=data),
    ).model_dump(exclude_none=True)


def notification(method: str, params: dict[str, Any] | list[Any] | None = None) -> dict[str, Any]:
    return JsonRpcNotification(method=method, params=params).model_dump(exclude_none=True)
