"""Step 1.2 live check -- wire the Wayland idle source into the pure monitor and
print the current state once per poll interval.

Sit still past the threshold and the line flips to IDLE; press a key and it flips
back to ACTIVE within one poll interval -- and it must flip back using the KEYBOARD
ALONE (the seat-level activity claim).

Usage:
    uv run python -m kdence.activity [--threshold 5] [--resolution-ms 1000]

The threshold defaults to a short value so the flip is observable in seconds. Real
deployments use IDLE_THRESHOLD_SECONDS (300) from .env.
"""

from __future__ import annotations

import argparse
import select

from kdence.activity.monitor import ActivityMonitor, ActivityState
from kdence.activity.wayland_idle import WaylandIdleSource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live active/idle state (Step 1.2)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="seconds of idle before reporting IDLE (default: 5, demo-sized)",
    )
    parser.add_argument(
        "--resolution-ms",
        type=int,
        default=1000,
        help="idle notification timeout handed to the compositor (default: 1000)",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.5,
        help="seconds between printed state lines (default: 0.5)",
    )
    args = parser.parse_args(argv)

    monitor = ActivityMonitor(
        threshold_seconds=args.threshold,
        resolution_seconds=args.resolution_ms / 1000,
    )

    def on_idled() -> None:
        monitor.mark_idled()

    def on_resumed() -> None:
        monitor.mark_resumed()

    print(
        f"Live state -- threshold={args.threshold:g}s, resolution={args.resolution_ms}ms. "
        "Sit still to go IDLE; press a key to return. Ctrl-C to stop."
    )
    last_line = ""
    with WaylandIdleSource(
        resolution_ms=args.resolution_ms, on_idled=on_idled, on_resumed=on_resumed
    ) as source:
        try:
            while True:
                ready, _, _ = select.select([source.fileno()], [], [], args.poll)
                if ready:
                    source.dispatch()
                state = monitor.state_at()
                idle = monitor.idle_seconds()
                marker = "IDLE " if state is ActivityState.IDLE else "ACTIVE"
                line = f"{marker}  idle={idle:5.1f}s"
                if line != last_line:
                    print(line)
                    last_line = line
        except KeyboardInterrupt:
            print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
