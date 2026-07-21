"""Pure merge rule -- combine the activity state and the focused window into one sample.

This is the logic of build-plan Step 3.1, kept free of hardware so the rule itself is
unit-testable. The rule: **when idle, suppress the app entirely** -- you are not "in"
anything if you have walked away. While active, the sample carries the focused app (and
title, if captured); the desktop / no-window case is reported as active-but-appless.
"""

from __future__ import annotations

from dataclasses import dataclass

from timekeeper.activity.monitor import ActivityState
from timekeeper.focus.identity import WindowIdentity


@dataclass(frozen=True)
class MergedSample:
    """One instant of "what am I doing": active or not, and (if active) in which app."""

    active: bool
    app_class: str | None  # None while idle (suppressed) or on the bare desktop
    title: str | None

    @property
    def line(self) -> str:
        if not self.active:
            return "— idle"
        app = self.app_class or "(desktop)"
        if self.title:
            return f"{app} — active — {self.title}"
        return f"{app} — active"


def merge(state: ActivityState, identity: WindowIdentity) -> MergedSample:
    """Apply the merge rule to a live activity state + focused-window identity."""
    if state is ActivityState.IDLE:
        # Suppress the app: away means not "in" anything.
        return MergedSample(active=False, app_class=None, title=None)
    if identity.is_none:
        return MergedSample(active=True, app_class=None, title=None)
    return MergedSample(active=True, app_class=identity.app_class, title=identity.title)
