"""Step 1.2 (synthetic) -- pure-logic tests for ActivityMonitor.

No Wayland, no hardware: fake transitions and a fake clock. This is where activity
correctness is proven; the live session only needs to confirm the idle *source* fires.
"""

from __future__ import annotations

import pytest

from timekeeper.activity import ActivityMonitor, ActivityState

# A small threshold/resolution keeps the arithmetic obvious. `resolution=1` means an
# `idled` transition implies input actually stopped 1s earlier (back-dating).
THRESHOLD = 5.0
RESOLUTION = 1.0


def make_monitor() -> ActivityMonitor:
    # clock is unused when we pass explicit timestamps, but must be present.
    return ActivityMonitor(THRESHOLD, RESOLUTION, clock=lambda: 0.0)


def test_active_by_default() -> None:
    monitor = make_monitor()
    assert monitor.state_at(now=0.0) is ActivityState.ACTIVE
    assert monitor.idle_seconds(now=100.0) == 0.0


def test_flips_to_idle_exactly_at_threshold() -> None:
    monitor = make_monitor()
    monitor.mark_idled(at=1.0)  # input stopped ~t=0.0 (back-dated by resolution)

    # Below threshold -> still ACTIVE.
    assert monitor.state_at(now=1.0) is ActivityState.ACTIVE
    assert monitor.state_at(now=0.0 + THRESHOLD - 0.01) is ActivityState.ACTIVE
    # At/after the threshold -> IDLE. Idle started at t=0.0, so it crosses at t=5.0.
    assert monitor.state_at(now=0.0 + THRESHOLD) is ActivityState.IDLE
    assert monitor.state_at(now=100.0) is ActivityState.IDLE


def test_idled_is_back_dated_by_resolution() -> None:
    # The compositor only tells us after `resolution` of inactivity; the active span
    # must end near last input, not near detection. At the instant `idled` arrives we
    # are already `resolution` seconds idle.
    monitor = make_monitor()
    monitor.mark_idled(at=10.0)
    assert monitor.idle_seconds(now=10.0) == pytest.approx(RESOLUTION)
    assert monitor.idle_seconds(now=13.5) == pytest.approx(3.5 + RESOLUTION)


def test_resume_resets_to_active() -> None:
    monitor = make_monitor()
    monitor.mark_idled(at=1.0)
    assert monitor.state_at(now=100.0) is ActivityState.IDLE
    monitor.mark_resumed(at=101.0)
    assert monitor.state_at(now=101.0) is ActivityState.ACTIVE
    assert monitor.idle_seconds(now=200.0) == 0.0


def test_flapping_below_threshold_never_reports_idle() -> None:
    # A brief pause (shorter than the threshold) then resumed input must stay ACTIVE.
    monitor = make_monitor()
    monitor.mark_idled(at=1.0)
    monitor.mark_resumed(at=2.5)  # idle lasted ~2.5s < 5s threshold
    assert monitor.state_at(now=3.0) is ActivityState.ACTIVE
    assert monitor.state_at(now=1000.0) is ActivityState.ACTIVE


def test_any_resume_signal_resets_regardless_of_input_device() -> None:
    # Keyboard-only vs mouse-only is a live/manual check, but the logic treats a single
    # seat-level `resumed` as the reset -- there is only one signal to react to.
    monitor = make_monitor()
    monitor.mark_idled(at=0.0)
    assert monitor.state_at(now=50.0) is ActivityState.IDLE
    monitor.mark_resumed()  # e.g. a keypress
    assert monitor.is_active is True


def test_default_clock_is_used_when_now_is_omitted() -> None:
    fake_time = {"t": 0.0}
    monitor = ActivityMonitor(THRESHOLD, RESOLUTION, clock=lambda: fake_time["t"])
    monitor.mark_idled()  # at = clock() = 0.0 -> idle_since = -1.0 (back-dated)
    fake_time["t"] = 3.5
    assert monitor.idle_seconds() == pytest.approx(4.5)  # 3.5 - (-1.0)
    assert monitor.state_at() is ActivityState.ACTIVE  # 4.5 < 5.0 threshold
    fake_time["t"] = 4.0
    assert monitor.state_at() is ActivityState.IDLE  # 5.0 >= 5.0 threshold


@pytest.mark.parametrize("bad", [0, -1, -0.5])
def test_rejects_nonpositive_threshold(bad: float) -> None:
    with pytest.raises(ValueError):
        ActivityMonitor(bad, RESOLUTION)


@pytest.mark.parametrize("bad", [0, -1, -0.5])
def test_rejects_nonpositive_resolution(bad: float) -> None:
    with pytest.raises(ValueError):
        ActivityMonitor(THRESHOLD, bad)
