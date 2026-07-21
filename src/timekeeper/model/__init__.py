"""Pure time model: instantaneous observations -> honest, non-overlapping durations.

Hardware-free by design (build-plan Phase 4). See :mod:`timekeeper.model.timeline`.
"""

from __future__ import annotations

from timekeeper.model.timeline import OpenSpan, Span, Timeline

__all__ = ["OpenSpan", "Span", "Timeline"]
