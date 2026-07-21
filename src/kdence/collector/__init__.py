"""Collector: merge the live activity and focus signals into one stream.

Phase 3 wires the two hardware sources together behind their pure logic and prints,
once per interval, "app X — active/idle" (build-plan Step 3.1). No persistence yet --
that arrives in Phase 4 under the tested time model.

Public surface:

- :func:`merge` / :class:`MergedSample` -- the pure merge rule (no hardware).
"""

from kdence.collector.merge import MergedSample, merge

__all__ = ["MergedSample", "merge"]
