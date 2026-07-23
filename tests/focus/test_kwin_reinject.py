"""Headless tests for the focus-script liveness re-inject (Phase 13.3).

The DBus/KWin calls are stubbed, so only the *decision* is exercised (no live session): an
evicted script is re-injected, a loaded one is left alone, and an unreadable state never
triggers a re-inject storm. This is the fix for the focus-freeze bug (an evicted script
silently freezes focus and mislabels hours).
"""

from __future__ import annotations

import asyncio

from kdence.focus.kwin_source import KWinFocusSource


class _Probe(KWinFocusSource):
    def __init__(self, loaded_returns) -> None:
        super().__init__(on_focus=lambda _c, _t: None)
        self._bus = object()  # pretend connected
        self._script_path = "/tmp/fake.js"
        self._loaded_returns = list(loaded_returns)
        self.injected = 0

    async def _is_loaded(self) -> bool:
        v = self._loaded_returns.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    async def _inject(self) -> None:
        self.injected += 1


def test_evicted_script_is_reinjected() -> None:
    probe = _Probe([False])
    assert asyncio.run(probe.ensure_loaded()) is True
    assert probe.injected == 1


def test_loaded_script_is_left_alone() -> None:
    probe = _Probe([True])
    assert asyncio.run(probe.ensure_loaded()) is True
    assert probe.injected == 0


def test_unreadable_state_does_not_reinject() -> None:
    probe = _Probe([RuntimeError("dbus hiccup")])
    assert asyncio.run(probe.ensure_loaded()) is True
    assert probe.injected == 0


def test_no_bus_is_a_noop() -> None:
    src = KWinFocusSource(on_focus=lambda _c, _t: None)  # never connected -> no bus
    assert asyncio.run(src.ensure_loaded()) is False
