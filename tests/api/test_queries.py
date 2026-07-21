"""Step 5.1/5.2 (synthetic) -- the pure read-back query logic.

Deterministic: every timestamp is built in a fixed UTC zone and ``now`` is explicit, so the
local-day windowing and clamping are provable without a wall clock. Idle never appears
because idle is the absence of a span (Phase 4) -- the timeline/totals only sum stored
active spans. Boundary cases (empty day, a single open span, a span across midnight) are the
Step 5.2 checks.
"""

from __future__ import annotations

import datetime as dt

from timekeeper.api import queries
from timekeeper.api.queries import Window
from timekeeper.storage.store import SpanRow

UTC = dt.timezone.utc


def ts(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> float:
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=UTC).timestamp()


def span(
    app: str | None,
    start: float,
    end: float,
    *,
    open: bool = False,
    title: str | None = None,
    site: str | None = None,
    id: int = 1,
) -> SpanRow:
    return SpanRow(
        id=id, app_class=app, title=title, site=site, start_at=start, end_at=end, open=open
    )


# -- windowing ----------------------------------------------------------------


def test_range_window_today_is_local_midnight_to_midnight() -> None:
    now = ts(2026, 7, 21, 14, 30)
    w = queries.range_window(now, "today", tz=UTC)
    assert w.start == ts(2026, 7, 21, 0, 0)
    assert w.end == ts(2026, 7, 22, 0, 0)


def test_range_window_week_starts_monday() -> None:
    # 2026-07-21 is a Tuesday; the week runs Mon 07-20 .. Mon 07-27.
    w = queries.range_window(ts(2026, 7, 21, 9), "week", tz=UTC)
    assert w.start == ts(2026, 7, 20, 0, 0)
    assert w.end == ts(2026, 7, 27, 0, 0)


def test_range_window_month() -> None:
    w = queries.range_window(ts(2026, 7, 21), "month", tz=UTC)
    assert w.start == ts(2026, 7, 1, 0, 0)
    assert w.end == ts(2026, 8, 1, 0, 0)


def test_range_window_month_wraps_december() -> None:
    w = queries.range_window(ts(2026, 12, 15), "month", tz=UTC)
    assert w.start == ts(2026, 12, 1)
    assert w.end == ts(2027, 1, 1)


# -- clamping + totals --------------------------------------------------------


def test_active_seconds_sums_clamped_durations() -> None:
    w = Window(0.0, 100.0)
    spans = [span("a", 10.0, 30.0), span("b", 40.0, 90.0)]  # 20 + 50
    assert queries.active_seconds(spans, w) == 70.0


def test_span_across_midnight_is_split_by_the_day_rule() -> None:
    # A span 23:30 -> 00:30 belongs half to each day. "Today" (the 21st) gets only 00:00-00:30.
    crossing = span("code", ts(2026, 7, 20, 23, 30), ts(2026, 7, 21, 0, 30))
    today = queries.range_window(ts(2026, 7, 21, 8), "today", tz=UTC)
    yesterday = Window(ts(2026, 7, 20), ts(2026, 7, 21))
    assert queries.active_seconds([crossing], today) == 1800.0  # the 00:00-00:30 half
    assert queries.active_seconds([crossing], yesterday) == 1800.0  # the 23:30-00:00 half


def test_span_entirely_outside_the_window_is_ignored() -> None:
    w = Window(100.0, 200.0)
    assert queries.active_seconds([span("a", 0.0, 50.0)], w) == 0.0
    assert queries.per_app_totals([span("a", 0.0, 50.0)], w) == []
    assert queries.timeline([span("a", 0.0, 50.0)], w) == []


def test_per_app_totals_shares_sessions_and_order() -> None:
    w = Window(0.0, 10_000.0)
    spans = [
        span("code", 0.0, 2000.0, id=1),  # code: 2000 + 1000 = 3000 over 2 sessions
        span("firefox", 2000.0, 3000.0, id=2),  # firefox: 1000 over 1 session
        span("code", 3000.0, 4000.0, id=3),
    ]
    totals = queries.per_app_totals(spans, w)
    assert [t.app_class for t in totals] == ["code", "firefox"]  # longest first
    code, firefox = totals
    assert (code.seconds, code.sessions) == (3000.0, 2)
    assert (firefox.seconds, firefox.sessions) == (1000.0, 1)
    assert round(code.share, 4) == 0.75
    assert round(firefox.share, 4) == 0.25
    assert round(sum(t.share for t in totals), 6) == 1.0


def test_desktop_span_keeps_null_app_class_in_totals() -> None:
    w = Window(0.0, 100.0)
    totals = queries.per_app_totals([span(None, 0.0, 50.0)], w)
    assert totals[0].app_class is None
    assert totals[0].seconds == 50.0


