"""TICKET-008: TextCleaner / Ollama cleanup tests.

All tests use :class:`httpx.MockTransport` so no real Ollama daemon is
required. Latency-bound tests rely on short real timeouts (< 200 ms) to
keep the suite fast and deterministic.
"""

from __future__ import annotations

import json

import httpx
import pytest

from sabi.cleanup import CleanedText, CleanupConfig, CleanupContext, TextCleaner


def _tags_ok(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/tags"
    return httpx.Response(
        200,
        json={"models": [{"name": "llama3.2:3b-instruct-q4_K_M"}]},
    )


def _make_cleaner(
    handler,
    *,
    config: CleanupConfig | None = None,
) -> TextCleaner:
    cfg = config or CleanupConfig(
        timeout_ms=200,
        availability_timeout_ms=100,
        availability_cache_ms=5000,
    )
    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        base_url=cfg.base_url,
        timeout=cfg.timeout_ms / 1000.0,
        transport=transport,
    )
    return TextCleaner(cfg, client=client)


def test_cleanup_happy_path_returns_cleaned_text() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return _tags_ok(request)
        assert request.url.path == "/api/chat"
        body = json.loads(request.content.decode())
        seen.append(body)
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "I think it might work."}},
        )

    with _make_cleaner(handler) as cleaner:
        result = cleaner.cleanup(
            "um i think it might like work",
            CleanupContext(source="asr"),
        )

    assert isinstance(result, CleanedText)
    assert result.text == "I think it might work."
    assert result.used_fallback is False
    assert result.latency_ms >= 0.0
    assert result.reason is None

    assert len(seen) == 1
    body = seen[0]
    assert body["model"] == "llama3.2:3b-instruct-q4_K_M"
    assert body["stream"] is False
    assert body["options"]["num_predict"] == 256
    messages = body["messages"]
    assert messages[0]["role"] == "system"
    assert "preserve" in messages[0]["content"].lower()
    assert "um i think it might like work" in messages[1]["content"]


def test_cleanup_bypasses_and_warns_once_when_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _make_cleaner(handler) as cleaner:
        with caplog.at_level("WARNING", logger="sabi.cleanup.ollama"):
            first = cleaner.cleanup("hello world")
            second = cleaner.cleanup("another phrase")

    assert first.used_fallback is True
    assert first.text == "hello world"
    assert first.reason == "ollama_unavailable"
    assert second.used_fallback is True
    assert second.text == "another phrase"

    warnings = [rec for rec in caplog.records if "Ollama cleanup unavailable" in rec.message]
    assert len(warnings) == 1, "WARNING must fire exactly once per TextCleaner"


def test_cleanup_timeout_returns_raw_with_fallback() -> None:
    """When Ollama exceeds ``timeout_ms``, httpx raises ``ReadTimeout``.

    MockTransport does not enforce timeouts against real I/O, so we raise
    the timeout directly from the handler to exercise the fallback path.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return _tags_ok(request)
        raise httpx.ReadTimeout("simulated cleanup timeout", request=request)

    cfg = CleanupConfig(timeout_ms=100, availability_timeout_ms=100)
    cleaner = _make_cleaner(handler, config=cfg)
    try:
        result = cleaner.cleanup("this is a longer sentence that should time out cleanly")
    finally:
        cleaner.close()

    assert result.used_fallback is True
    assert result.text == "this is a longer sentence that should time out cleanly"
    assert result.reason is not None and result.reason.startswith("http_error")


def test_is_available_treats_timeout_as_unavailable() -> None:
    """``is_available()`` must return False (not raise) when the daemon hangs."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated availability hang", request=request)

    cfg = CleanupConfig(timeout_ms=100, availability_timeout_ms=50)
    cleaner = _make_cleaner(handler, config=cfg)
    try:
        available = cleaner.is_available()
    finally:
        cleaner.close()

    assert available is False


def test_is_available_caches_result_within_window() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        calls.append(1)
        return _tags_ok(request)

    cfg = CleanupConfig(availability_cache_ms=5000)
    cleaner = _make_cleaner(handler, config=cfg)
    try:
        assert cleaner.is_available() is True
        assert cleaner.is_available() is True
        assert cleaner.is_available() is True
    finally:
        cleaner.close()

    assert len(calls) == 1


def test_is_available_force_refresh_bypasses_cache() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _tags_ok(request)

    cleaner = _make_cleaner(handler)
    try:
        cleaner.is_available()
        cleaner.is_available(force_refresh=True)
    finally:
        cleaner.close()

    assert len(calls) == 2


def test_cleanup_empty_input_short_circuits_without_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP traffic expected for empty input")

    cleaner = _make_cleaner(handler)
    try:
        result = cleaner.cleanup("   ")
    finally:
        cleaner.close()

    assert result.text == "   "
    assert result.used_fallback is False
    assert result.reason == "empty_input"


def test_cleanup_hallucination_guard_returns_raw() -> None:
    long_raw = "hello world this is a reasonably long sentence"
    hallucinated = "HALLUCINATED " * 200

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return _tags_ok(request)
        return httpx.Response(200, json={"message": {"content": hallucinated}})

    cleaner = _make_cleaner(handler)
    try:
        result = cleaner.cleanup(long_raw)
    finally:
        cleaner.close()

    assert result.used_fallback is True
    assert result.text == long_raw
    assert result.reason == "output_too_long"


def test_cleanup_missing_message_content_falls_back() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return _tags_ok(request)
        return httpx.Response(200, json={"unexpected": "shape"})

    cleaner = _make_cleaner(handler)
    try:
        result = cleaner.cleanup("hello world")
    finally:
        cleaner.close()

    assert result.used_fallback is True
    assert result.text == "hello world"
    assert result.reason == "missing_message_content"


def test_cleanup_http_500_falls_back() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return _tags_ok(request)
        return httpx.Response(500, json={"error": "boom"})

    cleaner = _make_cleaner(handler)
    try:
        result = cleaner.cleanup("hello world")
    finally:
        cleaner.close()

    assert result.used_fallback is True
    assert result.text == "hello world"
    assert result.reason is not None and result.reason.startswith("http_error")


def test_load_cleanup_config_reads_toml(tmp_path) -> None:
    from sabi.cleanup.ollama import load_cleanup_config

    cfg_file = tmp_path / "cleanup.toml"
    cfg_file.write_text(
        "[ollama]\n"
        'base_url = "http://example:9999"\n'
        'model = "custom:3b"\n'
        "\n"
        "[limits]\n"
        "timeout_ms = 123\n"
        "temperature = 0.7\n",
        encoding="utf-8",
    )
    cfg = load_cleanup_config(cfg_file)
    assert cfg.base_url == "http://example:9999"
    assert cfg.model == "custom:3b"
    assert cfg.timeout_ms == 123
    assert cfg.temperature == pytest.approx(0.7)
