"""Step 4.3 (synthetic) -- the SQLite store persists the model faithfully, and the crash
rule invents no hours.

Headless: the store is driven with fake timestamps through a bound Timeline, exactly as the
collector would drive it live, then queried directly. No Wayland needed. The live "run it a
few minutes and eyeball the dump" check is handed off in the Phase 4 plan.
"""

from __future__ import annotations

import sqlite3

from kdence.storage.store import Store

MAX_GAP = 5.0


def test_active_then_idle_persists_one_closed_span(tmp_path) -> None:
    db = tmp_path / "kdence.db"
    with Store(db) as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, "code")
        tl.active(2.0, "code")
        tl.idle(4.0)  # back-dated last-input instant
        rows = store.read_spans()
    assert len(rows) == 1
    (row,) = rows
    assert row.app_class == "code"
    assert row.start_at == 0.0
    assert row.end_at == 4.0
    assert row.open is False
    assert row.duration == 4.0


def test_app_switch_writes_contiguous_rows(tmp_path) -> None:
    with Store(tmp_path / "kdence.db") as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, "firefox")
        tl.active(3.0, "code")
        tl.active(7.0, "konsole")
        tl.stop(10.0)
        rows = store.read_spans()
        assert [r.app_class for r in rows] == ["firefox", "code", "konsole"]
        assert [r.duration for r in rows] == [3.0, 4.0, 3.0]
        assert all(r.open is False for r in rows)
        assert store.total_active_seconds() == 10.0


def test_at_most_one_open_row_at_a_time(tmp_path) -> None:
    db = tmp_path / "kdence.db"
    with Store(db) as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, "code")  # opens
        tl.active(2.0, "code")  # extends -- still one open row
        open_rows = [r for r in store.read_spans() if r.open]
        assert len(open_rows) == 1
        assert open_rows[0].end_at == 2.0  # end bumped to the latest heartbeat


def test_crash_recovery_closes_the_open_span_at_its_last_heartbeat(tmp_path) -> None:
    # Simulate a crash: write an open span, then abandon the connection WITHOUT a clean
    # close (no idle/stop). A brand-new Store over the same file must finalize that span at
    # its stored end_at -- NOT extend it to "now". That is the no-invented-hours rule.
    db = tmp_path / "kdence.db"
    store = Store(db)
    tl = store.bind(max_gap_seconds=MAX_GAP)
    tl.active(100.0, "code")
    tl.active(105.0, "code")  # last heartbeat at 105; span left open
    open_rows = [r for r in store.read_spans() if r.open]
    assert len(open_rows) == 1 and open_rows[0].end_at == 105.0
    store.close()  # connection closed, but the span was never cleanly finalized

    # Restart -- e.g. after a reboot, hours later.
    with Store(db) as restarted:
        rows = restarted.read_spans()
    assert len(rows) == 1
    (row,) = rows
    assert row.open is False  # recovered
    assert row.end_at == 105.0  # closed at the last heartbeat, no phantom time
    assert row.duration == 5.0


def test_recover_open_spans_reports_count(tmp_path) -> None:
    db = tmp_path / "kdence.db"
    store = Store(db)
    tl = store.bind(max_gap_seconds=MAX_GAP)
    tl.active(0.0, "code")
    store.close()
    with Store(db) as restarted:
        # __init__ already recovered it, so a second explicit call finds nothing.
        assert restarted.recover_open_spans() == 0
        assert all(r.open is False for r in restarted.read_spans())


def test_wal_mode_is_enabled_on_a_file_db(tmp_path) -> None:
    db = tmp_path / "kdence.db"
    with Store(db):
        pass
    con = sqlite3.connect(db)
    mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    con.close()
    assert mode.lower() == "wal"  # reader/writer isolation for Phase 5


def test_desktop_span_stores_null_app_class(tmp_path) -> None:
    with Store(tmp_path / "kdence.db") as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, None)  # bare desktop: active but appless
        tl.stop(2.0)
        rows = store.read_spans()
    assert rows[0].app_class is None
    assert rows[0].duration == 2.0


def test_detail_round_trips_through_the_store(tmp_path) -> None:
    with Store(tmp_path / "kdence.db") as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, "librewolf", None, "youtube.com", "site")
        tl.active(2.0, "librewolf", None, "github.com", "site")  # detail switch -> 2 spans
        tl.stop(4.0)
        rows = store.read_spans()
    assert [r.detail for r in rows] == ["youtube.com", "github.com"]
    assert [r.detail_source for r in rows] == ["site", "site"]
    # A browser site surfaces through the generic effective_site accessor too.
    assert [r.effective_site for r in rows] == ["youtube.com", "github.com"]
    assert [r.app_class for r in rows] == ["librewolf", "librewolf"]


def test_caption_detail_is_not_a_site(tmp_path) -> None:
    # A caption/mpris detail rides the same column but must not read back as a browser site.
    with Store(tmp_path / "kdence.db") as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, "org.kde.kate", None, "notes.md", "caption")
        tl.stop(2.0)
        (row,) = store.read_spans()
    assert row.detail == "notes.md"
    assert row.effective_source == "caption"
    assert row.effective_site is None  # caption is not a site -> no site drill-down


def test_non_detail_span_is_null(tmp_path) -> None:
    with Store(tmp_path / "kdence.db") as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, "code")
        tl.stop(2.0)
        (row,) = store.read_spans()
    assert row.detail is None and row.effective_detail is None and row.effective_site is None


def test_migration_adds_detail_columns_and_coalesces_a_legacy_site(tmp_path) -> None:
    # Hand-build a store from the browser-era schema: it had `site` but no detail columns.
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE spans (id INTEGER PRIMARY KEY, app_class TEXT, title TEXT, site TEXT, "
        "start_at REAL NOT NULL, end_at REAL NOT NULL, open INTEGER NOT NULL DEFAULT 0);"
    )
    conn.executemany(
        "INSERT INTO spans (app_class, title, site, start_at, end_at, open) VALUES (?, ?, ?, ?, ?, 0)",
        [("code", None, None, 0.0, 5.0), ("librewolf", None, "github.com", 5.0, 9.0)],
    )
    conn.commit()
    conn.close()

    # Opening it migrates the detail columns in place; history survives and a legacy `site`
    # value coalesces into the generic detail with source "site".
    with Store(db) as store:
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(spans)")}
        assert {"site", "detail", "detail_source"} <= cols
        rows = store.read_spans()
    assert len(rows) == 2
    assert rows[0].app_class == "code" and rows[0].effective_detail is None
    # Legacy browser row: detail column is NULL but the host coalesces through effective_*.
    assert rows[1].detail is None and rows[1].site == "github.com"
    assert rows[1].effective_detail == "github.com" and rows[1].effective_source == "site"
    assert rows[1].effective_site == "github.com"
