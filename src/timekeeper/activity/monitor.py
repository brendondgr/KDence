"""Pure active/idle decision logic -- no Wayland, no hardware, fully unit-testable.

This is the logic side of the pure/hardware seam. It consumes raw ``idled``/``resumed``
transitions (from any source, real or fake) plus its own monotonic clock, and answers
"active or idle right now?" by applying the user's threshold.

Design note -- why the threshold lives here, not in the compositor request: the idle
source detects idle-*start* at a small resolution, but declaring the user "idle" is a
policy decision (e.g. 5 minutes). Keeping it here means the interesting behaviour
(threshold crossing, back-dating, resume reset) is testable with fake timestamps and
never needs a live session. See docs/plans/phase-1-activity-detection.md.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable


class ActivityState(enum.Enum):
    ACTIVE = "active"
    IDLE = "idle"


class ActivityMonitor:
    """Decide active vs. idle from idle transitions and elapsed time.

    Args:
        threshold_seconds: how long the seat must stay idle before the user is
            reported ``IDLE`` (e.g. 300 for 5 minutes).
        resolution_seconds: the idle source's notification timeout, in seconds. When
            an ``idled`` transition arrives the seat has *already* been idle for this
            long, so the idle start is back-dated by it -- the active span ends near
            last input, not near detection. This is the honesty rule the time model
            (Phase 4) depends on.
        clock: monotonic time source; injectable for tests. Defaults to
            ``time.monotonic``.
    """

    def __init__(
        self,
        threshold_seconds: float,
        resolution_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if threshold_seconds <= 0:
            raise ValueError("threshold_seconds must be positive")
        if resolution_seconds <= 0:
            raise ValueError("resolution_seconds must be positive")
        self._threshold = float(threshold_seconds)
        self._resolution = float(resolution_seconds)
        self._clock = clock
        # Monotonic instant the seat last had input, or None while active.
        self._idle_since: float | None = None

    def mark_idled(self, at: float | None = None) -> None:
        """Record an ``idled`` transition. ``at`` defaults to the clock's now."""
        now = self._clock() if at is None else at
        # The compositor only told us after `resolution` of inactivity, so input
        # actually stopped that long ago -- back-date the idle start.
        self._idle_since = now - self._resolution

    def mark_resumed(self, at: float | None = None) -> None:
        """Record a ``resumed`` transition: any seat input makes us active again."""
        self._idle_since = None

    def idle_seconds(self, now: float | None = None) -> float:
        """Seconds the seat has currently been idle (0.0 while active)."""
        if self._idle_since is None:
            return 0.0
        moment = self._clock() if now is None else now
        return max(0.0, moment - self._idle_since)

    def state_at(self, now: float | None = None) -> ActivityState:
        """Current state: ``IDLE`` once idle time reaches the threshold, else ``ACTIVE``."""
        if self._idle_since is None:
            return ActivityState.ACTIVE
        return (
            ActivityState.IDLE
            if self.idle_seconds(now) >= self._threshold
            else ActivityState.ACTIVE
        )

    @property
    def is_active(self) -> bool:
        return self.state_at() is ActivityState.ACTIVE
