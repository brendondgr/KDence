"""A ``ext_idle_notifier_v1`` client written against the Wayland wire protocol.

Why hand-rolled and stdlib-only: on KDE Plasma 6 / Wayland there is no idle-time
counter over DBus (``org.freedesktop.ScreenSaver.GetSessionIdleTime`` returns
``NotSupported``). The honest source is the compositor's ``ext_idle_notifier_v1``
protocol, which is *event based* -- request a notification with a timeout and the
compositor sends ``idled`` after that much seat inactivity and ``resumed`` on the
next input. ``pywayland`` would speak this too, but it compiles a CFFI extension
needing system dev headers (a ``sudo`` step); this module needs only the standard
library, no compiler, no DBus.

This is deliberately the *hardware* side of the pure/hardware seam: it carries no
threshold logic. It only surfaces raw ``idled``/``resumed`` transitions. The
decision logic lives in :mod:`timekeeper.activity.monitor`.

Protocol reference (vendored): ``docs/references/protocols/ext-idle-notify-v1.xml``.
Wayland wire format reference: https://wayland-book.com/protocol-design/wire-protocol.html
"""

from __future__ import annotations

import os
import socket
import struct
from collections.abc import Callable

# --- Wayland object ids / opcodes -------------------------------------------
# wl_display is always object id 1; the client allocates ids from 2 upward.
_DISPLAY_ID = 1

# wl_display requests / events
_WL_DISPLAY_SYNC = 0
_WL_DISPLAY_GET_REGISTRY = 1
_WL_DISPLAY_ERROR = 0  # event
_WL_DISPLAY_DELETE_ID = 1  # event

# wl_registry request / events
_WL_REGISTRY_BIND = 0
_WL_REGISTRY_GLOBAL = 0  # event
_WL_REGISTRY_GLOBAL_REMOVE = 1  # event

# wl_callback event
_WL_CALLBACK_DONE = 0

# ext_idle_notifier_v1 requests: destroy=0, get_idle_notification=1 (opcode order
# matters -- destroy is the first request, so get_idle_notification is opcode 1).
_NOTIFIER_GET_IDLE_NOTIFICATION = 1

# ext_idle_notification_v1 events
_NOTIFICATION_IDLED = 0
_NOTIFICATION_RESUMED = 1

_SEAT_INTERFACE = "wl_seat"
_NOTIFIER_INTERFACE = "ext_idle_notifier_v1"


class WaylandProtocolError(RuntimeError):
    """Raised when the compositor sends a ``wl_display.error`` event."""

    def __init__(self, object_id: int, code: int, message: str) -> None:
        super().__init__(f"wl_display.error object={object_id} code={code}: {message}")
        self.object_id = object_id
        self.code = code
        self.message = message


def _pad4(n: int) -> int:
    """Round *n* up to the next 4-byte boundary (Wayland pads args to 32 bits)."""
    return (n + 3) & ~3


def _encode_string(value: str) -> bytes:
    """Encode a Wayland string arg: uint length (incl. NUL), bytes, NUL, pad."""
    raw = value.encode("utf-8") + b"\x00"
    length = len(raw)
    return struct.pack("=I", length) + raw + b"\x00" * (_pad4(length) - length)


def _message(object_id: int, opcode: int, body: bytes = b"") -> bytes:
    """Frame a request: 8-byte header (id, (size<<16)|opcode) then the body."""
    size = 8 + len(body)
    return struct.pack("=II", object_id, (size << 16) | opcode) + body


class _Connection:
    """A minimal framed connection to the Wayland unix socket (host byte order)."""

    def __init__(self) -> None:
        self._sock = self._connect()
        self._buf = b""
        self._next_id = 2  # 1 is wl_display

    @staticmethod
    def _connect() -> socket.socket:
        display = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
        if os.path.isabs(display):
            path = display
        else:
            runtime = os.environ.get("XDG_RUNTIME_DIR")
            if not runtime:
                raise RuntimeError("XDG_RUNTIME_DIR is not set -- no Wayland session to connect to")
            path = os.path.join(runtime, display)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
        sock.connect(path)
        return sock

    def new_id(self) -> int:
        allocated = self._next_id
        self._next_id += 1
        return allocated

    def send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def fileno(self) -> int:
        return self._sock.fileno()

    def messages(self, *, block: bool):
        """Read once, then yield every complete ``(object_id, opcode, body)`` buffered.

        With ``block=True`` this waits for at least one chunk; with ``block=False`` it
        returns whatever is already available (possibly nothing).
        """
        self._sock.setblocking(block)
        try:
            chunk = self._sock.recv(4096)
        except BlockingIOError:
            chunk = b""
        else:
            if not chunk:
                raise ConnectionError("Wayland compositor closed the connection")
        self._buf += chunk

        while len(self._buf) >= 8:
            object_id, word = struct.unpack("=II", self._buf[:8])
            size = word >> 16
            opcode = word & 0xFFFF
            if size < 8 or len(self._buf) < size:
                break  # wait for the rest of a partial message
            body = self._buf[8:size]
            self._buf = self._buf[size:]
            yield object_id, opcode, body

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


