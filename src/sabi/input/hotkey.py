"""Global hotkey trigger layer (TICKET-010).

Provides two trigger modes over the ``keyboard`` library:

* **push-to-talk** - ``on_start`` fires after the chord has been held
  for ``min_hold_ms``; ``on_stop`` fires as soon as any part of the
  chord is released.
* **toggle** - alternating presses flip ``on_start`` / ``on_stop``.

Subscribers register callbacks on a :class:`TriggerBus`; the bus
dispatches on a dedicated worker thread so callbacks never run inside
the ``keyboard`` Windows hook. The ``keyboard`` package cannot register
two ``add_hotkey`` callbacks for the same chord (the second overwrites
the first), so PTT is implemented with ``on_press_key`` /
``on_release_key`` + :func:`keyboard.is_pressed` chord checks rather
than two ``add_hotkey`` calls.
"""

from __future__ import annotations

import atexit
import logging
import os
import queue
import threading
import time
import tomllib
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from sabi.runtime.paths import configs_dir

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = configs_dir() / "hotkey.toml"

Mode = Literal["push_to_talk", "toggle"]
Reason = Literal["hotkey", "cli"]

_MODIFIER_NAMES: frozenset[str] = frozenset(
    {
        "ctrl",
        "control",
        "alt",
        "shift",
        "win",
        "windows",
        "cmd",
        "command",
        "super",
        "meta",
    }
)


class HotkeyConfig(BaseModel):
    """Configuration for :class:`HotkeyController`."""

    mode: Mode = "push_to_talk"
    binding: str = Field(default="ctrl+alt+space")
    min_hold_ms: int = Field(default=80, ge=0)
    cooldown_ms: int = Field(default=150, ge=0)


@dataclass(frozen=True)
class TriggerEvent:
    """Event emitted on ``on_start`` / ``on_stop``.

    ``started_at_ns`` is ``time.monotonic_ns()`` at the moment the
    trigger logically activated. On ``on_stop`` the field carries the
    ``started_at_ns`` of the matching ``on_start`` so downstream code
    can compute the hold duration without its own bookkeeping.
    """

    trigger_id: int
    mode: Mode
    started_at_ns: int
    reason: Reason = "hotkey"


StartCallback = Callable[[TriggerEvent], None]
StopCallback = Callable[[TriggerEvent], None]


def load_hotkey_config(path: Path | None = None) -> HotkeyConfig:
    """Load :class:`HotkeyConfig` from ``configs/hotkey.toml``."""
    target = path if path is not None else DEFAULT_CONFIG_PATH
    if not target.is_file():
        return HotkeyConfig()
    with target.open("rb") as f:
        data = tomllib.load(f)
    trigger = data.get("trigger", {}) or {}
    gates = data.get("gates", {}) or {}
    merged: dict[str, object] = {}
    for key in ("mode", "binding"):
        if key in trigger:
            merged[key] = trigger[key]
    for key in ("min_hold_ms", "cooldown_ms"):
        if key in gates:
            merged[key] = gates[key]
    return HotkeyConfig(**merged)


def parse_binding(binding: str) -> tuple[tuple[str, ...], str]:
    """Split ``"ctrl+alt+space"`` into ``(("ctrl", "alt"), "space")``.

    Returns ``(modifiers, trigger_key)``. Modifier names are kept in the
    same order the user wrote them so any subsequent ``keyboard`` call
    that needs the full binding can use the original string unchanged.
    """
    parts = [part.strip() for part in binding.split("+") if part.strip()]
    if not parts:
        raise ValueError(f"empty hotkey binding: {binding!r}")
    trigger = parts[-1].lower()
    modifiers = tuple(p.lower() for p in parts[:-1])
    return modifiers, trigger


