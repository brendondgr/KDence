"""Step 2.2/2.3 (synthetic) -- pure tests for FocusReporter fidelity.

The reporter's job: always hold the current window, emit a change exactly once per
genuine switch (no drops) and never for a repeat of the same window (no duplicates).
The *source's* fidelity under real rapid switching is the live check; here we prove the
reporter faithfully mirrors whatever stream it is fed.
"""

from __future__ import annotations

from timekeeper.focus.identity import NO_WINDOW, WindowIdentity
from timekeeper.focus.reporter import FocusReporter


def test_starts_on_no_window() -> None:
    assert FocusReporter().current is NO_WINDOW


def test_update_sets_current() -> None:
    reporter = FocusReporter()
    reporter.update("firefox", "whatever")
    assert reporter.current == WindowIdentity("firefox", None)


def test_change_stream_has_no_drops_or_duplicates() -> None:
    changes: list[WindowIdentity] = []
    reporter = FocusReporter(on_change=changes.append)
    # Rapid switching: a..b..b..c..c..a  (b and c each repeated = re-activation).
    for cls in ["a", "b", "b", "c", "c", "a"]:
        reporter.update(cls)
    # Every genuine switch fired once; the repeats fired nothing.
    assert [c.app_class for c in changes] == ["a", "b", "c", "a"]
    assert reporter.current == WindowIdentity("a", None)


def test_empty_title_window_is_handled() -> None:
    reporter = FocusReporter(capture_titles=True)
    ident = reporter.update("code", "")
    assert ident == WindowIdentity("code", None)  # empty caption -> no title, no crash


def test_desktop_focus_is_no_window() -> None:
    changes: list[WindowIdentity] = []
    reporter = FocusReporter(on_change=changes.append)
    reporter.update("firefox")
    reporter.update("")  # focus goes to the desktop
    assert reporter.current is NO_WINDOW
    assert changes[-1] is NO_WINDOW


def test_title_only_switch_is_invisible_when_titles_off() -> None:
    # Same app, different document: no change when titles are not captured (privacy),
    # but a change when they are (you really did switch documents).
    off_changes: list[WindowIdentity] = []
    off = FocusReporter(capture_titles=False, on_change=off_changes.append)
    off.update("code", "a.py")
    off.update("code", "b.py")
    assert [c.app_class for c in off_changes] == ["code"]  # one change, not two

    on_changes: list[WindowIdentity] = []
    on = FocusReporter(capture_titles=True, on_change=on_changes.append)
    on.update("code", "a.py")
    on.update("code", "b.py")
    assert [c.title for c in on_changes] == ["a.py", "b.py"]  # both switches seen
