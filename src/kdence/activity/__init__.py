"""Activity detection: active-vs-idle from the Wayland seat idle signal.

Public surface:

- :class:`ActivityMonitor` / :class:`ActivityState` -- pure decision logic (no hardware).
- :class:`WaylandIdleSource` -- ``ext_idle_notifier_v1`` client (the hardware side).

See docs/plans/phase-1-activity-detection.md for the design and the pure/hardware seam.
"""

from kdence.activity.monitor import ActivityMonitor, ActivityState
from kdence.activity.wayland_idle import WaylandIdleSource, WaylandProtocolError

__all__ = [
    "ActivityMonitor",
    "ActivityState",
    "WaylandIdleSource",
    "WaylandProtocolError",
]
