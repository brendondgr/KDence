"""Thin read-back HTTP server -- stdlib only, ``127.0.0.1`` local surface (Phase 5).

A ``ThreadingHTTPServer`` (thread per request) fronts the pure query layer. Each request
opens its **own** read-only :class:`~kdence.storage.reader.SpanReader`, so concurrent
reads never block or corrupt the collector's single writer and threads share no connection.
All computation lives in :mod:`kdence.api.queries`; this module only routes, reads, and
serialises JSON. No third-party dependency -- consistent with the project's stdlib-first
pattern (build-plan decision, Step 5.1).

Routes (shaped to ``docs/design-system.md``):

- ``GET /api/current``                        -> current session (from the store's open row)
- ``GET /api/summary?range=…[&date=|start=&end=]`` -> active total + per-app totals/share
- ``GET /api/timeline?range=…``               -> active spans clamped to the window
- ``GET /api/extent``                         -> earliest/latest span + days tracked (Phase 9)
- ``GET /api/buckets?…&granularity=…``        -> bounded per-bucket series for long ranges (Phase 9)
- ``GET /api/health``                         -> liveness + whether the store exists

Window selection (Phase 9): ``range`` is one of ``today|day|week|month|year`` (period), with an
optional ``date=YYYY-MM-DD`` anchor selecting *which* period; or ``start=&end=`` (dates or
timestamps) for a custom window. No params -> today, live.
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

from kdence import grouping
from kdence.api import queries
from kdence.detail import config as detail_config
from kdence.storage.paths import default_categories_path, default_detail_path
from kdence.storage.reader import SpanReader
from kdence.web import STATIC_DIR

# The write endpoint accepts a small JSON config; anything larger is not our contract.
_MAX_CONFIG_BYTES = 64 * 1024

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 5785

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
    categories_path: str | None = None  # None -> the durable XDG default, resolved lazily
    detail_path: str | None = None  # detail-provider toggle file; None -> XDG default, lazy


class ReadBackServer(ThreadingHTTPServer):
    """A threaded HTTP server carrying the store path + clock for its handlers."""

    daemon_threads = True  # requests don't outlive the process
    allow_reuse_address = True

    def __init__(self, config: _Config, host: str, port: int) -> None:
        self.config = config
        super().__init__((host, port), _Handler)


class _Handler(BaseHTTPRequestHandler):
    server_version = "KDenceReadBack/1.0"

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
                self._json(self._summary(params))
            elif route == "/api/timeline":
                self._json(self._timeline(params))
            elif route == "/api/extent":
                self._json(self._extent())
            elif route == "/api/buckets":
                self._json(self._buckets(params))
            elif route == "/api/categories":
                self._json(self._categories())
            elif route == "/api/detail":
                self._json(self._detail())
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

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        route = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if route == "/api/categories":
                self._json(self._save_categories())
            elif route == "/api/detail":
                self._json(self._save_detail())
            else:
                self._error(HTTPStatus.NOT_FOUND, f"no such route: {route}")
        except _BadRequest as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # never let one bad write take the server down
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, repr(exc))

    # -- route handlers (each opens its own read-only reader) -----------------

    def _current(self) -> dict:
        now = self._config.now()
        with SpanReader(self._config.store_path) as reader:
            state = queries.current_state(reader.open_span(), reader.latest_end(), now)
        return dataclasses.asdict(state)

    def _summary(self, params: dict[str, list[str]]) -> dict:
        window, name = self._resolve(params)
        with SpanReader(self._config.store_path) as reader:
            spans = reader.spans_overlapping(window.start, window.end)
        apps = queries.per_app_totals(spans, window)
        site_map = queries.per_app_site_totals(spans, window)
        # Values the user hid from the drill-down are folded away here (still on disk, just not shown).
        hidden = (detail_config.load(self._detail_path()) or detail_config.DetailConfig()).hidden
        detail_map = queries.per_app_detail_totals(spans, window, hidden)
        apps_json = []
        for a in apps:
            entry = dataclasses.asdict(a)
            # Generic in-app detail (site/document/track) -> the table drill-down for any app.
            details = detail_map.get(a.app_class)
            if details is not None:
                entry["details"] = [dataclasses.asdict(d) for d in details]
            # Browser hosts only -> the site-category editor (hosts are the assignable subset).
            sites = site_map.get(a.app_class)
            if sites is not None:
                # The charts read `apps` and ignore this per-app breakdown.
                entry["sites"] = [dataclasses.asdict(s) for s in sites]
            apps_json.append(entry)
        # Roll the same per-app totals up by category (the group-basis view). The site
        # breakdown lets a browser's time split across categories by site.
        groups = queries.group_totals(
            apps, grouping.load(self._categories_path()), site_totals=site_map
        )
        return {
            "range": name,
            "window": dataclasses.asdict(window),
            "active_seconds": queries.active_seconds(spans, window),
            "apps": apps_json,
            "groups": [dataclasses.asdict(g) for g in groups],
        }

    def _timeline(self, params: dict[str, list[str]]) -> dict:
        window, name = self._resolve(params)
        with SpanReader(self._config.store_path) as reader:
            spans = reader.spans_overlapping(window.start, window.end)
        return {
            "range": name,
            "window": dataclasses.asdict(window),
            "spans": [
                {**dataclasses.asdict(s), "seconds": s.seconds}
                for s in queries.timeline(spans, window)
            ],
        }

    def _extent(self) -> dict:
        with SpanReader(self._config.store_path) as reader:
            ext = reader.extent()
        if ext is None:
            return {"earliest": None, "latest": None, "days": 0.0, "spans": 0}
        earliest, latest, count = ext
        return {
            "earliest": earliest,
            "latest": latest,
            "days": (latest - earliest) / 86400.0,
            "spans": count,
        }

    def _buckets(self, params: dict[str, list[str]]) -> dict:
        window, name = self._resolve(params)
        granularity = self._param(params, "granularity") or queries.auto_granularity(window)
        if granularity not in queries.GRANULARITIES:
            raise _BadRequest(
                f"granularity must be one of {queries.GRANULARITIES}, got {granularity!r}"
            )
        with SpanReader(self._config.store_path) as reader:
            spans = reader.spans_overlapping(window.start, window.end)
        buckets = queries.bucket_series(spans, window, granularity)
        return {
            "range": name,
            "granularity": granularity,
            "window": dataclasses.asdict(window),
            "buckets": [
                {
                    "start": b.start,
                    "end": b.end,
                    "active_seconds": b.active_seconds,
                    # app_class kept in a list (may be null) rather than as an object key.
                    "apps": [{"app_class": app, "seconds": secs} for app, secs in b.apps.items()],
                }
                for b in buckets
            ],
        }

    def _categories_path(self) -> str:
        """The category-config file: the configured override, else the durable XDG default."""
        configured = self._config.categories_path
        return configured if configured is not None else str(default_categories_path())

    def _categories_payload(self, config: grouping.CategoryConfig) -> dict:
        return {
            "palette": list(grouping.PALETTE),
            "uncategorized_id": grouping.UNCATEGORIZED,
            "categories": [dataclasses.asdict(c) for c in config.categories],
            "assignments": dict(config.assignments),
            "site_assignments": dict(config.site_assignments),
            # The server-owned seed maps, so the view's "Auto-categorize" uses the same source.
            "defaults": dict(grouping.DEFAULT_ASSIGNMENTS),
            "site_defaults": dict(grouping.DEFAULT_SITE_ASSIGNMENTS),
        }

    def _categories(self) -> dict:
        """GET: the current category config (or the opinionated defaults if none saved yet)."""
        return self._categories_payload(grouping.load(self._categories_path()))

    def _save_categories(self) -> dict:
        """POST: validate a category config and persist it atomically; echo the saved config.

        Writes **only** the config file -- never the span store, so the store's single-writer
        isolation is untouched. Strict validation (:func:`grouping.parse`) turns bad input into
        a 400 rather than a corrupt file.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise _BadRequest("invalid Content-Length") from exc
        if length <= 0 or length > _MAX_CONFIG_BYTES:
            raise _BadRequest("empty or oversized body")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise _BadRequest(f"invalid JSON: {exc}") from exc
        try:
            config = grouping.parse(payload)
        except ValueError as exc:
            raise _BadRequest(str(exc)) from exc
        grouping.save(self._categories_path(), config)
        return self._categories_payload(config)

    # -- in-app detail providers (the dashboard's live toggle) ----------------

    def _detail_path(self) -> str:
        """The detail-toggle file: the configured override, else the durable XDG default."""
        configured = self._config.detail_path
        return configured if configured is not None else str(default_detail_path())

    def _detail_payload(self, config: detail_config.DetailConfig) -> dict:
        return {
            "providers": sorted(config.providers),
            "denylist": sorted(config.denylist),
            "hidden": sorted(config.hidden),  # detail values ✕'d from the drill-down
            # The toggleable providers + their blurbs, server-owned so the UI has one source.
            "available": list(detail_config.PROVIDERS),
            "labels": dict(detail_config.PROVIDER_LABELS),
        }

    def _detail(self) -> dict:
        """GET: the current in-app detail toggle state (empty/OFF when nothing saved yet)."""
        config = detail_config.load(self._detail_path()) or detail_config.DetailConfig()
        return self._detail_payload(config)

    def _save_detail(self) -> dict:
        """POST: validate the detail-provider toggle and persist it atomically; echo it back.

        Writes **only** the ``detail.json`` config (never the span store). The collector re-reads
        it each interval and reconfigures its providers live, so the toggle takes effect without a
        restart. Strict validation turns an unknown provider into a 400 rather than a bad file.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise _BadRequest("invalid Content-Length") from exc
        if length <= 0 or length > _MAX_CONFIG_BYTES:
            raise _BadRequest("empty or oversized body")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise _BadRequest(f"invalid JSON: {exc}") from exc
        try:
            config = detail_config.parse(payload, strict=True)
        except ValueError as exc:
            raise _BadRequest(str(exc)) from exc
        detail_config.save(self._detail_path(), config)  # save() creates the parent dir
        return self._detail_payload(config)

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

    def _param(self, params: dict[str, list[str]], key: str) -> str | None:
        values = params.get(key)
        return values[0] if values else None

    def _instant(self, value: str) -> float:
        """A query value -> wall-clock timestamp: a float as-is, else a ``YYYY-MM-DD`` date."""
        try:
            return float(value)
        except ValueError:
            pass
        try:
            return queries.local_date_to_timestamp(value)
        except ValueError as exc:
            raise _BadRequest(str(exc)) from exc

    def _resolve(self, params: dict[str, list[str]]) -> tuple[queries.Window, str]:
        """Resolve request params to a ``(window, name)``. Back-compat: ``range=today`` alone
        still means today. ``start``/``end`` -> custom; ``date`` anchors a named period."""
        now = self._config.now()
        start_p = self._param(params, "start")
        end_p = self._param(params, "end")
        if start_p is not None or end_p is not None:
            if start_p is None or end_p is None:
                raise _BadRequest("a custom range needs both start and end")
            try:
                window = queries.custom_window(self._instant(start_p), self._instant(end_p))
            except ValueError as exc:
                raise _BadRequest(str(exc)) from exc
            return window, "custom"

        period = self._param(params, "range") or self._param(params, "period") or "today"
        if period not in queries.RANGES:
            raise _BadRequest(f"range must be one of {queries.RANGES}, got {period!r}")
        date_p = self._param(params, "date")
        anchor = self._instant(date_p) if date_p is not None else None
        return queries.range_window(now, period, anchor=anchor), period

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
    categories_path: str | None = None,
    detail_path: str | None = None,
) -> ReadBackServer:
    """Build (but do not start) a read-back server for ``store_path``.

    ``categories_path`` / ``detail_path`` override where the category config and the detail-provider
    toggle are read/written (both default to the durable XDG paths); tests point them at temp files.
    """
    return ReadBackServer(
        _Config(
            store_path=store_path,
            now=now,
            categories_path=categories_path,
            detail_path=detail_path,
        ),
        host,
        port,
    )