class WaylandIdleSource:
    """Subscribe to seat idle transitions via ``ext_idle_notifier_v1``.

    Args:
        resolution_ms: the timeout handed to the compositor. ``idled`` fires after
            this much seat inactivity; small values detect idle-start promptly. This
            is intentionally *not* the user's idle threshold -- the threshold is
            applied by :class:`~timekeeper.activity.monitor.ActivityMonitor`.
        on_idled: called with no args when the seat becomes idle.
        on_resumed: called with no args when input resumes.

    Use as a context manager, then drive it with :meth:`dispatch` (typically from a
    ``select`` loop on :meth:`fileno`).
    """

    def __init__(
        self,
        resolution_ms: int = 1000,
        *,
        on_idled: Callable[[], None] | None = None,
        on_resumed: Callable[[], None] | None = None,
    ) -> None:
        if resolution_ms <= 0:
            raise ValueError("resolution_ms must be positive")
        self._resolution_ms = int(resolution_ms)
        self.on_idled = on_idled
        self.on_resumed = on_resumed
        self._conn: _Connection | None = None
        self._registry_id: int | None = None
        self._seat_id: int | None = None
        self._notifier_id: int | None = None
        self._notification_id: int | None = None
        self._globals: dict[str, tuple[int, int]] = {}
        self._error: WaylandProtocolError | None = None

    # -- lifecycle -----------------------------------------------------------
    def connect(self) -> WaylandIdleSource:
        conn = _Connection()
        self._conn = conn

        self._registry_id = conn.new_id()
        conn.send(
            _message(_DISPLAY_ID, _WL_DISPLAY_GET_REGISTRY, struct.pack("=I", self._registry_id))
        )
        self._roundtrip()  # collect advertised globals

        seat = self._globals.get(_SEAT_INTERFACE)
        notifier = self._globals.get(_NOTIFIER_INTERFACE)
        if seat is None:
            raise RuntimeError("compositor does not advertise wl_seat")
        if notifier is None:
            raise RuntimeError(
                "compositor does not advertise ext_idle_notifier_v1 -- "
                "idle detection is unavailable on this session"
            )

        self._seat_id = self._bind(_SEAT_INTERFACE, seat)
        self._notifier_id = self._bind(_NOTIFIER_INTERFACE, notifier)

        self._notification_id = conn.new_id()
        body = struct.pack("=III", self._notification_id, self._resolution_ms, self._seat_id)
        conn.send(_message(self._notifier_id, _NOTIFIER_GET_IDLE_NOTIFICATION, body))
        self._roundtrip()  # flush and surface any protocol error
        return self

    def _bind(self, interface: str, glob: tuple[int, int]) -> int:
        assert self._conn is not None and self._registry_id is not None
        name, version = glob
        new_id = self._conn.new_id()
        body = (
            struct.pack("=I", name)
            + _encode_string(interface)
            + struct.pack("=II", version, new_id)
        )
        self._conn.send(_message(self._registry_id, _WL_REGISTRY_BIND, body))
        return new_id

    def _roundtrip(self) -> None:
        """Send wl_display.sync and process events until its callback.done arrives."""
        assert self._conn is not None
        callback_id = self._conn.new_id()
        self._conn.send(_message(_DISPLAY_ID, _WL_DISPLAY_SYNC, struct.pack("=I", callback_id)))
        while True:
            for object_id, opcode, body in self._conn.messages(block=True):
                self._handle(object_id, opcode, body)
                if object_id == callback_id and opcode == _WL_CALLBACK_DONE:
                    if self._error is not None:
                        raise self._error
                    return
            if self._error is not None:
                raise self._error

    def dispatch(self, *, block: bool = False) -> int:
        """Process pending events, invoking ``on_idled``/``on_resumed``. Returns count."""
        if self._conn is None:
            raise RuntimeError("WaylandIdleSource is not connected")
        handled = 0
        for object_id, opcode, body in self._conn.messages(block=block):
            self._handle(object_id, opcode, body)
            handled += 1
        if self._error is not None:
            raise self._error
        return handled

    def fileno(self) -> int:
        if self._conn is None:
            raise RuntimeError("WaylandIdleSource is not connected")
        return self._conn.fileno()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> WaylandIdleSource:
        return self.connect()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- event handling ------------------------------------------------------
    def _handle(self, object_id: int, opcode: int, body: bytes) -> None:
        if object_id == _DISPLAY_ID and opcode == _WL_DISPLAY_ERROR:
            self._error = self._parse_error(body)
            return
        if object_id == _DISPLAY_ID and opcode == _WL_DISPLAY_DELETE_ID:
            return
        if object_id == self._registry_id and opcode == _WL_REGISTRY_GLOBAL:
            name, interface, version = self._parse_global(body)
            self._globals[interface] = (name, version)
            return
        if object_id == self._notification_id:
            if opcode == _NOTIFICATION_IDLED and self.on_idled is not None:
                self.on_idled()
            elif opcode == _NOTIFICATION_RESUMED and self.on_resumed is not None:
                self.on_resumed()
            return
        # Everything else (wl_seat capabilities/name, callback.done, global_remove)
        # is framed by its header size and safely ignored.

    @staticmethod
    def _parse_global(body: bytes) -> tuple[int, str, int]:
        name = struct.unpack_from("=I", body, 0)[0]
        str_len = struct.unpack_from("=I", body, 4)[0]
        interface = body[8 : 8 + str_len - 1].decode("utf-8")  # drop trailing NUL
        version = struct.unpack_from("=I", body, 8 + _pad4(str_len))[0]
        return name, interface, version

    @staticmethod
    def _parse_error(body: bytes) -> WaylandProtocolError:
        object_id, code = struct.unpack_from("=II", body, 0)
        str_len = struct.unpack_from("=I", body, 8)[0]
        message = body[12 : 12 + str_len - 1].decode("utf-8", "replace")
        return WaylandProtocolError(object_id, code, message)
