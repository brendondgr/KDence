"""The hardware side of MPRIS detail: read now-playing metadata off the session bus.

Each MPRIS player owns a bus name ``org.mpris.MediaPlayer2.<id>[.instanceN]`` and exposes
``Metadata`` + ``PlaybackStatus`` on ``org.mpris.MediaPlayer2.Player`` at ``/org/mpris/
MediaPlayer2``. This source enumerates the live players and reads those properties into the pure
:class:`~kdence.detail.mpris.tracker.MprisTracker` via the pure
:func:`~kdence.detail.mpris.policy.label_for`. No logic lives here beyond D-Bus plumbing +
variant unwrapping.

**Polling, not signals.** Like the Phase 6 live view (which polls rather than streams), this
refreshes on the collector's own interval instead of subscribing to ``PropertiesChanged``. That
trades up-to-one-interval latency for a great deal of simplicity and robustness: no fragile
unique-name → well-known-name bookkeeping across ``NameOwnerChanged``, and a crashed player just
stops appearing. ``dbus-fast`` is already a dependency (Phase 2), so this adds none.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from dbus_fast import Message, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import MessageType

from kdence.detail.mpris.policy import label_for
from kdence.detail.mpris.tracker import MprisTracker

_MPRIS_PREFIX = "org.mpris.MediaPlayer2."
_MPRIS_PATH = "/org/mpris/MediaPlayer2"
_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
_PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
_DBUS_SERVICE = "org.freedesktop.DBus"
_DBUS_PATH = "/org/freedesktop/DBus"


def player_identifier(bus_name: str) -> str:
    """The tracker key for a player bus name: the id with any ``.instanceN`` suffix dropped.

    ``org.mpris.MediaPlayer2.firefox.instance_1_15`` -> ``firefox``; ``...vlc`` -> ``vlc``.
    """
    tail = bus_name[len(_MPRIS_PREFIX) :] if bus_name.startswith(_MPRIS_PREFIX) else bus_name
    return tail.split(".", 1)[0].strip().lower()


def _unwrap(value: Any) -> Any:
    """Recursively turn ``dbus-fast`` ``Variant``/containers into plain Python values."""
    if isinstance(value, Variant):
        return _unwrap(value.value)
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


class MprisSource:
    """Poll live MPRIS players and feed their now-playing labels into an :class:`MprisTracker`.

    Args:
        tracker: the pure tracker to report into.
        clock: wall-clock source (injectable for tests); defaults to :func:`time.time`.

    Async lifecycle: ``await connect()``, then ``await refresh()`` once per collector interval,
    and ``await close()`` (or ``async with``) at shutdown. Requires a live session bus.
    """

    def __init__(self, tracker: MprisTracker, clock: Callable[[], float] = time.time) -> None:
        self._tracker = tracker
        self._clock = clock
        self._bus: MessageBus | None = None
        self._seen: set[str] = set()

    async def connect(self) -> MprisSource:
        self._bus = await MessageBus().connect()
        return self

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None

    async def __aenter__(self) -> MprisSource:
        return await self.connect()

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def refresh(self) -> None:
        """Re-read every live player's now-playing item into the tracker; forget vanished ones."""
        if self._bus is None:
            return
        players = [n for n in await self._list_names() if n.startswith(_MPRIS_PREFIX)]
        now = self._clock()
        current: set[str] = set()
        for name in players:
            pid = player_identifier(name)
            current.add(pid)
            metadata, status = await self._player_props(name)
            self._tracker.report(pid, label_for(metadata, status), now)
        # A player that disappeared from the bus should stop being attributed immediately
        # (the TTL would eventually handle it, but forgetting is cleaner).
        for gone in self._seen - current:
            self._tracker.forget(gone)
        self._seen = current

    # -- D-Bus plumbing --------------------------------------------------------

    async def _list_names(self) -> list[str]:
        assert self._bus is not None
        reply = await self._bus.call(
            Message(
                destination=_DBUS_SERVICE,
                path=_DBUS_PATH,
                interface=_DBUS_SERVICE,
                member="ListNames",
                signature="",
                body=[],
            )
        )
        if reply is None or reply.message_type is MessageType.ERROR:
            return []
        return list(reply.body[0]) if reply.body else []

    async def _get(self, name: str, prop: str) -> Any:
        assert self._bus is not None
        reply = await self._bus.call(
            Message(
                destination=name,
                path=_MPRIS_PATH,
                interface=_PROPERTIES_IFACE,
                member="Get",
                signature="ss",
                body=[_PLAYER_IFACE, prop],
            )
        )
        if reply is None or reply.message_type is MessageType.ERROR or not reply.body:
            return None
        return _unwrap(reply.body[0])

    async def _player_props(self, name: str) -> tuple[dict[str, Any] | None, str | None]:
        metadata = await self._get(name, "Metadata")
        status = await self._get(name, "PlaybackStatus")
        meta = metadata if isinstance(metadata, dict) else None
        return meta, status if isinstance(status, str) else None
