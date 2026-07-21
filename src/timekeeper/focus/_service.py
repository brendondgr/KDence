"""The DBus object KWin's script calls back into (kept separate on purpose).

This module must NOT use ``from __future__ import annotations``: ``dbus-fast``
introspects the ``@method`` parameter annotations at runtime to derive the DBus
signature, and PEP 563 would turn ``'s'`` into an unusable string. So the interface
lives here, apart from :mod:`timekeeper.focus.kwin_source` (which does use future
annotations for its own forward references).
"""

from collections.abc import Callable

from dbus_fast.service import ServiceInterface, method

INTERFACE = "org.timekeeper.Focus"


class FocusInterface(ServiceInterface):
    """Receives ``Report(tag, app_class, title)`` calls from the KWin script."""

    def __init__(self, on_focus: Callable[[str, str], None]) -> None:
        super().__init__(INTERFACE)
        self._on_focus = on_focus

    @method()
    def Report(self, tag: "s", app_class: "s", title: "s"):  # noqa: F821, UP037
        # `tag` marks the initial report vs. later activations; the reporter ignores it
        # but it is handy when watching the wire. Void method -> empty out-signature.
        self._on_focus(app_class, title)
