"""Pure window-identity model -- no compositor, no DBus, fully unit-testable.

This is the logic side of the focus seam. The hardware side
(:mod:`timekeeper.focus.kwin_source`) only forwards raw ``resourceClass`` +
``caption`` strings out of KWin; deciding *what a window is* to this system --
which fields we keep and whether titles are captured -- happens here.

Privacy stance (build-plan Step 2.2): the **app class** is always kept -- it names
the application (e.g. ``firefox``, ``org.kde.konsole``) and leaks little. The
**title** is opt-in and defaults to *off*, because captions leak document names and
URLs (the global privacy rule: default to the more private option). Flip
``capture_titles=True`` to record them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowIdentity:
    """A focused window reduced to the fields this system stores.

    ``app_class`` is the compositor's ``resourceClass``. An empty ``app_class`` is the
    canonical "no window" identity (the desktop, or focus on nothing). ``title`` is
    ``None`` when title capture is disabled or the window has no caption.
    """

    app_class: str
    title: str | None = None

    @property
    def is_none(self) -> bool:
        """True when nothing is focused (the desktop / focus on nothing)."""
        return self.app_class == ""

    @property
    def label(self) -> str:
        """A human-readable one-liner, respecting whatever title we actually hold."""
        if self.is_none:
            return "(no window)"
        if self.title:
            return f"{self.app_class} — {self.title}"
        return self.app_class


# The single canonical "focus on nothing" value; compares equal across the system.
NO_WINDOW = WindowIdentity("", None)


def make_identity(app_class: str, title: str | None, *, capture_titles: bool) -> WindowIdentity:
    """Build a :class:`WindowIdentity` from raw compositor strings, applying policy.

    Normalises whitespace, collapses an empty class to :data:`NO_WINDOW`, and drops the
    title entirely unless ``capture_titles`` is set (the privacy default is *off*).
    """
    app_class = (app_class or "").strip()
    if not app_class:
        return NO_WINDOW
    if not capture_titles:
        return WindowIdentity(app_class, None)
    caption = (title or "").strip()
    return WindowIdentity(app_class, caption or None)
