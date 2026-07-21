"""Pure time model: instantaneous observations -> honest, non-overlapping durations.

Hardware-free by design (build-plan Phase 4). See :mod:`kdence.model.timeline`.
"""

from __future__ import annotations

from kdence.model.timeline import OpenSpan, Span, Timeline

__all__ = ["OpenSpan", "Span", "Timeline"]