def test_timeline_is_clamped_and_sorted() -> None:
    w = Window(100.0, 200.0)
    spans = [
        span("b", 150.0, 250.0, id=2),  # clamped to 150-200
        span("a", 50.0, 120.0, id=1),  # clamped to 100-120
    ]
    tl = queries.timeline(spans, w)
    assert [(s.app_class, s.start, s.end) for s in tl] == [
        ("a", 100.0, 120.0),
        ("b", 150.0, 200.0),
    ]
    assert [s.seconds for s in tl] == [20.0, 50.0]


# -- current state ------------------------------------------------------------


def test_current_state_active_from_a_fresh_open_span() -> None:
    now = 1000.0
    open_span = span("code", start=940.0, end=999.0, open=True)  # last heartbeat 1s ago
    state = queries.current_state(open_span, latest_end=999.0, now=now)
    assert state.active is True
    assert state.app_class == "code"
    assert state.session_seconds == 60.0  # now - start
    assert state.as_of == 999.0


def test_current_state_idle_when_no_open_span() -> None:
    state = queries.current_state(None, latest_end=500.0, now=1000.0)
    assert state.active is False
    assert state.app_class is None
    assert state.session_seconds == 0.0
    assert state.as_of == 500.0  # still reports last activity for staleness


def test_current_state_stale_open_span_reads_as_idle() -> None:
    # An open row whose last heartbeat is ancient means the daemon died, not "active".
    now = 100_000.0
    stale = span("code", start=0.0, end=50.0, open=True)
    state = queries.current_state(stale, latest_end=50.0, now=now, stale_after=15.0)
    assert state.active is False


# -- Step 5.2 boundaries ------------------------------------------------------


def test_empty_day_returns_zeros_not_errors() -> None:
    w = queries.range_window(ts(2026, 7, 21), "today", tz=UTC)
    assert queries.active_seconds([], w) == 0.0
    assert queries.per_app_totals([], w) == []
    assert queries.timeline([], w) == []
    assert queries.current_state(None, None, now=ts(2026, 7, 21)).active is False


def test_single_open_span_counts_up_to_now() -> None:
    # A day with exactly one, still-open span: it counts from its start to the query time.
    day = ts(2026, 7, 21)
    start = day + 3600  # 01:00
    now = day + 3600 + 300  # 5 minutes of an open session
    open_span = span("code", start=start, end=now, open=True)
    w = queries.range_window(now, "today", tz=UTC)
    assert queries.active_seconds([open_span], w) == 300.0
    state = queries.current_state(open_span, latest_end=now, now=now)
    assert state.active is True
    assert state.session_seconds == 300.0


# -- per-browser site drill-down (browser-activity scope) ---------------------


def test_per_app_site_totals_reconcile_with_the_app_total() -> None:
    # A browser across two hosts + a stretch of un-sited browser time, plus a non-browser app.
    win = Window(ts(2026, 3, 9), ts(2026, 3, 10))
    spans = [
        span("librewolf", ts(2026, 3, 9, 9), ts(2026, 3, 9, 10), site="youtube.com", id=1),
        span("librewolf", ts(2026, 3, 9, 10), ts(2026, 3, 9, 12), site="github.com", id=2),
        span("librewolf", ts(2026, 3, 9, 12), ts(2026, 3, 9, 12, 30), site="youtube.com", id=3),
        span("librewolf", ts(2026, 3, 9, 13), ts(2026, 3, 9, 13, 30), site=None, id=4),
        span("code", ts(2026, 3, 9, 14), ts(2026, 3, 9, 15), id=5),  # non-browser, no site
    ]
    apps = {a.app_class: a for a in queries.per_app_totals(spans, win)}
    site_map = queries.per_app_site_totals(spans, win)

    # Non-browser app has no drill-down.
    assert "code" not in site_map
    # Browser drill-down sums exactly to the browser's own total.
    sites = site_map["librewolf"]
    assert round(sum(s.seconds for s in sites), 6) == round(apps["librewolf"].seconds, 6)
    # Shares within the browser sum to 1.
    assert round(sum(s.share for s in sites), 6) == 1.0

    by_site = {s.site: s for s in sites}
    assert round(by_site["youtube.com"].seconds, 6) == round(1.5 * 3600, 6)  # 1h + 30m
    assert by_site["youtube.com"].sessions == 2  # two separate spans
    assert round(by_site["github.com"].seconds, 6) == round(2 * 3600, 6)
    assert None in by_site  # un-sited browser time kept so the breakdown reconciles


def test_per_app_site_totals_sorted_longest_first() -> None:
    win = Window(ts(2026, 3, 9), ts(2026, 3, 10))
    spans = [
        span("firefox", ts(2026, 3, 9, 9), ts(2026, 3, 9, 9, 30), site="a.com", id=1),
        span("firefox", ts(2026, 3, 9, 10), ts(2026, 3, 9, 12), site="b.com", id=2),
    ]
    sites = queries.per_app_site_totals(spans, win)["firefox"]
    assert [s.site for s in sites] == ["b.com", "a.com"]
