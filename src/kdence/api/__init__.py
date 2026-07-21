"""Read-back query layer (build-plan Phase 5).

Pure aggregates in :mod:`kdence.api.queries`; a thin stdlib HTTP surface in
:mod:`kdence.api.server`. Reads are isolated from the collector's writer via read-only
connections (:class:`kdence.storage.reader.SpanReader`).
"""

from __future__ import annotations

from kdence.api.queries import (
    AppTotal,
    CurrentState,
    TimelineSpan,
    Window,
    active_seconds,
    current_state,
    per_app_totals,
    range_window,
    timeline,
)
from kdence.api.server import ReadBackServer, serve

__all__ = [
    "AppTotal",
    "CurrentState",
    "ReadBackServer",
    "TimelineSpan",
    "Window",
    "active_seconds",
    "current_state",
    "per_app_totals",
    "range_window",
    "serve",
    "timeline",
]
