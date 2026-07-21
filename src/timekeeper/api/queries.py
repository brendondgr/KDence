"""Pure read-back query logic -- spans in, view-shaped aggregates out.

No SQL, no HTTP, no clock of its own: every function takes an explicit ``now`` and a
``[start, end)`` window, so the whole layer is deterministic and unit-testable (this is
where Phase 5 correctness lives). The HTTP layer (``api/server.py``) is a thin shell that
opens a read-only connection, hands the rows here, and serialises the results.

Two rules from earlier phases are applied here, and only here:

- **The local-day rule (Phase 4.1).** Storage is day-agnostic -- spans hold absolute
  wall-clock ``start_at``/``end_at``. :func:`range_window` computes the local TODAY / WEEK /
  MONTH bounds and everything else **clamps** spans to that window, so a span crossing local
  midnight contributes only its in-window slice.
- **Idle is the absence of a span (Phase 4).** Nothing here invents idle time; totals and
  timelines only ever sum stored active spans.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from timekeeper.grouping.categories import CategoryConfig, resolve
from timekeeper.grouping.palette import variant
from timekeeper.storage.store import SpanRow

# Named periods. "today" is the day containing *now*; "day" is the day containing the
# navigation anchor (Phase 9) -- same computation, different intent. WEEK starts Monday.
RANGES = ("today", "day", "week", "month", "year")

# Bucket granularities for the time-series charts (Phase 9). "hour" uses fixed 3600s steps;
# "day"/"week"/"month" are calendar-aligned in local time.
GRANULARITIES = ("hour", "day", "week", "month")

# A current session is only "live" if its last heartbeat is this fresh (a few collector
# intervals). Older open rows mean the daemon stopped without a clean close.
DEFAULT_STALE_AFTER_SECONDS = 15.0


@dataclass(frozen=True)
class Window:
    start: float
    end: float


@dataclass(frozen=True)
class AppTotal:
    app_class: str | None
    seconds: float
    sessions: int
    share: float  # 0..1 of the window's total active time


@dataclass(frozen=True)
class SiteTotal:
    """One host's slice of a single browser's active time (the table drill-down)."""

    site: str | None  # normalised host / "(local app)" / None for un-sited browser time
    seconds: float
    sessions: int
    share: float  # 0..1 of the owning browser's active time


@dataclass(frozen=True)
class GroupMember:
    """One application inside a category, coloured as a variant of the category's base."""

    app_class: str | None
    seconds: float
    sessions: int
    share: float  # 0..1 of the *group's* active time
    color: str


@dataclass(frozen=True)
class GroupTotal:
    """A category's rolled-up total plus its member apps (the group-basis table view)."""

    id: str
    name: str
    color: str
    seconds: float
    sessions: int
    share: float  # 0..1 of the window's total active time
    apps: list[GroupMember]


@dataclass(frozen=True)
class TimelineSpan:
    app_class: str | None
    title: str | None
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class Bucket:
    start: float
    end: float
    active_seconds: float
    apps: dict[str | None, float]  # app_class -> active seconds in this bucket


@dataclass(frozen=True)
class CurrentState:
    active: bool
    app_class: str | None
    title: str | None
    session_seconds: float
    as_of: float | None  # latest heartbeat seen, or None if the store is empty


# -- windowing ----------------------------------------------------------------


def range_window(
    now: float,
    range_name: str,
    tz: _dt.tzinfo | None = None,
    anchor: float | None = None,
) -> Window:
    """Local period bounds as a ``[start, end)`` wall-clock window.

    The period is the DAY / WEEK / MONTH / YEAR **containing** ``anchor`` -- or, when
    ``anchor`` is ``None``, containing ``now`` (so ``"today"`` stays live). This one function
    powers both the live view and Phase 9's date navigation. ``tz=None`` means the machine's
    local zone; tests pass a fixed zone for determinism. WEEK starts on Monday.
    """
    if range_name not in RANGES:
        raise ValueError(f"range must be one of {RANGES}, got {range_name!r}")
    effective = now if anchor is None else anchor
    local = _dt.datetime.fromtimestamp(effective, tz)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_name in ("today", "day"):
        start = midnight
        end = midnight + _dt.timedelta(days=1)
    elif range_name == "week":
        start = midnight - _dt.timedelta(days=midnight.weekday())  # back to Monday
        end = start + _dt.timedelta(days=7)
    elif range_name == "month":
        start = midnight.replace(day=1)
        end = _next_month(start)
    else:  # year
        start = midnight.replace(month=1, day=1)
        end = start.replace(year=start.year + 1)
    return Window(start.timestamp(), end.timestamp())


def custom_window(start: float, end: float) -> Window:
    """An explicit ``[start, end)`` window. Raises if it is not strictly positive-width."""
    if end <= start:
        raise ValueError(f"custom window end must be after start (got {start} .. {end})")
    return Window(start, end)


