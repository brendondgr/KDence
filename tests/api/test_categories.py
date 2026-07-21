"""Category API tests (headless): GET defaults, POST persist/validate, grouped summary.

A temp store is driven with fake timestamps (as the collector would), the stdlib server runs
on an ephemeral port with its category config pointed at a temp file, and the JSON is checked
against the pure query/grouping layers over the same rows.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from timekeeper.api.server import serve
from timekeeper.grouping.categories import UNCATEGORIZED
from timekeeper.storage.store import Store


@contextmanager
def running_server(store_path: str, categories_path: str, now: float) -> Iterator[str]:
    server = serve(
        str(store_path),
        host="127.0.0.1",
        port=0,
        now=lambda: now,
        categories_path=str(categories_path),
    )
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
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def post_json(base: str, path: str, body: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def seed(store_path: str, now: float) -> None:
    # Three spans ending at `now` (so they're within today in any local zone): code (work,
    # 1800s) then steam (games, 600s) then an unseeded browser (uncategorized, 300s). A wide
    # max_gap lets the transition heartbeats stitch instead of tripping the suspend rule.
    with Store(store_path) as store:
        tl = store.bind(max_gap_seconds=100_000.0)
        tl.active(now - 2700, "code")
        tl.active(now - 900, "steam")
        tl.active(now - 300, "librewolf")
        tl.stop(now)


def test_get_categories_returns_defaults_when_no_file(tmp_path) -> None:
    now = 1_760_000_000.0
    cats = tmp_path / "categories.json"
    with running_server(tmp_path / "tk.db", cats, now) as base:
        status, body = get_json(base, "/api/categories")
    assert status == 200
    assert len(body["palette"]) == 12
    assert body["uncategorized_id"] == UNCATEGORIZED
    ids = {c["id"] for c in body["categories"]}
    assert {"work", "games", "social", "entertainment", UNCATEGORIZED} <= ids
    assert body["assignments"]["code"] == "work"


def test_summary_groups_reconcile_with_apps(tmp_path) -> None:
    now = 1_760_000_000.0
    cats = tmp_path / "categories.json"
    store = tmp_path / "tk.db"
    seed(store, now)
    with running_server(store, cats, now) as base:
        status, body = get_json(base, "/api/summary?range=today")
    assert status == 200
    groups = {g["id"]: g for g in body["groups"]}
    # code -> work, steam -> games, librewolf -> uncategorized.
    assert round(groups["work"]["seconds"]) == 1800
    assert round(groups["games"]["seconds"]) == 600
    assert round(groups[UNCATEGORIZED]["seconds"]) == 300
    # Group seconds reconcile with the flat active total and with per-app totals.
    assert round(sum(g["seconds"] for g in body["groups"])) == round(body["active_seconds"])
    app_secs = {a["app_class"]: a["seconds"] for a in body["apps"]}
    assert round(groups["work"]["apps"][0]["seconds"]) == round(app_secs["code"])
    # Members carry their own (variant) colours.
    assert all("color" in m for g in body["groups"] for m in g["apps"])


def test_post_categories_persists_and_round_trips(tmp_path) -> None:
    now = 1_760_000_000.0
    cats = tmp_path / "categories.json"
    store = tmp_path / "tk.db"
    seed(store, now)
    new_config = {
        "categories": [
            {"id": "work", "name": "Work", "color": "#4c9aff"},
            {"id": "fun", "name": "Fun", "color": "#f0883e"},
        ],
        "assignments": {"steam": "fun", "code": "work"},
    }
    with running_server(store, cats, now) as base:
        status, saved = post_json(base, "/api/categories", json.dumps(new_config).encode())
        assert status == 200
        assert saved["assignments"]["steam"] == "fun"
        # Uncategorized was force-injected on save.
        assert UNCATEGORIZED in {c["id"] for c in saved["categories"]}
        # A fresh GET reflects the persisted file.
        _, got = get_json(base, "/api/categories")
        assert got["assignments"]["steam"] == "fun"
        # And the summary now rolls steam up under 'fun'.
        _, summary = get_json(base, "/api/summary?range=today")
        groups = {g["id"]: g for g in summary["groups"]}
        assert round(groups["fun"]["seconds"]) == 600
    assert cats.exists()  # persisted to disk


def test_post_bad_config_is_rejected_without_writing(tmp_path) -> None:
    now = 1_760_000_000.0
    cats = tmp_path / "categories.json"
    with running_server(tmp_path / "tk.db", cats, now) as base:
        status, body = post_json(base, "/api/categories", b'{"categories": []}')
        assert status == 400
        status2, _ = post_json(base, "/api/categories", b"not json")
        assert status2 == 400
    assert not cats.exists()  # nothing was written
