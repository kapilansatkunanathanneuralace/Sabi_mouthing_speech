"""TICKET-010: HotkeyController and TriggerBus tests.

A tiny fake of the ``keyboard`` package drives the controller without
touching the real Windows hook. It records every registered callback so
tests can synthesize press / release events, and it tracks which keys
are currently "held" so :meth:`is_pressed` answers deterministically.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import pytest

from sabi.input import (
    HotkeyConfig,
    HotkeyController,
    TriggerBus,
    TriggerEvent,
    load_hotkey_config,
    parse_binding,
)


class FakeKeyboard:
    """Minimal stand-in for the ``keyboard`` module."""

    def __init__(self) -> None:
        self.held: set[str] = set()
        self.press_callbacks: dict[str, list[Callable[[Any], None]]] = {}
        self.release_callbacks: dict[str, list[Callable[[Any], None]]] = {}
        self.hotkey_callbacks: dict[str, list[Callable[[], None]]] = {}
        self.unhook_all_calls = 0
        self.remover_calls = 0

    def on_press_key(self, key: str, cb: Callable[[Any], None]) -> Callable[[], None]:
        self.press_callbacks.setdefault(key, []).append(cb)

        def remove() -> None:
            self.remover_calls += 1
            self.press_callbacks[key].remove(cb)

        return remove

    def on_release_key(self, key: str, cb: Callable[[Any], None]) -> Callable[[], None]:
        self.release_callbacks.setdefault(key, []).append(cb)

        def remove() -> None:
            self.remover_calls += 1
            self.release_callbacks[key].remove(cb)

        return remove

    def add_hotkey(self, binding: str, cb: Callable[[], None]) -> Callable[[], None]:
        self.hotkey_callbacks.setdefault(binding, []).append(cb)

        def remove() -> None:
            self.remover_calls += 1
            self.hotkey_callbacks[binding].remove(cb)

        return remove

    def unhook_all(self) -> None:
        self.unhook_all_calls += 1

    def is_pressed(self, binding: str) -> bool:
        parts = [p.strip().lower() for p in binding.split("+") if p.strip()]
        return all(p in self.held for p in parts)

    def press(self, key: str) -> None:
        self.held.add(key)
        for cb in list(self.press_callbacks.get(key, [])):
            cb(object())

    def release(self, key: str) -> None:
        self.held.discard(key)
        for cb in list(self.release_callbacks.get(key, [])):
            cb(object())

    def tap_hotkey(self, binding: str) -> None:
        for cb in list(self.hotkey_callbacks.get(binding, [])):
            cb()


@pytest.fixture
def fake_kb() -> FakeKeyboard:
    return FakeKeyboard()


def _drain(bus: TriggerBus, *, timeout: float = 1.0) -> None:
    """Block until the bus worker has processed every queued event."""
    deadline = time.monotonic() + timeout
    while not bus._queue.empty():
        if time.monotonic() > deadline:
            raise TimeoutError("trigger bus did not drain in time")
        time.sleep(0.005)
    time.sleep(0.02)


def _collect(controller: HotkeyController) -> tuple[list[TriggerEvent], list[TriggerEvent]]:
    starts: list[TriggerEvent] = []
    stops: list[TriggerEvent] = []
    controller.bus.subscribe_start(starts.append)
    controller.bus.subscribe_stop(stops.append)
    return starts, stops


def test_parse_binding_splits_modifiers_and_trigger() -> None:
    mods, trig = parse_binding("Ctrl+Alt+Space")
    assert mods == ("ctrl", "alt")
    assert trig == "space"


def test_ptt_emits_start_after_min_hold_and_stop_on_release(
    fake_kb: FakeKeyboard,
) -> None:
    cfg = HotkeyConfig(mode="push_to_talk", min_hold_ms=30, cooldown_ms=0)
    with HotkeyController(cfg, keyboard_module=fake_kb) as controller:
        starts, stops = _collect(controller)

        fake_kb.press("ctrl")
        fake_kb.press("alt")
        fake_kb.press("space")
        time.sleep(0.10)
        fake_kb.release("space")
        fake_kb.release("alt")
        fake_kb.release("ctrl")

        _drain(controller.bus)

        assert len(starts) == 1
        assert len(stops) == 1
        assert starts[0].mode == "push_to_talk"
        assert starts[0].reason == "hotkey"
        assert stops[0].trigger_id == starts[0].trigger_id
        assert stops[0].started_at_ns == starts[0].started_at_ns


def test_ptt_short_tap_does_not_fire_start(fake_kb: FakeKeyboard) -> None:
    cfg = HotkeyConfig(mode="push_to_talk", min_hold_ms=200, cooldown_ms=0)
    with HotkeyController(cfg, keyboard_module=fake_kb) as controller:
        starts, stops = _collect(controller)

        fake_kb.press("ctrl")
        fake_kb.press("alt")
        fake_kb.press("space")
        time.sleep(0.05)
        fake_kb.release("space")
        fake_kb.release("alt")
        fake_kb.release("ctrl")

        _drain(controller.bus)

        assert starts == []
        assert stops == []


def test_ptt_cooldown_suppresses_second_start(fake_kb: FakeKeyboard) -> None:
    cfg = HotkeyConfig(mode="push_to_talk", min_hold_ms=10, cooldown_ms=1000)
    with HotkeyController(cfg, keyboard_module=fake_kb) as controller:
        starts, stops = _collect(controller)

        for _ in range(2):
            fake_kb.press("ctrl")
            fake_kb.press("alt")
            fake_kb.press("space")
            time.sleep(0.05)
            fake_kb.release("space")
            fake_kb.release("alt")
            fake_kb.release("ctrl")
            time.sleep(0.02)

        _drain(controller.bus)

        assert len(starts) == 1
        assert len(stops) == 1


def test_ptt_modifier_release_breaks_chord(fake_kb: FakeKeyboard) -> None:
    cfg = HotkeyConfig(mode="push_to_talk", min_hold_ms=10, cooldown_ms=0)
    with HotkeyController(cfg, keyboard_module=fake_kb) as controller:
        starts, stops = _collect(controller)

        fake_kb.press("ctrl")
        fake_kb.press("alt")
        fake_kb.press("space")
        time.sleep(0.05)
        fake_kb.release("ctrl")
        time.sleep(0.02)
        fake_kb.release("alt")
        fake_kb.release("space")

        _drain(controller.bus)

        assert len(starts) == 1
        assert len(stops) == 1


def test_toggle_alternating_presses_start_then_stop(
    fake_kb: FakeKeyboard,
) -> None:
    cfg = HotkeyConfig(mode="toggle", min_hold_ms=0, cooldown_ms=0)
    with HotkeyController(cfg, keyboard_module=fake_kb) as controller:
        starts, stops = _collect(controller)

        fake_kb.tap_hotkey("ctrl+alt+space")
        fake_kb.tap_hotkey("ctrl+alt+space")
        fake_kb.tap_hotkey("ctrl+alt+space")

        _drain(controller.bus)

        assert len(starts) == 2
        assert len(stops) == 1
        assert starts[0].mode == "toggle"
        assert stops[0].trigger_id == starts[0].trigger_id


def test_toggle_min_hold_drops_debounce_presses(
    fake_kb: FakeKeyboard,
) -> None:
    cfg = HotkeyConfig(mode="toggle", min_hold_ms=500, cooldown_ms=0)
    with HotkeyController(cfg, keyboard_module=fake_kb) as controller:
        starts, stops = _collect(controller)

        fake_kb.tap_hotkey("ctrl+alt+space")
        fake_kb.tap_hotkey("ctrl+alt+space")

        _drain(controller.bus)

        assert len(starts) == 1
        assert stops == []


def test_stop_removes_hooks_and_joins_worker(fake_kb: FakeKeyboard) -> None:
    cfg = HotkeyConfig(mode="push_to_talk", min_hold_ms=10, cooldown_ms=0)
    controller = HotkeyController(cfg, keyboard_module=fake_kb)
    controller.start()
    assert fake_kb.remover_calls == 0
    controller.stop()
    assert fake_kb.remover_calls >= 2
    assert all(not cbs for cbs in fake_kb.press_callbacks.values())
    assert all(not cbs for cbs in fake_kb.release_callbacks.values())


def test_fire_cli_events_share_contract(fake_kb: FakeKeyboard) -> None:
    cfg = HotkeyConfig(mode="push_to_talk", min_hold_ms=0, cooldown_ms=0)
    with HotkeyController(cfg, keyboard_module=fake_kb) as controller:
        starts, stops = _collect(controller)

        start_event = controller.bus.fire_start_cli("push_to_talk")
        controller.bus.fire_stop_cli("push_to_talk", start_event)

        _drain(controller.bus)

    assert len(starts) == 1
    assert len(stops) == 1
    assert starts[0].reason == "cli"
    assert stops[0].reason == "cli"
    assert stops[0].trigger_id == starts[0].trigger_id
    assert stops[0].started_at_ns == starts[0].started_at_ns


def test_load_hotkey_config_defaults_when_missing(tmp_path: Any) -> None:
    cfg = load_hotkey_config(None)
    assert cfg.mode == "push_to_talk"
    assert cfg.binding == "ctrl+alt+space"
    assert cfg.min_hold_ms == 80
    assert cfg.cooldown_ms == 150


def test_load_hotkey_config_reads_toml(tmp_path: Any) -> None:
    cfg_path = tmp_path / "hotkey.toml"
    cfg_path.write_text(
        """
[trigger]
mode = "toggle"
binding = "ctrl+shift+f12"

[gates]
min_hold_ms = 10
cooldown_ms = 20
        """.strip(),
        encoding="utf-8",
    )
    cfg = load_hotkey_config(cfg_path)
    assert cfg.mode == "toggle"
    assert cfg.binding == "ctrl+shift+f12"
    assert cfg.min_hold_ms == 10
    assert cfg.cooldown_ms == 20
