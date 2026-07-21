"""Thin read-back HTTP server -- stdlib only, ``127.0.0.1`` local surface (Phase 5).

A ``ThreadingHTTPServer`` (thread per request) fronts the pure query layer. Each request
opens its **own** read-only :class:`~timekeeper.storage.reader.SpanReader`, so concurrent
reads never block or corrupt the collector's single writer and threads share no connection.
All computation lives in :mod:`timekeeper.api.queries`; this module only routes, reads, and
serialises JSON. No third-party dependency -- consistent with the project's stdlib-first
pattern (build-plan decision, Step 5.1).

Routes (shaped to ``docs/design-system.md``):

- ``GET /api/current``                       -> current session (from the store's open row)
- ``GET /api/summary?range=today|week|month`` -> active total + per-app totals/share
- ``GET /api/timeline?range=…``               -> active spans clamped to the window
- ``GET /api/health``                         -> liveness + whether the store exists
"""

from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from timekeeper.api import queries
from timekeeper.storage.reader import SpanReader
from timekeeper.web import STATIC_DIR

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765

# Extensions we are willing to serve, and their content types. Anything else 404s.
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".map": "application/json",
}


@dataclasses.dataclass
class _Config:
    store_path: str
    now: Callable[[], float] = time.time
    static_dir: Path = STATIC_DIR


class ReadBackServer(ThreadingHTTPServer):
    """A threaded HTTP server carrying the store path + clock for its handlers."""

    daemon_threads = True  # requests don't outlive the process
    allow_reuse_address = True

    def __init__(self, config: _Config, host: str, port: int) -> None:
        self.config = config
        super().__init__((host, port), _Handler)


class _Handler(BaseHTTPRequestHandler):
    server_version = "TimeKeeperReadBack/1.0"

    @property
    def _config(self) -> _Config:
        return self.server.config  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)
        try:
            if route == "/api/current":
                self._json(self._current())
            elif route == "/api/summary":
                self._json(self._summary(self._range(params)))
            elif route == "/api/timeline":
                self._json(self._timeline(self._range(params)))
            elif route == "/api/health":
                self._json(self._health())
            elif parsed.path.startswith("/api/"):
                self._error(HTTPStatus.NOT_FOUND, f"no such route: {route}")
            else:
                self._static(parsed.path)  # the live view (Phase 6)
        except _BadRequest as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # keep a single bad request from taking the server down
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, repr(exc))

    # -- route handlers (each opens its own read-only reader) -----------------

    def _current(self) -> dict:
        now = self._config.now()
        with SpanReader(self._config.store_path) as reader:
            state = queries.current_state(reader.open_span(), reader.latest_end(), now)
        return dataclasses.asdict(state)

    def _summary(self, range_name: str) -> dict:
        now = self._config.now()
        window = queries.range_window(now, range_name)
        with SpanReader(self._config.store_path) as reader:
            spans = reader.spans_overlapping(window.start, window.end)
        apps = queries.per_app_totals(spans, window)
        return {
            "range": range_name,
            "window": dataclasses.asdict(window),
            "active_seconds": queries.active_seconds(spans, window),
            "apps": [dataclasses.asdict(a) for a in apps],
        }

    def _timeline(self, range_name: str) -> dict:
        now = self._config.now()
        window = queries.range_window(now, range_name)
        with SpanReader(self._config.store_path) as reader:
            spans = reader.spans_overlapping(window.start, window.end)
        return {
            "range": range_name,
            "window": dataclasses.asdict(window),
            "spans": [
                {**dataclasses.asdict(s), "seconds": s.seconds}
                for s in queries.timeline(spans, window)
            ],
        }

    def _health(self) -> dict:
        path = self._config.store_path
        return {"ok": True, "store": path, "exists": Path(path).exists()}

    def _static(self, url_path: str) -> None:
        """Serve a file from the static dir; ``/`` -> index.html. Traversal-safe."""
        root = self._config.static_dir.resolve()
        rel = url_path.lstrip("/") or "index.html"
        target = (root / rel).resolve()
        # Reject anything that escapes the static root (path traversal).
        if root != target and root not in target.parents:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        content_type = _CONTENT_TYPES.get(target.suffix.lower())
        if content_type is None or not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- helpers --------------------------------------------------------------

    def _range(self, params: dict[str, list[str]]) -> str:
        value = params.get("range", ["today"])[0]
        if value not in queries.RANGES:
            raise _BadRequest(f"range must be one of {queries.RANGES}, got {value!r}")
        return value

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)

    def log_message(self, *args: object) -> None:  # silence stderr access logging
        pass


class _BadRequest(Exception):
    """A client error (400)."""


def serve(
    store_path: str,
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    now: Callable[[], float] = time.time,
) -> ReadBackServer:
    """Build (but do not start) a read-back server for ``store_path``."""
    return ReadBackServer(_Config(store_path=store_path, now=now), host, port)
