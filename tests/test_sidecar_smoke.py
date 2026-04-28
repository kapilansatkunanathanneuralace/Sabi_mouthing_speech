from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


def test_frozen_sidecar_meta_version() -> None:
    sidecar = os.environ.get("SABI_SIDECAR_BIN")
    if not sidecar:
        pytest.skip("SABI_SIDECAR_BIN is not set")
    binary = Path(sidecar)
    if not binary.is_file():
        pytest.fail(f"SABI_SIDECAR_BIN does not point to a file: {binary}")

    proc = subprocess.run(
        [str(binary)],
        input='{"jsonrpc":"2.0","id":1,"method":"meta.version"}\n',
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, proc.stderr
    payload = json.loads(lines[-1])
    assert payload["result"]["protocol_version"] == "1.0.0"
