"""Step 1.2 (live) -- automated smoke test for the Wayland idle source.

Marked ``live``: it needs a real KDE Plasma 6 / Wayland session and is skipped in
headless CI (``uv run pytest -m "not live"``). It proves the ``idled`` half of the
protocol end to end: the test process produces no seat input, so after the timeout the
compositor sends ``idled``. The ``resumed``/keyboard-only half cannot be automated
without synthesising input and stays a manual check (see the Phase 1 handoff).
"""

from __future__ import annotations

import select
import time

import pytest

from kdence.activity.wayland_idle import WaylandIdleSource

pytestmark = pytest.mark.live


def test_connects_and_binds_idle_notifier() -> None:
    # Connecting requires the compositor to advertise wl_seat + ext_idle_notifier_v1
    # and accept the get_idle_notification request without a protocol error.
    with WaylandIdleSource(resolution_ms=1000) as source:
        assert source.fileno() >= 0


def test_idled_fires_when_no_input() -> None:
    events: list[str] = []
    source = WaylandIdleSource(
        resolution_ms=1000,
        on_idled=lambda: events.append("idled"),
        on_resumed=lambda: events.append("resumed"),
    )
    with source:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and "idled" not in events:
            ready, _, _ = select.select([source.fileno()], [], [], 0.5)
            if ready:
                source.dispatch()
    assert "idled" in events, "compositor did not report idle within 5s of no input"