def local_date_to_timestamp(date_str: str, tz: _dt.tzinfo | None = None) -> float:
    """Parse a ``YYYY-MM-DD`` local date to its local-midnight timestamp.

    This is the seam where the API's date parameters become wall-clock instants; the day the
    string names is interpreted in the machine's local zone (``tz=None``).
    """
    try:
        year, month, day = (int(part) for part in date_str.split("-"))
        return _dt.datetime(year, month, day, tzinfo=tz).timestamp()
    except (ValueError, TypeError) as exc:
        raise ValueError(f"date must be YYYY-MM-DD, got {date_str!r}") from exc


def _next_month(first_of_month: _dt.datetime) -> _dt.datetime:
    if first_of_month.month == 12:
        return first_of_month.replace(year=first_of_month.year + 1, month=1)
    return first_of_month.replace(month=first_of_month.month + 1)


def auto_granularity(window: Window) -> str:
    """Pick a bucket size that keeps a chart readable/bounded across the window's length.

    Hourly for a day or two, daily up to ~3 months, weekly up to ~2 years, monthly beyond.
    Overridable by callers; the thresholds are tunable (see the Phase 9 plan).
    """
    days = (window.end - window.start) / 86400.0
    if days <= 2:
        return "hour"
    if days <= 92:
        return "day"
    if days <= 731:
        return "week"
    return "month"


def _bucket_edges(window: Window, granularity: str, tz: _dt.tzinfo | None) -> list[float]:
    """Boundary timestamps partitioning the window into calendar-aligned buckets.

    "hour" steps a fixed 3600s (a documented small skew across DST, accepted for a personal
    tracker -- Phase 4.1); "day"/"week"/"month" step whole local calendar units so buckets
    line up with midnights / Mondays / first-of-month regardless of the window's origin.
    """
    if granularity not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}, got {granularity!r}")
    edges = [window.start]
    if granularity == "hour":
        t = window.start
        while t < window.end - 1e-6:
            t = min(t + 3600.0, window.end)
            edges.append(t)
        return edges
    cur = _dt.datetime.fromtimestamp(window.start, tz)
    while cur.timestamp() < window.end - 1e-6:
        if granularity == "day":
            nxt = _local_midnight(cur, tz) + _dt.timedelta(days=1)
            nxt = _local_midnight(nxt, tz)
        elif granularity == "week":
            base = _local_midnight(cur, tz)
            nxt = _local_midnight(base + _dt.timedelta(days=7), tz)
        else:  # month
            nxt = _next_month(_local_midnight(cur, tz).replace(day=1))
        ts = min(nxt.timestamp(), window.end)
        edges.append(ts)
        cur = nxt
    return edges


def _local_midnight(dt: _dt.datetime, tz: _dt.tzinfo | None) -> _dt.datetime:
    """Local midnight of ``dt``'s calendar date -- re-derived from the date to stay DST-sane."""
    return _dt.datetime(dt.year, dt.month, dt.day, tzinfo=tz)


def bucket_series(
    spans: list[SpanRow],
    window: Window,
    granularity: str,
    tz: _dt.tzinfo | None = None,
) -> list[Bucket]:
    """Per-bucket active seconds + per-app breakdown over the window (idle excluded).

    The bounded, pre-aggregated series the charts use for long ranges, so a year view never
    ships every raw span. Each bucket's numbers reconcile with :func:`active_seconds` /
    :func:`per_app_totals` over the same sub-window.
    """
    edges = _bucket_edges(window, granularity, tz)
    out: list[Bucket] = []
    for i in range(len(edges) - 1):
        b_start, b_end = edges[i], edges[i + 1]
        b_window = Window(b_start, b_end)
        apps: dict[str | None, float] = {}
        active = 0.0
        for span in spans:
            clipped = clamp(span, b_window)
            if clipped is None:
                continue
            dur = clipped[1] - clipped[0]
            apps[span.app_class] = apps.get(span.app_class, 0.0) + dur
            active += dur
        out.append(Bucket(start=b_start, end=b_end, active_seconds=active, apps=apps))
    return out


# -- clamping + aggregates ----------------------------------------------------


def clamp(span: SpanRow, window: Window) -> tuple[float, float] | None:
    """Intersect a span with the window; ``None`` if it falls entirely outside."""
    start = max(span.start_at, window.start)
    end = min(span.end_at, window.end)
    if end <= start:
        return None
    return start, end


def active_seconds(spans: list[SpanRow], window: Window) -> float:
    """Total active time within the window (each span clamped to it)."""
    total = 0.0
    for span in spans:
        clipped = clamp(span, window)
        if clipped is not None:
            total += clipped[1] - clipped[0]
    return total


def per_app_totals(spans: list[SpanRow], window: Window) -> list[AppTotal]:
    """Per-application seconds, session count, and share -- sorted longest first.

    A "session" is one stored span that overlaps the window (rapid re-focus of the same app
    counts as several). Share is the fraction of the window's total active time.
    """
    seconds: dict[str | None, float] = {}
    sessions: dict[str | None, int] = {}
    for span in spans:
        clipped = clamp(span, window)
        if clipped is None:
            continue
        key = span.app_class
        seconds[key] = seconds.get(key, 0.0) + (clipped[1] - clipped[0])
        sessions[key] = sessions.get(key, 0) + 1

    grand_total = sum(seconds.values())
    totals = [
        AppTotal(
            app_class=key,
            seconds=secs,
            sessions=sessions[key],
            share=(secs / grand_total) if grand_total > 0 else 0.0,
        )
        for key, secs in seconds.items()
    ]
    # Longest first; ties broken by app class for a stable order (None sorts last).
    totals.sort(key=lambda a: (-a.seconds, a.app_class or "￿"))
    return totals


