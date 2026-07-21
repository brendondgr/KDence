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

from timekeeper.storage.store import SpanRow

RANGES = ("today", "week", "month")

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
class TimelineSpan:
    app_class: str | None
    title: str | None
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class CurrentState:
    active: bool
    app_class: str | None
    title: str | None
    session_seconds: float
    as_of: float | None  # latest heartbeat seen, or None if the store is empty


# -- windowing ----------------------------------------------------------------


def range_window(now: float, range_name: str, tz: _dt.tzinfo | None = None) -> Window:
    """Local TODAY / WEEK / MONTH bounds as a ``[start, end)`` wall-clock window.

    ``tz=None`` means the machine's local zone (what the user means by "today"); tests pass
    a fixed zone for determinism. WEEK starts on Monday.
    """
    if range_name not in RANGES:
        raise ValueError(f"range must be one of {RANGES}, got {range_name!r}")
    local = _dt.datetime.fromtimestamp(now, tz)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_name == "today":
        start = midnight
        end = midnight + _dt.timedelta(days=1)
    elif range_name == "week":
        start = midnight - _dt.timedelta(days=midnight.weekday())  # back to Monday
        end = start + _dt.timedelta(days=7)
    else:  # month
        start = midnight.replace(day=1)
        end = _next_month(start)
    return Window(start.timestamp(), end.timestamp())


def _next_month(first_of_month: _dt.datetime) -> _dt.datetime:
    if first_of_month.month == 12:
        return first_of_month.replace(year=first_of_month.year + 1, month=1)
    return first_of_month.replace(month=first_of_month.month + 1)


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
