"""Step 5.1 (headless) -- the HTTP surface reconciles with the raw store, under load.

No Wayland: a temp SQLite store is driven with fake timestamps (exactly as the collector
would), the stdlib server is started on an ephemeral port, and its JSON is checked against
what the pure query layer computes from the same rows. The concurrency case runs a live
writer while readers hammer an endpoint, asserting no errors and no garbled rows -- the
reader/writer isolation the build plan requires.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from timekeeper.api import queries
from timekeeper.api.server import serve
from timekeeper.storage.reader import SpanReader
from timekeeper.storage.store import Store

MAX_GAP = 5.0


@contextmanager
def running_server(store_path: str, now: float) -> Iterator[str]:
    server = serve(str(store_path), host="127.0.0.1", port=0, now=lambda: now)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get_json(base: str, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(base + path)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a JSON body
        return exc.code, json.loads(exc.read())


def seed_today(store_path: str, now: float) -> None:
    """Dense 1s heartbeats (as the collector emits) ending 'now', inside today's window.

    Firefox for the first third, then code -- so the store holds two real spans plus a
    still-open code session ending exactly at ``now``.
    """
    window = queries.range_window(now, "today")
    duration = min(60.0, now - window.start - 1)  # stay strictly inside today
    base = now - duration
    switch = base + duration / 3
    with Store(store_path) as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        t = base
        while t < now:
            tl.active(t, "firefox" if t < switch else "code")
            t += 1.0
        tl.active(now, "code")  # final heartbeat at `now`, leaves the code span open


def test_summary_reconciles_with_the_raw_store(tmp_path) -> None:
    db = tmp_path / "tk.db"
    now = 1_800_000_000.0
    seed_today(str(db), now)
    with running_server(db, now) as base:
        status, body = get_json(base, "/api/summary?range=today")
    assert status == 200

    # Independently compute the expected numbers from the raw store, same window.
    window = queries.range_window(now, "today")
    with SpanReader(str(db)) as reader:
        spans = reader.spans_overlapping(window.start, window.end)
    assert body["active_seconds"] == pytest.approx(queries.active_seconds(spans, window))
    expected = queries.per_app_totals(spans, window)
    assert [a["app_class"] for a in body["apps"]] == [t.app_class for t in expected]
    assert body["apps"][0]["seconds"] == pytest.approx(expected[0].seconds)
    assert sum(a["share"] for a in body["apps"]) == pytest.approx(1.0)


def test_timeline_reconciles_and_is_sorted(tmp_path) -> None:
    db = tmp_path / "tk.db"
    now = 1_800_000_000.0
    seed_today(str(db), now)
    with running_server(db, now) as base:
        status, body = get_json(base, "/api/timeline?range=today")
    assert status == 200
    starts = [s["start"] for s in body["spans"]]
    assert starts == sorted(starts)
    assert all(s["seconds"] >= 0 for s in body["spans"])
    # Every timeline span carries an app class field (idle is never present).
    assert all("app_class" in s for s in body["spans"])


def test_current_reports_the_open_session(tmp_path) -> None:
    db = tmp_path / "tk.db"
    now = 1_800_000_000.0
    seed_today(str(db), now)  # leaves an open span ending at `now`
    with running_server(db, now) as base:
        status, body = get_json(base, "/api/current")
    assert status == 200
    assert body["active"] is True
    assert body["app_class"] == "code"
    assert body["session_seconds"] > 0
    assert body["as_of"] == pytest.approx(now)


def test_current_on_missing_store_is_idle_not_an_error(tmp_path) -> None:
    db = tmp_path / "does-not-exist.db"
    with running_server(db, 1_800_000_000.0) as base:
        status, body = get_json(base, "/api/current")
        hstatus, health = get_json(base, "/api/health")
    assert status == 200
    assert body["active"] is False
    assert hstatus == 200 and health["exists"] is False


def test_unknown_route_404_and_bad_range_400(tmp_path) -> None:
    db = tmp_path / "tk.db"
    seed_today(str(db), 1_800_000_000.0)
    with running_server(db, 1_800_000_000.0) as base:
        s404, _ = get_json(base, "/api/nope")
        s400, body = get_json(base, "/api/summary?range=decade")
    assert s404 == 404
    assert s400 == 400
    assert "range" in body["error"]


def get_raw(base: str, path: str) -> tuple[int, bytes, str]:
    req = urllib.request.Request(base + path)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")


def test_serves_the_live_view_at_root(tmp_path) -> None:
    # Phase 6: the API also serves the dashboard. "/" -> index.html, assets by path.
    with running_server(tmp_path / "tk.db", 1_800_000_000.0) as base:
        s_root, body, ctype = get_raw(base, "/")
        s_js, js_body, js_ctype = get_raw(base, "/app.js")
        s_ech, ech_body, _ = get_raw(base, "/vendor/echarts.min.js")
    assert s_root == 200 and b"actld" in body and "text/html" in ctype
    assert s_js == 200 and "javascript" in js_ctype
    assert s_ech == 200 and len(ech_body) > 100_000  # the vendored library is present


def test_static_missing_file_404_and_api_still_json(tmp_path) -> None:
    with running_server(tmp_path / "tk.db", 1_800_000_000.0) as base:
        s_missing, _, _ = get_raw(base, "/nope.js")
        s_api, _ = get_json(base, "/api/health")
    assert s_missing == 404
    assert s_api == 200  # /api/* routing is unaffected by the static handler


def test_static_path_traversal_is_blocked(tmp_path) -> None:
    with running_server(tmp_path / "tk.db", 1_800_000_000.0) as base:
        # Escaping the static root must 404, never leak a file.
        status, body, _ = get_raw(base, "/../../server.py")
    assert status == 404
    assert b"BaseHTTPRequestHandler" not in body


def test_concurrent_reads_while_writing_stay_clean(tmp_path) -> None:
    # A live writer plus a swarm of readers: WAL + read-only connections must yield no
    # errors and no garbled rows (every response parses and its shares stay well-formed).
    db = tmp_path / "tk.db"
    now = 1_800_000_000.0
    seed_today(str(db), now)  # ensure the DB + WAL exist before readers start

    stop = threading.Event()
    errors: list[str] = []

    def writer() -> None:
        try:
            with Store(str(db)) as store:
                tl = store.bind(max_gap_seconds=MAX_GAP)
                t = now
                apps = ["code", "firefox", "konsole"]
                i = 0
                while not stop.is_set() and i < 400:
                    t += 1.0
                    tl.active(t, apps[i % len(apps)])
                    i += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"writer: {exc!r}")

    def reader(base: str) -> None:
        try:
            for _ in range(40):
                status, body = get_json(base, "/api/summary?range=today")
                assert status == 200
                assert body["active_seconds"] >= 0
                for a in body["apps"]:
                    assert 0.0 <= a["share"] <= 1.0
                    assert a["sessions"] >= 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"reader: {exc!r}")

    with running_server(db, now) as base:
        w = threading.Thread(target=writer, daemon=True)
        w.start()
        readers = [threading.Thread(target=reader, args=(base,), daemon=True) for _ in range(6)]
        for r in readers:
            r.start()
        for r in readers:
            r.join(timeout=30)
        stop.set()
        w.join(timeout=30)

    assert errors == []
