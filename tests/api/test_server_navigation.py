"""Step 9.3 (headless) -- the date-aware HTTP surface over a multi-day store.

A temp store is seeded with spans on specific local dates (written directly, as the collector
would have over days), the stdlib server is started on an ephemeral port, and the new
endpoints are checked: ``/api/extent`` reports the navigable range, ``date``/``start``/``end``
select arbitrary historical windows, and ``/api/buckets`` reconciles with the raw store.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from kdence.api.server import serve
from kdence.storage.store import Store

# Local (naive) timestamps -- the server interprets date params in the machine's local zone,
# so seeding in the same local frame keeps the tests deterministic across machines.


def lts(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> float:
    return dt.datetime(y, mo, d, h, mi).timestamp()


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
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def seed_spans(store_path: str, rows: list[tuple[str, float, float]]) -> None:
    """Insert closed spans directly (Store creates the schema; then raw INSERTs for speed)."""
    with Store(store_path):
        pass
    conn = sqlite3.connect(store_path)
    conn.executemany(
        "INSERT INTO spans (app_class, title, start_at, end_at, open) VALUES (?, NULL, ?, ?, 0)",
        rows,
    )
    conn.commit()
    conn.close()


NOW = lts(2026, 7, 21, 15)  # "now" is far from the seeded March dates


def _march_store(tmp_path):
    db = tmp_path / "kdence.db"
    seed_spans(
        str(db),
        [
            ("code", lts(2026, 3, 9, 9), lts(2026, 3, 9, 10)),  # 1h on Mar 9
            ("firefox", lts(2026, 3, 9, 11), lts(2026, 3, 9, 11, 30)),  # 30m on Mar 9
            ("code", lts(2026, 3, 12, 14), lts(2026, 3, 12, 15)),  # 1h on Mar 12
        ],
    )
    return db


def test_extent_reports_the_navigable_range(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(base, "/api/extent")
    assert status == 200
    assert body["earliest"] == pytest.approx(lts(2026, 3, 9, 9))
    assert body["latest"] == pytest.approx(lts(2026, 3, 12, 15))
    assert body["spans"] == 3
    assert body["days"] == pytest.approx((lts(2026, 3, 12, 15) - lts(2026, 3, 9, 9)) / 86400.0)


def test_extent_on_empty_store_is_nulls(tmp_path) -> None:
    with running_server(tmp_path / "empty.db", NOW) as base:
        status, body = get_json(base, "/api/extent")
    assert status == 200
    assert body["earliest"] is None and body["latest"] is None and body["spans"] == 0


def test_summary_for_an_anchored_past_day(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(base, "/api/summary?range=day&date=2026-03-09")
    assert status == 200
    assert body["range"] == "day"
    assert body["active_seconds"] == pytest.approx(1.5 * 3600)  # 1h code + 30m firefox
    apps = {a["app_class"]: a["seconds"] for a in body["apps"]}
    assert apps["code"] == pytest.approx(3600)
    assert apps["firefox"] == pytest.approx(1800)


def test_summary_for_a_different_day_is_empty(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(base, "/api/summary?range=day&date=2026-03-10")
    assert status == 200
    assert body["active_seconds"] == pytest.approx(0.0)
    assert body["apps"] == []


def test_custom_range_spanning_both_active_days(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(base, "/api/summary?start=2026-03-09&end=2026-03-13")
    assert status == 200
    assert body["range"] == "custom"
    assert body["active_seconds"] == pytest.approx(2.5 * 3600)  # all three spans


def test_custom_range_needs_both_bounds(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(base, "/api/summary?start=2026-03-09")
    assert status == 400
    assert "start" in body["error"] and "end" in body["error"]


def test_buckets_reconcile_with_the_summary(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        _, summary = get_json(base, "/api/summary?range=day&date=2026-03-09")
        status, body = get_json(base, "/api/buckets?range=day&date=2026-03-09&granularity=hour")
    assert status == 200
    assert body["granularity"] == "hour"
    assert len(body["buckets"]) == 24
    total = sum(b["active_seconds"] for b in body["buckets"])
    assert total == pytest.approx(summary["active_seconds"])
    # Hour 09 holds the 1h code span.
    hour9 = body["buckets"][9]
    apps = {a["app_class"]: a["seconds"] for a in hour9["apps"]}
    assert apps["code"] == pytest.approx(3600)


def test_buckets_auto_granularity_for_a_month(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(base, "/api/buckets?range=month&date=2026-03-09")
    assert status == 200
    assert body["granularity"] == "day"  # a month -> daily buckets
    assert len(body["buckets"]) == 31


def test_bad_granularity_is_400(tmp_path) -> None:
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(
            base, "/api/buckets?range=day&date=2026-03-09&granularity=fortnight"
        )
    assert status == 400
    assert "granularity" in body["error"]


def test_legacy_range_today_still_works(tmp_path) -> None:
    # Back-compat: the Phase 5/6 view's plain ?range=today must be unaffected.
    db = _march_store(tmp_path)
    with running_server(db, NOW) as base:
        status, body = get_json(base, "/api/summary?range=today")
    assert status == 200
    assert body["range"] == "today"