class TriggerBus:
    """Thread-safe pub/sub with a dedicated dispatcher thread.

    Callbacks registered via :meth:`subscribe_start` /
    :meth:`subscribe_stop` are invoked on the bus worker thread, never
    on the ``keyboard`` hook thread. Subscriber exceptions are logged
    and swallowed so one bad callback cannot stall the bus.
    """

    _SHUTDOWN = object()

    def __init__(self) -> None:
        self._queue: queue.Queue[Any] = queue.Queue()
        self._start_subs: list[StartCallback] = []
        self._stop_subs: list[StopCallback] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._next_trigger_id = 1

    def subscribe_start(self, cb: StartCallback) -> None:
        with self._lock:
            self._start_subs.append(cb)

    def subscribe_stop(self, cb: StopCallback) -> None:
        with self._lock:
            self._stop_subs.append(cb)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._run,
                    name="sabi-trigger-bus",
                    daemon=True,
                )
                self._worker.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is TriggerBus._SHUTDOWN:
                return
            kind, event = item
            subs = (
                list(self._start_subs) if kind == "start" else list(self._stop_subs)
            )
            for cb in subs:
                try:
                    cb(event)
                except Exception:
                    logger.exception("trigger subscriber raised")

    def next_trigger_id(self) -> int:
        with self._lock:
            tid = self._next_trigger_id
            self._next_trigger_id += 1
            return tid

    def emit_start(self, event: TriggerEvent) -> None:
        self._ensure_worker()
        self._queue.put(("start", event))

    def emit_stop(self, event: TriggerEvent) -> None:
        self._ensure_worker()
        self._queue.put(("stop", event))

    def fire_start_cli(self, mode: Mode) -> TriggerEvent:
        event = TriggerEvent(
            trigger_id=self.next_trigger_id(),
            mode=mode,
            started_at_ns=time.monotonic_ns(),
            reason="cli",
        )
        self.emit_start(event)
        return event

    def fire_stop_cli(self, mode: Mode, start_event: TriggerEvent | None = None) -> TriggerEvent:
        started_at_ns = (
            start_event.started_at_ns if start_event is not None else time.monotonic_ns()
        )
        trigger_id = (
            start_event.trigger_id if start_event is not None else self.next_trigger_id()
        )
        event = TriggerEvent(
            trigger_id=trigger_id,
            mode=mode,
            started_at_ns=started_at_ns,
            reason="cli",
        )
        self.emit_stop(event)
        return event

    def shutdown(self, *, timeout: float = 1.0) -> None:
        with self._lock:
            worker = self._worker
        if worker is None:
            return
        self._queue.put(TriggerBus._SHUTDOWN)
        worker.join(timeout=timeout)


class HotkeyController:
    """Bind OS hotkeys to a :class:`TriggerBus` with min-hold + cooldown gates.

    Intended usage::

        with HotkeyController(HotkeyConfig()) as controller:
            controller.bus.subscribe_start(on_start)
            controller.bus.subscribe_stop(on_stop)
            ...

    ``keyboard_module`` is an injection seam for the test suite; real
    callers leave it ``None`` and the global ``keyboard`` package is
    imported lazily so that ``sabi.input`` can be imported on machines
    where the Windows hook is unavailable.
    """

    def __init__(
        self,
        config: HotkeyConfig,
        bus: TriggerBus | None = None,
        *,
        keyboard_module: Any | None = None,
    ) -> None:
        self.config = config
        self.bus = bus if bus is not None else TriggerBus()
        self._keyboard = keyboard_module
        self._modifiers, self._trigger_key = parse_binding(config.binding)
        self._hook_removers: list[Callable[[], None]] = []
        self._used_unhook_all = False
        self._lock = threading.Lock()
        self._started = False
        self._pending_start_timer: threading.Timer | None = None
        self._current_start: TriggerEvent | None = None
        self._last_start_mono: float = float("-inf")
        self._toggle_active = False
        self._last_toggle_press_mono: float = float("-inf")
        self._atexit_registered = False

    @property
    def keyboard(self) -> Any:
        if self._keyboard is None:
            import keyboard

            self._keyboard = keyboard
        return self._keyboard

    def start(self) -> "HotkeyController":
        with self._lock:
            if self._started:
                return self
            self._started = True
        if os.environ.get("SABI_SIDECAR_NO_HOTKEY") == "1":
            logger.info("hotkey controller disabled by SABI_SIDECAR_NO_HOTKEY")
            return self
        if self.config.mode == "push_to_talk":
            self._install_ptt_hooks()
        else:
            self._install_toggle_hooks()
        if not self._atexit_registered:
            proxy = weakref.proxy(self)

            def _cleanup() -> None:
                try:
                    proxy.stop()
                except ReferenceError:
                    return

            atexit.register(_cleanup)
            self._atexit_registered = True
        logger.info(
            "hotkey controller started: mode=%s binding=%s",
            self.config.mode,
            self.config.binding,
        )
        return self

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            self._started = False
            timer = self._pending_start_timer
            self._pending_start_timer = None
        if timer is not None:
            timer.cancel()
        removers = list(self._hook_removers)
        self._hook_removers.clear()
        if removers:
            for remove in removers:
                try:
                    remove()
                except Exception:
                    logger.exception("failed to remove keyboard hook")
        else:
            try:
                self.keyboard.unhook_all()
                self._used_unhook_all = True
            except Exception:
                logger.exception("keyboard.unhook_all failed")
        self.bus.shutdown()
        logger.info("hotkey controller stopped")

    def __enter__(self) -> "HotkeyController":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    def _install_ptt_hooks(self) -> None:
        trigger_handler_press = self._on_trigger_press
        trigger_handler_release = self._on_trigger_release
        self._add_remover(
            self.keyboard.on_press_key(self._trigger_key, trigger_handler_press)
        )
        self._add_remover(
            self.keyboard.on_release_key(self._trigger_key, trigger_handler_release)
        )
        modifier_handler = self._on_modifier_release
        for mod in self._modifiers:
            if mod in _MODIFIER_NAMES:
                self._add_remover(
                    self.keyboard.on_release_key(mod, modifier_handler)
                )

    def _install_toggle_hooks(self) -> None:
        self._add_remover(
            self.keyboard.add_hotkey(self.config.binding, self._on_toggle_press)
        )

    def _add_remover(self, handle: Any) -> None:
        if callable(handle):
            self._hook_removers.append(handle)

    def _chord_pressed(self) -> bool:
        try:
            return bool(self.keyboard.is_pressed(self.config.binding))
        except Exception:
            logger.debug("is_pressed failed", exc_info=True)
            return False

    def _on_trigger_press(self, _event: Any) -> None:
        if not self._chord_pressed():
            return
        with self._lock:
            if self._pending_start_timer is not None or self._current_start is not None:
                return
            timer = threading.Timer(
                self.config.min_hold_ms / 1000.0,
                self._fire_start_if_still_held,
            )
            timer.daemon = True
            self._pending_start_timer = timer
        timer.start()

    def _on_trigger_release(self, _event: Any) -> None:
        self._handle_release()

    def _on_modifier_release(self, _event: Any) -> None:
        if self._chord_pressed():
            return
        self._handle_release()

    def _handle_release(self) -> None:
        with self._lock:
            timer = self._pending_start_timer
            self._pending_start_timer = None
            current = self._current_start
            self._current_start = None
        if timer is not None:
            timer.cancel()
        if current is not None:
            self.bus.emit_stop(
                TriggerEvent(
                    trigger_id=current.trigger_id,
                    mode=current.mode,
                    started_at_ns=current.started_at_ns,
                    reason="hotkey",
                )
            )

    def _fire_start_if_still_held(self) -> None:
        if not self._chord_pressed():
            with self._lock:
                self._pending_start_timer = None
            return
        now_mono = time.monotonic()
        with self._lock:
            if not self._started:
                return
            cooldown_s = self.config.cooldown_ms / 1000.0
            if now_mono - self._last_start_mono < cooldown_s:
                self._pending_start_timer = None
                return
            event = TriggerEvent(
                trigger_id=self.bus.next_trigger_id(),
                mode=self.config.mode,
                started_at_ns=time.monotonic_ns(),
                reason="hotkey",
            )
            self._current_start = event
            self._last_start_mono = now_mono
            self._pending_start_timer = None
        self.bus.emit_start(event)

    def _on_toggle_press(self) -> None:
        now_mono = time.monotonic()
        with self._lock:
            if not self._started:
                return
            if now_mono - self._last_toggle_press_mono < self.config.min_hold_ms / 1000.0:
                return
            self._last_toggle_press_mono = now_mono
            if self._toggle_active:
                current = self._current_start
                self._current_start = None
                self._toggle_active = False
                stop_event = (
                    TriggerEvent(
                        trigger_id=current.trigger_id if current else self.bus.next_trigger_id(),
                        mode=self.config.mode,
                        started_at_ns=current.started_at_ns if current else time.monotonic_ns(),
                        reason="hotkey",
                    )
                )
                self.bus.emit_stop(stop_event)
                return
            cooldown_s = self.config.cooldown_ms / 1000.0
            if now_mono - self._last_start_mono < cooldown_s:
                return
            event = TriggerEvent(
                trigger_id=self.bus.next_trigger_id(),
                mode=self.config.mode,
                started_at_ns=time.monotonic_ns(),
                reason="hotkey",
            )
            self._current_start = event
            self._toggle_active = True
            self._last_start_mono = now_mono
        self.bus.emit_start(event)


