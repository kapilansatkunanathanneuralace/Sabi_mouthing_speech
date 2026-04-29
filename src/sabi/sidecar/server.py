"""Line-delimited JSON-RPC stdio server for the Sabi sidecar."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, TextIO

from sabi.sidecar.dispatcher import SidecarDispatcher, make_default_dispatcher
from sabi.sidecar.protocol import PARSE_ERROR, error_response

logger = logging.getLogger(__name__)


def _write_json(stream: TextIO, payload: dict[str, Any]) -> None:
    stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
    stream.flush()


async def run_stdio_server_async(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    dispatcher: SidecarDispatcher | None = None,
) -> int:
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout
    dispatch = dispatcher or make_default_dispatcher()

    def notify_sink(payload: dict[str, Any]) -> None:
        _write_json(out_stream, payload)

    notify = dispatch.notify_payload(notify_sink)

    while True:
        line = in_stream.readline()
        if line == "":
            return 0
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            _write_json(out_stream, error_response(None, PARSE_ERROR, "Parse error", str(exc)))
            continue
        if not isinstance(payload, dict):
            _write_json(out_stream, error_response(None, PARSE_ERROR, "Request must be object"))
            continue
        result = await dispatch.dispatch(payload, notify=notify)
        if result.response is not None:
            _write_json(out_stream, result.response)
        if result.shutdown:
            return 0


def run_stdio_server(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    dispatcher: SidecarDispatcher | None = None,
) -> int:
    return asyncio.run(
        run_stdio_server_async(stdin=stdin, stdout=stdout, dispatcher=dispatcher),
    )
