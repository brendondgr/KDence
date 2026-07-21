"""Pure time model -- turn instantaneous observations into honest durations.

This is where correctness lives (build-plan Step 4.2). It runs on injected wall-clock
timestamps and holds no hardware, no SQL and no clock of its own -- feed it a sequence of
events and it produces contiguous, non-overlapping :class:`Span`s. The four honesty rules
are written up in ``docs/plans/phase-4-time-model-and-storage.md``; in short:

- **Stitched heartbeats.** Same-window heartbeats within ``max_gap`` extend one span; a
  different window closes the old span and opens a new one at the same instant (so spans
  are contiguous). Active time is the sum of believable heartbeat-to-heartbeat gaps.
- **Back-dating the idle boundary.** ``idle(at)`` closes the open span at ``at`` -- the
  caller passes the *back-dated* last-input instant (from ``ActivityMonitor``), so the
  trailing idle window is never counted as active. (Step 4.2 case b.)
- **Suspend gap.** A heartbeat gap greater than ``max_gap`` is a break, not activity: the
  open span ends at its last in-window heartbeat and a fresh one starts later. Suspended
  hours never become phantom active time. (Step 4.2 case d.)
- **Open span on crash.** The model keeps the open span's ``end`` bumped to the latest
  heartbeat; on a clean shutdown call ``stop(at)``. Recovery after a *crash* (no ``stop``)
  is the storage layer's job -- it finalizes the open span at its last stored heartbeat.

The ``on_open`` / ``on_extend`` / ``on_close`` callbacks let the storage layer map each
change to exactly one SQLite write without re-deriving state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Span:
    """A finalized active span: a single window held continuously over ``[start, end]``."""

    app_class: str | None  # None == the bare desktop (active but appless)
    title: str | None
    start: float  # Unix seconds (wall clock)
    end: float  # Unix seconds; >= start
    site: str | None = None  # browser sub-identity (active tab host); None for non-browsers

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def label(self) -> str:
        app = self.app_class or "(desktop)"
        return f"{app} — {self.title}" if self.title else app


@dataclass(frozen=True)
class OpenSpan:
    """The current, still-growing span. ``end`` tracks the latest heartbeat seen."""

    app_class: str | None
    title: str | None
    start: float
    end: float
    site: str | None = None

    def finalize(self) -> Span:
        return Span(self.app_class, self.title, self.start, self.end, self.site)


class Timeline:
    """Consume ``active`` / ``idle`` / ``stop`` events; emit honest, non-overlapping spans.

    Args:
        max_gap_seconds: the largest believable gap between two heartbeats. A larger gap
            means a suspend or a stalled process, so the earlier span ends at its last
            heartbeat rather than bridging the gap. Must be positive.
        on_open: called with the new :class:`OpenSpan` when a span begins.
        on_extend: called with the updated :class:`OpenSpan` when a heartbeat advances
            ``end`` (same window, within ``max_gap``).
        on_close: called with the finalized :class:`Span` when a span ends (window switch,
            idle, suspend break, or ``stop``).
    """

    def __init__(
        self,
        *,
        max_gap_seconds: float,
        on_open: Callable[[OpenSpan], None] | None = None,
        on_extend: Callable[[OpenSpan], None] | None = None,
        on_close: Callable[[Span], None] | None = None,
    ) -> None:
        if max_gap_seconds <= 0:
            raise ValueError("max_gap_seconds must be positive")
        self._max_gap = float(max_gap_seconds)
        self._on_open = on_open
        self._on_extend = on_extend
        self._on_close = on_close
        self._open: OpenSpan | None = None
        self._closed: list[Span] = []

    @property
    def open_span(self) -> OpenSpan | None:
        """The current growing span, or ``None`` while idle / not yet started."""
        return self._open

    @property
    def closed_spans(self) -> tuple[Span, ...]:
        """All finalized spans so far, in order."""
        return tuple(self._closed)

    @property
    def spans(self) -> tuple[Span, ...]:
        """Every span as it stands now: the finalized ones plus the open one, finalized."""
        if self._open is None:
            return tuple(self._closed)
        return (*self._closed, self._open.finalize())

    def active(
        self,
        at: float,
        app_class: str | None,
        title: str | None = None,
        site: str | None = None,
    ) -> None:
        """Heartbeat: at wall-time ``at`` the user is active in this window.

        Same window within ``max_gap`` extends the open span; a different window -- a change of
        app, title, **or** browser ``site`` -- (or a suspend-sized gap) finalizes the open span
        and starts a new one, so a hop between two sites in the same browser splits cleanly.
        """
        current = self._open
        if current is None:
            self._start(at, app_class, title, site)
            return

        gap = at - current.end
        same_window = (
            app_class == current.app_class and title == current.title and site == current.site
        )

        if gap > self._max_gap:
            # Suspend / stall: don't bridge the gap. End the old span at its last
            # heartbeat, begin a fresh one at `at` (even if it's the same window).
            self._close(current.end)
            self._start(at, app_class, title, site)
        elif same_window:
            self._extend(at)
        else:
            # Window switch within a believable interval: contiguous boundary at `at`.
            self._close(at)
            self._start(at, app_class, title, site)

    def idle(self, at: float) -> None:
        """The user is idle as of wall-time ``at`` (the back-dated last-input instant).

        Closes the open span at ``at``. A no-op if already idle. The trailing idle window
        is therefore excluded from active time -- the honesty rule of Step 4.2 case (b).
        """
        if self._open is not None:
            self._close(at)

    def stop(self, at: float) -> None:
        """Graceful shutdown: finalize the open span at ``at``. A no-op if already idle."""
        if self._open is not None:
            self._close(at)

    # -- internals -------------------------------------------------------------

    def _start(
        self, at: float, app_class: str | None, title: str | None, site: str | None = None
    ) -> None:
        self._open = OpenSpan(app_class, title, start=at, end=at, site=site)
        if self._on_open is not None:
            self._on_open(self._open)

    def _extend(self, at: float) -> None:
        assert self._open is not None
        # Never move `end` backwards (guards against a wall-clock jump).
        if at <= self._open.end:
            return
        self._open = replace(self._open, end=at)
        if self._on_extend is not None:
            self._on_extend(self._open)

    def _close(self, at: float) -> None:
        assert self._open is not None
        end = at if at >= self._open.start else self._open.start
        span = replace(self._open, end=end).finalize()
        self._open = None
        self._closed.append(span)
        if self._on_close is not None:
            self._on_close(span)