def group_totals(app_totals: list[AppTotal], config: CategoryConfig) -> list[GroupTotal]:
    """Roll per-application totals up into their categories (the group-basis view).

    Each app is placed by :func:`~timekeeper.grouping.categories.resolve` (its assignment, or
    the reserved Uncategorized), so the per-group sums always reconcile with ``app_totals`` and
    the group shares sum to 1. Member apps are coloured as :func:`~timekeeper.grouping.palette.
    variant` shades of the category base; empty categories are omitted; groups and members are
    sorted longest-first.
    """
    by_id = config.by_id()
    order = [c.id for c in config.categories]
    buckets: dict[str, list[AppTotal]] = {}
    for a in app_totals:
        buckets.setdefault(resolve(a.app_class, config), []).append(a)

    grand = sum(a.seconds for a in app_totals)
    groups: list[GroupTotal] = []
    for cid in order:
        members = buckets.get(cid)
        if not members:
            continue
        members.sort(key=lambda a: (-a.seconds, a.app_class or "￿"))
        secs = sum(a.seconds for a in members)
        sess = sum(a.sessions for a in members)
        base = by_id[cid].color
        n = len(members)
        member_totals = [
            GroupMember(
                app_class=a.app_class,
                seconds=a.seconds,
                sessions=a.sessions,
                share=(a.seconds / secs) if secs > 0 else 0.0,
                color=variant(base, i, n),
            )
            for i, a in enumerate(members)
        ]
        groups.append(
            GroupTotal(
                id=cid,
                name=by_id[cid].name,
                color=base,
                seconds=secs,
                sessions=sess,
                share=(secs / grand) if grand > 0 else 0.0,
                apps=member_totals,
            )
        )
    groups.sort(key=lambda g: (-g.seconds, g.name))
    return groups


def per_app_site_totals(spans: list[SpanRow], window: Window) -> dict[str | None, list[SiteTotal]]:
    """Per-application host breakdowns for the table drill-down -- browsers only.

    Groups each app's clamped spans by ``site``. Only apps that recorded at least one real
    (non-``None``) site get an entry -- in practice the browsers, since nothing else stores a
    site. Any un-sited browser time (an internal page, or a moment with no fresh tab report) is
    kept as a ``site=None`` bucket so each breakdown still sums to that browser's own total and
    reconciles with :func:`per_app_totals`. Each list is sorted longest-first.
    """
    per_app: dict[str | None, dict[str | None, list[float]]] = {}
    for span in spans:
        clipped = clamp(span, window)
        if clipped is None:
            continue
        dur = clipped[1] - clipped[0]
        sites = per_app.setdefault(span.app_class, {})
        entry = sites.setdefault(span.site, [0.0, 0.0])
        entry[0] += dur
        entry[1] += 1

    out: dict[str | None, list[SiteTotal]] = {}
    for app_class, sites in per_app.items():
        if not any(site is not None for site in sites):
            continue  # no real site here -> not a browser row, no drill-down
        app_total = sum(secs for secs, _ in sites.values())
        totals = [
            SiteTotal(
                site=site,
                seconds=secs,
                sessions=int(count),
                share=(secs / app_total) if app_total > 0 else 0.0,
            )
            for site, (secs, count) in sites.items()
        ]
        totals.sort(key=lambda s: (-s.seconds, s.site or "￿"))
        out[app_class] = totals
    return out


def timeline(spans: list[SpanRow], window: Window) -> list[TimelineSpan]:
    """Active spans clamped to the window, in chronological order (idle excluded)."""
    out: list[TimelineSpan] = []
    for span in spans:
        clipped = clamp(span, window)
        if clipped is None:
            continue
        out.append(TimelineSpan(span.app_class, span.title, clipped[0], clipped[1]))
    out.sort(key=lambda s: s.start)
    return out


def current_state(
    open_span: SpanRow | None,
    latest_end: float | None,
    now: float,
    stale_after: float = DEFAULT_STALE_AFTER_SECONDS,
) -> CurrentState:
    """Derive the live session from the store's open row (reader/writer isolation).

    An ``open`` row whose last heartbeat is fresh means the user is active in that app; its
    session length is measured from the span's start. No fresh open row means idle (or the
    daemon has stopped). ``latest_end`` (the newest heartbeat in the store) is echoed as
    ``as_of`` so the view can flag stale data.
    """
    if open_span is not None and (now - open_span.end_at) <= stale_after:
        return CurrentState(
            active=True,
            app_class=open_span.app_class,
            title=open_span.title,
            session_seconds=max(0.0, now - open_span.start_at),
            as_of=latest_end,
        )
    return CurrentState(
        active=False, app_class=None, title=None, session_seconds=0.0, as_of=latest_end
    )
