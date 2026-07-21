"""Step 9.2 (synthetic) -- anchored/custom windows + the pure bucket series.

Deterministic in a fixed UTC zone: anchoring on an arbitrary past date must select the period
*containing that date*, custom ranges must clamp, and the bucket series must reconcile with the
window-level aggregates it summarizes.
"""

from __future__ import annotations

import datetime as dt

import pytest

from kdence.api import queries
from kdence.storage.store import SpanRow

UTC = dt.timezone.utc


def ts(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> float:
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=UTC).timestamp()


def span(app: str | None, start: float, end: float, *, id: int = 1) -> SpanRow:
    return SpanRow(id=id, app_class=app, title=None, start_at=start, end_at=end, open=False)


# -- anchored windows ---------------------------------------------------------


def test_anchor_selects_the_day_containing_that_date_not_now() -> None:
    now = ts(2026, 7, 21, 15)  # a Tuesday in July
    anchor = ts(2026, 3, 9, 13)  # a Monday in March, months earlier
    win = queries.range_window(now, "day", tz=UTC, anchor=anchor)
    assert win.start == ts(2026, 3, 9)
    assert win.end == ts(2026, 3, 10)


def test_anchor_week_is_the_monday_week_containing_the_anchor() -> None:
    anchor = ts(2026, 3, 11, 9)  # Wednesday
    win = queries.range_window(ts(2026, 7, 21), "week", tz=UTC, anchor=anchor)
    assert win.start == ts(2026, 3, 9)  # Monday
    assert win.end == ts(2026, 3, 16)


def test_anchor_month_and_year_bounds() -> None:
    anchor = ts(2024, 2, 15, 12)  # a leap February
    month = queries.range_window(0.0, "month", tz=UTC, anchor=anchor)
    assert month.start == ts(2024, 2, 1)
    assert month.end == ts(2024, 3, 1)  # spans Feb 29 correctly
    year = queries.range_window(0.0, "year", tz=UTC, anchor=anchor)
    assert year.start == ts(2024, 1, 1)
    assert year.end == ts(2025, 1, 1)


def test_no_anchor_falls_back_to_now() -> None:
    now = ts(2026, 7, 21, 15)
    assert queries.range_window(now, "day", tz=UTC) == queries.range_window(now, "today", tz=UTC)


# -- custom windows + date parsing --------------------------------------------


def test_custom_window_requires_positive_width() -> None:
    assert queries.custom_window(100.0, 200.0) == queries.Window(100.0, 200.0)
    with pytest.raises(ValueError):
        queries.custom_window(200.0, 200.0)
    with pytest.raises(ValueError):
        queries.custom_window(300.0, 200.0)


def test_local_date_to_timestamp_is_local_midnight() -> None:
    assert queries.local_date_to_timestamp("2026-03-09", tz=UTC) == ts(2026, 3, 9)
    with pytest.raises(ValueError):
        queries.local_date_to_timestamp("2026/03/09", tz=UTC)
    with pytest.raises(ValueError):
        queries.local_date_to_timestamp("not-a-date", tz=UTC)


# -- auto granularity ---------------------------------------------------------


def test_auto_granularity_scales_with_window_length() -> None:
    day = queries.range_window(0.0, "day", tz=UTC, anchor=ts(2026, 3, 9))
    month = queries.range_window(0.0, "month", tz=UTC, anchor=ts(2026, 3, 9))
    year = queries.range_window(0.0, "year", tz=UTC, anchor=ts(2026, 3, 9))
    assert queries.auto_granularity(day) == "hour"
    assert queries.auto_granularity(month) == "day"
    assert queries.auto_granularity(year) == "week"
    # A five-year custom window -> monthly.
    five_years = queries.custom_window(ts(2020, 1, 1), ts(2025, 1, 1))
    assert queries.auto_granularity(five_years) == "month"


# -- bucket series ------------------------------------------------------------


def test_hour_buckets_partition_a_day_and_reconcile() -> None:
    win = queries.range_window(0.0, "day", tz=UTC, anchor=ts(2026, 3, 9))
    spans = [
        span("code", ts(2026, 3, 9, 9, 0), ts(2026, 3, 9, 9, 30)),  # 30 min in hour 09
        span("firefox", ts(2026, 3, 9, 9, 45), ts(2026, 3, 9, 10, 15)),  # straddles 09/10
    ]
    buckets = queries.bucket_series(spans, win, "hour", tz=UTC)
    assert len(buckets) == 24
    # Hour 09 = 30 min code + 15 min firefox; hour 10 = 15 min firefox.
    assert buckets[9].active_seconds == pytest.approx(45 * 60)
    assert buckets[9].apps["code"] == pytest.approx(30 * 60)
    assert buckets[9].apps["firefox"] == pytest.approx(15 * 60)
    assert buckets[10].apps["firefox"] == pytest.approx(15 * 60)
    # The series total reconciles with the window-level active total.
    total = sum(b.active_seconds for b in buckets)
    assert total == pytest.approx(queries.active_seconds(spans, win))


def test_day_buckets_span_a_month_calendar_aligned() -> None:
    win = queries.range_window(0.0, "month", tz=UTC, anchor=ts(2026, 3, 15))
    spans = [span("code", ts(2026, 3, 15, 10), ts(2026, 3, 15, 12))]  # 2h on the 15th
    buckets = queries.bucket_series(spans, win, "day", tz=UTC)
    assert len(buckets) == 31  # March
    assert buckets[0].start == ts(2026, 3, 1)
    # Day index 14 == March 15th holds all the active time.
    assert buckets[14].active_seconds == pytest.approx(2 * 3600)
    assert sum(b.active_seconds for b in buckets) == pytest.approx(2 * 3600)


def test_bucket_per_app_reconciles_with_per_app_totals() -> None:
    win = queries.range_window(0.0, "day", tz=UTC, anchor=ts(2026, 3, 9))
    spans = [
        span("code", ts(2026, 3, 9, 9), ts(2026, 3, 9, 10), id=1),
        span("firefox", ts(2026, 3, 9, 11), ts(2026, 3, 9, 11, 30), id=2),
        span("code", ts(2026, 3, 9, 14), ts(2026, 3, 9, 14, 30), id=3),
    ]
    buckets = queries.bucket_series(spans, win, "hour", tz=UTC)
    # Sum per-app across buckets == per_app_totals over the whole window.
    agg: dict[str | None, float] = {}
    for b in buckets:
        for app, secs in b.apps.items():
            agg[app] = agg.get(app, 0.0) + secs
    totals = {t.app_class: t.seconds for t in queries.per_app_totals(spans, win)}
    assert agg == pytest.approx(totals)


def test_invalid_granularity_rejected() -> None:
    win = queries.range_window(0.0, "day", tz=UTC, anchor=ts(2026, 3, 9))
    with pytest.raises(ValueError):
        queries.bucket_series([], win, "fortnight", tz=UTC)
