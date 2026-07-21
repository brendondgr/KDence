"""Pure focus reporter -- always holds "the currently focused window."

Fed raw ``(app_class, title)`` transitions from any source (real KWin or a fake in a
test), it applies the identity/privacy policy and remembers the current window. It
emits an ``on_change`` callback only when the identity *actually* changes, so
re-activating the same window (e.g. alt-tab back) does not produce a duplicate event,
while every genuine switch does (no drops). This is the "reporter component" of
build-plan Step 2.3, with zero hardware so its fidelity is unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable

from kdence.focus.identity import NO_WINDOW, WindowIdentity, make_identity


class FocusReporter:
    """Track the current focused window, de-duplicating unchanged activations.

    Args:
        capture_titles: whether to keep window titles (default off; see
            :func:`~kdence.focus.identity.make_identity`).
        on_change: called with the new :class:`WindowIdentity` whenever the current
            identity changes (never for a repeat of the same identity).
    """

    def __init__(
        self,
        *,
        capture_titles: bool = False,
        on_change: Callable[[WindowIdentity], None] | None = None,
    ) -> None:
        self._capture_titles = capture_titles
        self._on_change = on_change
        self._current: WindowIdentity = NO_WINDOW

    @property
    def current(self) -> WindowIdentity:
        return self._current

    @property
    def capture_titles(self) -> bool:
        return self._capture_titles

    def update(self, app_class: str, title: str | None = None) -> WindowIdentity:
        """Record an activation; fire ``on_change`` iff the identity actually changed."""
        new = make_identity(app_class, title, capture_titles=self._capture_titles)
        if new != self._current:
            self._current = new
            if self._on_change is not None:
                self._on_change(new)
        return new
