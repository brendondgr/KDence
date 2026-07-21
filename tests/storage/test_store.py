"""Step 4.3 (synthetic) -- the SQLite store persists the model faithfully, and the crash
rule invents no hours.

Headless: the store is driven with fake timestamps through a bound Timeline, exactly as the
collector would drive it live, then queried directly. No Wayland needed. The live "run it a
few minutes and eyeball the dump" check is handed off in the Phase 4 plan.
"""

from __future__ import annotations

import sqlite3

from timekeeper.storage.store import Store

MAX_GAP = 5.0


def test_active_then_idle_persists_one_closed_span(tmp_path) -> None:
    db = tmp_path / "tk.db"
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
    with Store(tmp_path / "tk.db") as store:
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
    db = tmp_path / "tk.db"
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
    db = tmp_path / "tk.db"
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
    db = tmp_path / "tk.db"
    store = Store(db)
    tl = store.bind(max_gap_seconds=MAX_GAP)
    tl.active(0.0, "code")
    store.close()
    with Store(db) as restarted:
        # __init__ already recovered it, so a second explicit call finds nothing.
        assert restarted.recover_open_spans() == 0
        assert all(r.open is False for r in restarted.read_spans())


def test_wal_mode_is_enabled_on_a_file_db(tmp_path) -> None:
    db = tmp_path / "tk.db"
    with Store(db):
        pass
    con = sqlite3.connect(db)
    mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    con.close()
    assert mode.lower() == "wal"  # reader/writer isolation for Phase 5


def test_desktop_span_stores_null_app_class(tmp_path) -> None:
    with Store(tmp_path / "tk.db") as store:
        tl = store.bind(max_gap_seconds=MAX_GAP)
        tl.active(0.0, None)  # bare desktop: active but appless
        tl.stop(2.0)
        rows = store.read_spans()
    assert rows[0].app_class is None
    assert rows[0].duration == 2.0
