"""Step 3.1 (synthetic) -- pure tests for the activity+focus merge rule."""

from __future__ import annotations

from timekeeper.activity.monitor import ActivityState
from timekeeper.collector.merge import merge
from timekeeper.focus.identity import NO_WINDOW, WindowIdentity


def test_idle_suppresses_the_app() -> None:
    # Even with a window focused, being idle means "not in anything."
    sample = merge(ActivityState.IDLE, WindowIdentity("firefox", None))
    assert sample.active is False
    assert sample.app_class is None
    assert sample.line == "— idle"


def test_active_reports_the_focused_app() -> None:
    sample = merge(ActivityState.ACTIVE, WindowIdentity("firefox", None))
    assert sample.active is True
    assert sample.app_class == "firefox"
    assert sample.line == "firefox — active"


def test_active_on_the_desktop_is_appless_but_active() -> None:
    sample = merge(ActivityState.ACTIVE, NO_WINDOW)
    assert sample.active is True
    assert sample.app_class is None
    assert sample.line == "(desktop) — active"


def test_title_appears_in_the_line_when_present() -> None:
    sample = merge(ActivityState.ACTIVE, WindowIdentity("code", "main.py"))
    assert sample.title == "main.py"
    assert sample.line == "code — active — main.py"


# -- browser site sub-identity ------------------------------------------------


def test_active_browser_carries_the_resolved_site() -> None:
    sample = merge(ActivityState.ACTIVE, WindowIdentity("librewolf", None), "youtube.com")
    assert sample.active is True
    assert sample.app_class == "librewolf"
    assert sample.site == "youtube.com"
    assert sample.line == "librewolf — active — youtube.com"


def test_idle_suppresses_the_site_too() -> None:
    sample = merge(ActivityState.IDLE, WindowIdentity("librewolf", None), "youtube.com")
    assert sample.active is False
    assert sample.site is None


def test_no_site_leaves_a_plain_active_sample() -> None:
    sample = merge(ActivityState.ACTIVE, WindowIdentity("code", None), None)
    assert sample.site is None
    assert sample.line == "code — active"
