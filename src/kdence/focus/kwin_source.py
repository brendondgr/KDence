"""The hardware side of focus detection: get KWin to report the focused window.

On Plasma 6 / Wayland there is no simple DBus property for "the active window's
class." The sanctioned path is a **KWin script**: we load a tiny script into the
compositor (over ``org.kde.kwin.Scripting``) that connects to
``workspace.windowActivated`` and calls back out via ``callDBus`` -- the only reliable
egress from KWin's sandboxed script engine. We host the receiving end here as a small,
**local** DBus service (``org.kdence.Focus``) using ``dbus-fast``.

This module carries no identity or privacy logic -- it forwards raw
``(resourceClass, caption)`` strings to ``on_focus``. The policy lives in the pure
:mod:`kdence.focus.identity` / :mod:`kdence.focus.reporter`.

Proven live in build-plan Step 2.1: the script reports the real focused window and
every focus change, out of the compositor, to this service. See
docs/plans/phase-0-platform-notes.md for the platform facts.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from importlib import resources

from dbus_fast import Message
from dbus_fast.aio import MessageBus
from dbus_fast.constants import MessageType

from kdence.focus._service import INTERFACE as _INTERFACE
from kdence.focus._service import FocusInterface

# Our private receiver (local-only; not a public API).
_SERVICE_NAME = "org.kdence.Focus"
_OBJECT_PATH = "/org/kdence/Focus"

# KWin's scripting entry point (introspected on Plasma 6.7).
_KWIN_SERVICE = "org.kde.KWin"
_SCRIPTING_PATH = "/Scripting"
_SCRIPTING_IFACE = "org.kde.kwin.Scripting"
_PLUGIN_NAME = "kdence-focus"

_SCRIPT_RESOURCE = "kwin_focus_report.js"


class KWinFocusSource:
    """Load the focus-reporting KWin script and surface its activations.

    Args:
        on_focus: called with ``(app_class, title)`` for the initially focused window
            and on every focus change. Both are raw compositor strings; an empty
            ``app_class`` means focus went to the desktop.

    Async lifecycle: ``await connect()`` then let the event loop run; call
    ``await close()`` (or use ``async with``) to unload the script and drop the DBus
    name. Requires a live KDE Plasma 6 / Wayland session.
    """

    def __init__(self, on_focus: Callable[[str, str], None]) -> None:
        self._on_focus = on_focus
        self._bus: MessageBus | None = None
        self._script_path: str | None = None

    async def connect(self) -> KWinFocusSource:
        self._bus = await MessageBus().connect()
        self._bus.export(_OBJECT_PATH, FocusInterface(self._on_focus))
        await self._bus.request_name(_SERVICE_NAME)

        self._script_path = self._write_script()
        # Drop any stale instance from a previous (possibly crashed) run first.
        await self._call_scripting("unloadScript", "s", [_PLUGIN_NAME], tolerant=True)
        await self._call_scripting("loadScript", "ss", [self._script_path, _PLUGIN_NAME])
        await self._call_scripting("start", "", [])
        return self

    async def close(self) -> None:
        if self._bus is not None:
            await self._call_scripting("unloadScript", "s", [_PLUGIN_NAME], tolerant=True)
            self._bus.disconnect()
            self._bus = None
        if self._script_path is not None:
            try:
                os.unlink(self._script_path)
            except OSError:
                pass
            self._script_path = None

    async def __aenter__(self) -> KWinFocusSource:
        return await self.connect()

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # -- internals -----------------------------------------------------------
    def _write_script(self) -> str:
        template = resources.files("kdence.focus").joinpath(_SCRIPT_RESOURCE).read_text()
        script = (
            template.replace("%SERVICE%", _SERVICE_NAME)
            .replace("%PATH%", _OBJECT_PATH)
            .replace("%IFACE%", _INTERFACE)
        )
        # KWin's loadScript reads a filesystem path, so materialise the script. It must
        # survive until unload; close() removes it.
        fd, path = tempfile.mkstemp(prefix="kdence-focus-", suffix=".js")
        with os.fdopen(fd, "w") as handle:
            handle.write(script)
        return path

    async def _call_scripting(
        self, member: str, signature: str, body: list[object], *, tolerant: bool = False
    ) -> None:
        assert self._bus is not None
        reply = await self._bus.call(
            Message(
                destination=_KWIN_SERVICE,
                path=_SCRIPTING_PATH,
                interface=_SCRIPTING_IFACE,
                member=member,
                signature=signature,
                body=body,
            )
        )
        if reply is not None and reply.message_type is MessageType.ERROR and not tolerant:
            raise RuntimeError(f"KWin {member} failed: {reply.error_name}: {reply.body}")
