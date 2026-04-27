"""TICKET-013: Rich status TUI rendering tests."""

from __future__ import annotations

from types import SimpleNamespace

from rich.console import Console

from sabi.pipelines.events import PipelineStatusEvent
from sabi.ui.status_tui import StatusTUI


def _render_text(tui: StatusTUI) -> str:
    tui.console.print(tui.render())
    return tui.console.export_text()


def test_status_tui_renders_header_and_utterance_rows() -> None:
    console = Console(record=True, width=240)
    tui = StatusTUI(console=console)

    tui.handle_status(
        PipelineStatusEvent(
            pipeline="silent",
            mode="recording",
            utterance_id=1,
            hotkey_binding="ctrl+alt+space",
            force_paste_binding="f12",
            ollama_ok=True,
            ollama_model="llama3.2:3b",
            cuda_status="cpu (unavailable)",
            created_at_ns=1,
        )
    )
    tui.handle_utterance(
        SimpleNamespace(
            pipeline="silent",
            utterance_id=1,
            text_raw="hello world",
            text_final="Hello world.",
            confidence=0.93,
            decision="pasted",
            latencies={"total_ms": 123.0},
            error=None,
        )
    )

    text = _render_text(tui)

    assert "Pipeline: silent" in text
    assert "Mode: idle" in text
    assert "Hotkey: ctrl+alt+space" in text
    assert "Ollama: ok" in text
    assert "llama3.2:3b" in text
    assert "CUDA: cpu (unavailable)" in text
    assert "hello world" in text
    assert "Hello world." in text
    assert "0.93" in text
    assert "123 ms" in text


def test_status_tui_renders_pending_hint_and_ollama_offline() -> None:
    console = Console(record=True, width=240)
    tui = StatusTUI(console=console)

    tui.handle_status(
        PipelineStatusEvent(
            pipeline="audio",
            mode="idle",
            hotkey_binding="ctrl+alt+space",
            force_paste_binding="f12",
            ollama_ok=False,
            ollama_model="llama3.2:3b",
            cuda_status="cuda (available)",
            pending_force_paste=True,
            created_at_ns=1,
        )
    )
    tui.handle_utterance(
        SimpleNamespace(
            pipeline="audio",
            utterance_id=2,
            text_raw="maybe text",
            text_final="Maybe text.",
            confidence=0.22,
            decision="withheld_low_confidence",
            latencies={"total_ms": 300.0},
            error=None,
        )
    )

    text = _render_text(tui)

    assert "Pipeline: audio" in text
    assert "Ollama: offline" in text
    assert "raw" in text
    assert "output" in text
    assert "pending" in text
    assert "F12 to" in text
    assert "paste anyway" in text
    assert "discard" in text
    assert "Maybe text." in text


def test_status_tui_footer_rollups_and_clipboard_countdown() -> None:
    now_ns = 1_000_000_000
    console = Console(record=True, width=240)
    tui = StatusTUI(console=console, clock_ns=lambda: now_ns)

    for value in (100.0, 200.0, 300.0):
        tui.handle_utterance(
            SimpleNamespace(
                pipeline="silent",
                utterance_id=int(value),
                text_raw=f"raw {value}",
                text_final=f"clean {value}",
                confidence=0.9,
                decision="pasted",
                latencies={"total_ms": value},
                error=None,
            )
        )
    tui.handle_status(
        PipelineStatusEvent(
            pipeline="silent",
            mode="pasting",
            hotkey_binding="ctrl+alt+space",
            ollama_ok=True,
            ollama_model="llama3.2:3b",
            cuda_status="cpu (unavailable)",
            clipboard_restore_deadline_ns=now_ns + 400_000_000,
            created_at_ns=now_ns,
        )
    )

    text = _render_text(tui)

    assert "latency p50=200 ms" in text
    assert "p95=300 ms" in text
    assert "original clipboard will be restored" in text
    assert "400" in text


def test_status_tui_renders_fused_pipeline() -> None:
    console = Console(record=True, width=240)
    tui = StatusTUI(console=console)

    tui.handle_status(
        PipelineStatusEvent(
            pipeline="fused",
            mode="decoding",
            hotkey_binding="ctrl+alt+space",
            force_paste_binding="f12",
            ollama_ok=True,
            ollama_model="llama3.2:3b",
            cuda_status="cuda (available)",
            created_at_ns=1,
        )
    )
    tui.handle_utterance(
        SimpleNamespace(
            pipeline="fused",
            utterance_id=3,
            text_raw="hello fused",
            text_final="Hello fused.",
            confidence=0.88,
            decision="pasted",
            latencies={"total_ms": 222.0},
            error=None,
        )
    )

    text = _render_text(tui)

    assert "Pipeline: fused" in text
    assert "hello fused" in text
    assert "Hello fused." in text
