"""Output layer: clipboard + paste injection (TICKET-009)."""

from sabi.output.inject import (
    InjectConfig,
    InjectResult,
    capture_clipboard,
    paste_text,
)

__all__ = [
    "InjectConfig",
    "InjectResult",
    "capture_clipboard",
    "paste_text",
]
