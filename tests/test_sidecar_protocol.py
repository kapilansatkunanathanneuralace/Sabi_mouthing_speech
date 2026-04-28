from __future__ import annotations

from sabi.sidecar.protocol import (
    METHOD_NOT_FOUND,
    SIDECAR_PROTOCOL_VERSION,
    JsonRpcRequest,
    error_response,
)


def test_protocol_version_is_pinned() -> None:
    assert SIDECAR_PROTOCOL_VERSION == "1.0.0"


def test_request_rejects_extra_fields() -> None:
    try:
        JsonRpcRequest.model_validate(
            {"jsonrpc": "2.0", "id": 1, "method": "meta.version", "extra": True}
        )
    except Exception as exc:  # noqa: BLE001
        assert "extra" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected validation failure")


def test_error_response_shape() -> None:
    payload = error_response(1, METHOD_NOT_FOUND, "missing")
    assert payload == {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": METHOD_NOT_FOUND, "message": "missing"},
    }