def run_hotkey_debug(config: HotkeyConfig) -> int:
    """Print ``[TRIGGER START]`` / ``[TRIGGER STOP]`` lines until Ctrl+C.

    Shared between ``python -m sabi hotkey-debug`` and the
    ``scripts/hotkey_debug.py`` shim so both paths exercise the same
    code.
    """
    print(
        f"sabi hotkey-debug: mode={config.mode} binding={config.binding} "
        f"min_hold_ms={config.min_hold_ms} cooldown_ms={config.cooldown_ms}"
    )
    print("Press the hotkey. Ctrl+C to exit.")

    def on_start(event: TriggerEvent) -> None:
        print(
            f"[TRIGGER START] id={event.trigger_id} mode={event.mode} "
            f"reason={event.reason} t_ns={event.started_at_ns}"
        )

    def on_stop(event: TriggerEvent) -> None:
        dur_ms = (time.monotonic_ns() - event.started_at_ns) / 1e6
        print(
            f"[TRIGGER STOP]  id={event.trigger_id} mode={event.mode} "
            f"reason={event.reason} held_ms={dur_ms:.1f}"
        )

    with HotkeyController(config) as controller:
        controller.bus.subscribe_start(on_start)
        controller.bus.subscribe_stop(on_stop)
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nexiting...")
    return 0


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "HotkeyConfig",
    "HotkeyController",
    "TriggerBus",
    "TriggerEvent",
    "load_hotkey_config",
    "parse_binding",
    "run_hotkey_debug",
]
