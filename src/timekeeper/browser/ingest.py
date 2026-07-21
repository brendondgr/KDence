"""Loopback tab-ingest -- the I/O side of the browser seam (no time logic).

A deliberately tiny HTTP listener the collector runs, bound to a **loopback address only**.
The WebExtension POSTs the active tab's raw ``hostname`` + ``scheme`` to ``/tab``; this
normalises it through the pure :func:`~timekeeper.browser.site.normalize_site` policy and
hands the result to the :class:`~timekeeper.browser.tracker.BrowserTabTracker` the collector
polls each interval. All the *decisions* live in those pure modules; this file only moves
bytes.

Privacy invariants enforced here:

- **Loopback only.** The constructor refuses any bind address that is not loopback, so the
  endpoint can never be exposed off-machine.
- **Hostname only.** The contract accepts a hostname and scheme; paths/queries never appear
  in it and are never stored. What the extension sends is all this endpoint can know.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from timekeeper.browser.site import normalize_site
from timekeeper.browser.tracker import BrowserTabTracker

DEFAULT_INGEST_PORT = 8766
# The POST body is a hostname + a couple of short tokens; anything larger is not our contract.
_MAX_BODY_BYTES = 8192


def _is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


class _Handler(BaseHTTPRequestHandler):
    # Quieten the default stderr access log; the collector owns the console line.
    def log_message(self, *_args: object) -> None:  # noqa: D102
        return

    def _send(self, status: int, body: bytes = b"") -> None:
        self.send_response(status)
        # Loopback-only dev endpoint: allow the extension's origin without credentials.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if body:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802  (CORS preflight)
        self._send(204)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, b'{"ok":true}')
        else:
            self._send(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/tab":
            self._send(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400)
            return
        if length <= 0 or length > _MAX_BODY_BYTES:
            self._send(400)
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            self._send(400)
            return
        if not isinstance(payload, dict):
            self._send(400)
            return
        self.server.record(payload)
        self._send(204)


class TabIngestServer:
    """A loopback HTTP endpoint feeding a :class:`BrowserTabTracker`.

    Args:
        tracker: the tab tracker to report into.
        host: bind address; must be loopback (raises otherwise).
        port: TCP port (``0`` picks a free one -- handy for tests).
        clock: wall-clock source, injected for deterministic tests.
    """

    def __init__(
        self,
        tracker: BrowserTabTracker,
        host: str = "127.0.0.1",
        port: int = DEFAULT_INGEST_PORT,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not _is_loopback(host):
            raise ValueError(f"ingest must bind a loopback address, got {host!r}")
        self._tracker = tracker
        self._clock = clock
        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.record = self.record  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The actually-bound port (meaningful when constructed with ``port=0``)."""
        return self._httpd.server_address[1]

    def record(self, payload: dict) -> str | None:
        """Normalise one tab report and push it into the tracker; returns the stored site.

        The pure seam: usable directly in tests without going through HTTP. Missing/blank
        fields degrade gracefully -- an unknown engine or empty host simply records nothing
        useful rather than raising.
        """
        browser = str(payload.get("browser", ""))
        hostname = str(payload.get("hostname", ""))
        scheme = payload.get("scheme")
        site = normalize_site(hostname, scheme if scheme is None else str(scheme))
        self._tracker.report(browser, site, self._clock())
        return site

    def start(self) -> None:
        """Serve on a background daemon thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="tk-tab-ingest", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and release the socket."""
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def __enter__(self) -> TabIngestServer:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()
