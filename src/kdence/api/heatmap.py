"""Pure time-of-day heat map -- active intervals in, per-day five-minute slots out.

The heat map answers *"at what time of day am I usually active?"* across a long window, so it
is shaped differently from every other read-back aggregate: each local day is folded onto one
24-hour clock of :data:`SLOTS_PER_DAY` five-minute slots, and a window is the element-wise sum
of its days. Only **completed** local days are binned (today is still moving), which is what
lets the per-day slots be computed once and cached (see :mod:`kdence.api.heatmap_cache`).

No SQL, no clock, no file I/O: callers pass the intervals, the cut-off, and the zone, so every
function here is deterministic and unit-testable.

Slot mapping. Every real UTC offset is a multiple of five minutes, so the epoch-aligned 300 s
grid coincides with the local wall-clock grid in any zone: an interval is split on that grid
and each piece lands in ``(its local date, (hour*60 + minute) // 5)``. On a DST fall-back day
the repeated hour folds onto the same slots (so one slot can exceed 300 s that day); on a
spring-forward day the skipped hour's slots simply stay empty. Both are the recorded DST limit
(honesty-review #6), not new ones.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

SLOT_SECONDS = 300
SLOTS_PER_DAY = 24 * 60 * 60 // SLOT_SECONDS  # 288

# The window lengths the dashboard offers; ``None`` means the whole archive.
PRESET_DAYS: dict[str, int | None] = {"7": 7, "30": 30, "90": 90, "365": 365, "all": None}


@dataclass(frozen=True)
class HeatmapWindow:
    """A heat-map aggregate over the inclusive local-date range ``[first, last]``.

    ``seconds[i]`` is the total active time in slot ``i`` summed over the window's days;
    ``active_days[i]`` counts the days on which slot ``i`` saw any activity. ``days`` is the
    number of **calendar** days in the window -- the denominator for "on an average day",
    so a day the machine was off counts as a zero, not as missing.
    """

    first: _dt.date | None
    last: _dt.date | None
    days: int
    seconds: list[float]
    active_days: list[int]


def local_midnight(day: _dt.date, tz: _dt.tzinfo | None = None) -> float:
    """The wall-clock timestamp of ``day``'s local midnight (``tz=None`` = the machine's zone)."""
    return _dt.datetime(day.year, day.month, day.day, tzinfo=tz).timestamp()


def local_date(ts: float, tz: _dt.tzinfo | None = None) -> _dt.date:
    return _dt.datetime.fromtimestamp(ts, tz).date()


def daily_slots(
    intervals: Iterable[tuple[float, float]],
    until: float,
    tz: _dt.tzinfo | None = None,
) -> dict[_dt.date, list[float]]:
    """Bin active ``(start, end)`` intervals into per-local-day five-minute slots.

    Everything at or after ``until`` (normally today's local midnight) is dropped, so only
    completed days are returned. Days with no activity are absent from the result. Each value
    is a :data:`SLOTS_PER_DAY`-long list of active seconds; the grand total always equals the
    summed (clipped) interval durations.
    """
    out: dict[_dt.date, list[float]] = {}
    for start, end in intervals:
        end = min(end, until)
        t = start
        while t < end:
            boundary = (t // SLOT_SECONDS + 1) * SLOT_SECONDS
            piece_end = min(boundary, end)
            local = _dt.datetime.fromtimestamp(t, tz)
            slot = (local.hour * 60 + local.minute) // 5
            day = out.get(local.date())
            if day is None:
                day = out[local.date()] = [0.0] * SLOTS_PER_DAY
            day[slot] += piece_end - t
            t = piece_end
    return out


def resolve_range(
    preset: str,
    earliest: _dt.date | None,
    through: _dt.date | None,
) -> tuple[_dt.date, _dt.date] | None:
    """The inclusive ``(first, last)`` dates a preset covers, clamped to the archive.

    ``through`` is the last completed day and ``earliest`` the archive's first day. A preset
    of N days ends at ``through`` and starts N-1 days earlier, but never before ``earliest``;
    ``"all"`` starts at ``earliest``. ``None`` when there is no completed day yet.
    """
    if preset not in PRESET_DAYS:
        raise ValueError(f"days must be one of {tuple(PRESET_DAYS)}, got {preset!r}")
    if earliest is None or through is None or through < earliest:
        return None
    n = PRESET_DAYS[preset]
    first = earliest if n is None else max(earliest, through - _dt.timedelta(days=n - 1))
    return first, through


def aggregate(
    days: Mapping[_dt.date, Sequence[float]],
    first: _dt.date | None,
    last: _dt.date | None,
) -> HeatmapWindow:
    """Sum the per-day slots over the inclusive ``[first, last]`` range."""
    seconds = [0.0] * SLOTS_PER_DAY
    active = [0] * SLOTS_PER_DAY
    if first is None or last is None or last < first:
        return HeatmapWindow(None, None, 0, seconds, active)
    for day, slots in days.items():
        if not (first <= day <= last):
            continue
        for i, secs in enumerate(slots):
            if secs > 0:
                seconds[i] += secs
                active[i] += 1
    return HeatmapWindow(first, last, (last - first).days + 1, seconds, active)
