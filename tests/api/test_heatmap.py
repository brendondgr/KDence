"""The time-of-day heat map -- pure binning, window resolution, the daily cache, and the route.

Deterministic: timestamps are built in fixed zones and ``now`` is explicit. The binning cases
prove every clipped second lands in exactly one ``(local day, five-minute slot)`` and that
today is never binned; the cache cases prove a build happens once per local date and that a
corrupt cache file is rebuilt rather than trusted.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import urllib.request
from contextlib import contextmanager
from zoneinfo import ZoneInfo

import pytest

from kdence.api import heatmap
from kdence.api import heatmap_cache as hc
from kdence.api.server import serve
from kdence.storage.store import Store

UTC = dt.timezone.utc
D = dt.date


def ts(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0, tz=UTC) -> float:
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=tz).timestamp()


# -- binning ------------------------------------------------------------------


def test_an_interval_splits_across_five_minute_slots() -> None:
    # 10:03:00 -> 10:11:30 = 120 s in :00, 300 s in :05, 90 s in :10.
    out = heatmap.daily_slots([(ts(2026, 3, 2, 10, 3), ts(2026, 3, 2, 10, 11, 30))], 1e12, UTC)
    day = out[D(2026, 3, 2)]
    base = 10 * 12
    assert day[base : base + 3] == [120.0, 300.0, 90.0]
    assert sum(day) == pytest.approx(510.0)


def test_a_span_across_midnight_lands_on_both_days() -> None:
    out = heatmap.daily_slots([(ts(2026, 3, 2, 23, 58), ts(2026, 3, 3, 0, 4))], 1e12, UTC)
    assert out[D(2026, 3, 2)][287] == pytest.approx(120.0)
    assert out[D(2026, 3, 3)][0] == pytest.approx(240.0)


def test_nothing_at_or_after_the_cutoff_is_binned() -> None:
    until = ts(2026, 3, 3)  # "today's" midnight
    out = heatmap.daily_slots(
        [(ts(2026, 3, 2, 23, 55), ts(2026, 3, 3, 1)), (ts(2026, 3, 3, 9), ts(2026, 3, 3, 10))],
        until,
        UTC,
    )
    assert list(out) == [D(2026, 3, 2)]
    assert sum(out[D(2026, 3, 2)]) == pytest.approx(300.0)


def test_slots_follow_local_wall_clock_in_a_non_utc_zone() -> None:
    tz = ZoneInfo("America/New_York")
    out = heatmap.daily_slots(
        [(ts(2026, 7, 1, 9, 0, tz=tz), ts(2026, 7, 1, 9, 5, tz=tz))], 1e12, tz
    )
    assert out[D(2026, 7, 1)][9 * 12] == pytest.approx(300.0)


def test_totals_reconcile_with_the_intervals() -> None:
    intervals = [
        (ts(2026, 3, 1, 8, 1, 7), ts(2026, 3, 1, 9, 44, 2)),
        (ts(2026, 3, 1, 22, 30), ts(2026, 3, 2, 2, 17, 13)),
        (ts(2026, 3, 4, 12, 0, 1), ts(2026, 3, 4, 12, 0, 2)),
    ]
    out = heatmap.daily_slots(intervals, 1e12, UTC)
    assert sum(sum(v) for v in out.values()) == pytest.approx(sum(b - a for a, b in intervals))
    assert all(len(v) == heatmap.SLOTS_PER_DAY for v in out.values())


# -- windows + aggregation -------------------------------------------------------


def test_resolve_range_clamps_to_the_archive() -> None:
    earliest, through = D(2026, 3, 1), D(2026, 3, 20)
    assert heatmap.resolve_range("7", earliest, through) == (D(2026, 3, 14), through)
    assert heatmap.resolve_range("30", earliest, through) == (earliest, through)
    assert heatmap.resolve_range("all", earliest, through) == (earliest, through)
    assert heatmap.resolve_range("all", None, None) is None
    with pytest.raises(ValueError):
        heatmap.resolve_range("14", earliest, through)


def test_aggregate_sums_days_and_counts_calendar_days() -> None:
    a = [0.0] * heatmap.SLOTS_PER_DAY
    b = [0.0] * heatmap.SLOTS_PER_DAY
    a[100], b[100], b[5] = 60.0, 30.0, 300.0
    days = {D(2026, 3, 1): a, D(2026, 3, 3): b, D(2026, 3, 9): b}  # 3/9 is outside
    win = heatmap.aggregate(days, D(2026, 3, 1), D(2026, 3, 4))
    assert win.days == 4  # includes the two untracked days as zeros
    assert win.seconds[100] == pytest.approx(90.0)
    assert win.active_days[100] == 2
    assert win.seconds[5] == pytest.approx(300.0) and win.active_days[5] == 1

    empty = heatmap.aggregate(days, None, None)
    assert empty.days == 0 and sum(empty.seconds) == 0


# -- the daily cache --------------------------------------------------------------


def seed(db: str, intervals: list[tuple[float, float]]) -> None:
    """Dense 1 s heartbeats per interval, closed by a gap (as the collector would write)."""
    with Store(db) as store:
        tl = store.bind(max_gap_seconds=5.0)
        for start, end in intervals:
            t = start
            while t <= end:
                tl.active(t, "code")
                t += 1.0
            tl.idle(end)


class Clock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_cache_builds_once_per_day_and_persists(tmp_path, monkeypatch) -> None:
    db, cache_file = str(tmp_path / "k.db"), tmp_path / "cache" / "heatmap.json"
    seed(
        db,
        [(ts(2026, 3, 1, 10), ts(2026, 3, 1, 10, 10)), (ts(2026, 3, 2, 9), ts(2026, 3, 2, 9, 3))],
    )
    clock = Clock(ts(2026, 3, 2, 12))  # the 3/2 span is "today" -> excluded
    builds = []
    real_build = hc.build
    monkeypatch.setattr(hc, "build", lambda *a, **k: builds.append(1) or real_build(*a, **k))

    cache = hc.HeatmapCache(db, cache_file, now=clock, tz=UTC)
    snap, win = cache.window("all")
    assert snap.through == D(2026, 3, 1) and snap.earliest == D(2026, 3, 1)
    assert win.days == 1 and sum(win.seconds) == pytest.approx(600.0)
    cache.window("7")
    assert len(builds) == 1  # same date -> served from memory
    assert cache_file.exists()

    # A fresh process on the same date reuses the file instead of rebuilding.
    hc.HeatmapCache(db, cache_file, now=clock, tz=UTC).window("all")
    assert len(builds) == 1

    # The date rolls over -> exactly one rebuild, and yesterday is now included.
    clock.t = ts(2026, 3, 3, 0, 1)
    snap, win = cache.window("all")
    assert len(builds) == 2
    assert snap.through == D(2026, 3, 2) and win.days == 2
    assert sum(win.seconds) == pytest.approx(600.0 + 180.0)


def test_a_corrupt_cache_file_is_rebuilt(tmp_path) -> None:
    db, cache_file = str(tmp_path / "k.db"), tmp_path / "heatmap.json"
    seed(db, [(ts(2026, 3, 1, 10), ts(2026, 3, 1, 10, 5))])
    cache_file.write_text('{"version": 1, "days": {"2026-03-01": [1, 2]}}')
    cache = hc.HeatmapCache(db, cache_file, now=Clock(ts(2026, 3, 5)), tz=UTC)
    _, win = cache.window("all")
    assert sum(win.seconds) == pytest.approx(300.0)
    assert json.loads(cache_file.read_text())["built_for"] == "2026-03-05"


def test_an_empty_store_has_no_completed_days(tmp_path) -> None:
    cache = hc.HeatmapCache(str(tmp_path / "missing.db"), tmp_path / "h.json", now=Clock(1e9))
    snap, win = cache.window("all")
    assert snap.earliest is None and snap.through is None and win.days == 0


def test_snapshot_round_trips_through_json() -> None:
    slots = [0.0] * heatmap.SLOTS_PER_DAY
    slots[7] = 12.5
    snap = hc.Snapshot(D(2026, 3, 5), 123.0, D(2026, 3, 1), {D(2026, 3, 2): slots})
    assert hc.from_dict(json.loads(json.dumps(hc.to_dict(snap)))) == snap


# -- the route ------------------------------------------------------------------------


@contextmanager
def running(db: str, cache_path: str, now: float):
    server = serve(db, host="127.0.0.1", port=0, now=lambda: now, heatmap_cache_path=cache_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get(base: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_heatmap_route_serves_completed_days(tmp_path) -> None:
    db = str(tmp_path / "k.db")
    # Machine-local zone (as the server uses): 10:00-10:10 two days ago.
    two_days_ago = dt.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    two_days_ago -= dt.timedelta(days=2)
    start = two_days_ago.timestamp()
    seed(db, [(start, start + 600)])
    with running(db, str(tmp_path / "h.json"), now=dt.datetime.now().timestamp()) as base:
        status, body = get(base, "/api/heatmap")
        assert status == 200
        assert body["days_param"] == "all" and body["slot_minutes"] == 5
        assert body["days"] == 2  # two days ago + yesterday; today excluded
        assert len(body["seconds"]) == heatmap.SLOTS_PER_DAY
        assert body["seconds"][120] == pytest.approx(300.0)
        assert body["seconds"][121] == pytest.approx(300.0)
        assert body["active_days"][120] == 1

        status, body = get(base, "/api/heatmap?days=7")
        assert status == 200 and body["days"] == 2

        status, body = get(base, "/api/heatmap?days=14")
        assert status == 400 and "days must be one of" in body["error"]
    assert (tmp_path / "h.json").exists()
