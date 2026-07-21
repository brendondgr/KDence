"""Step 1.1 -- the five-minute idle experiment.

Run this on a live KDE Plasma 6 / Wayland session and it logs every ``idled`` /
``resumed`` transition from the compositor plus a running idle-seconds counter (timed
with our own monotonic clock, since there is no idle counter to read on Wayland).

Do the three sub-experiments the build plan calls for and read the answers off the log:

  (a) sit still ~30 s        -> expect one `idled`, then a rising idle counter.
  (b) touch ONLY the keyboard -> expect `resumed` (the critical case: proves activity
                                  is one seat-level signal, not two input streams).
  (c) move ONLY the mouse     -> expect `resumed`.

Usage:
    uv run python -m timekeeper.activity.experiment [--timeout-ms 1000] [--duration 0]

``--duration 0`` (default) runs until Ctrl-C.
"""

from __future__ import annotations

import argparse
import select
import time

from timekeeper.activity.wayland_idle import WaylandIdleSource


def _fmt(elapsed: float) -> str:
    return f"[t+{elapsed:6.1f}s]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wayland idle-signal experiment (Step 1.1)")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=1000,
        help="idle notification timeout handed to the compositor (default: 1000)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="seconds to run; 0 = until Ctrl-C (default: 0)",
    )
    args = parser.parse_args(argv)

    start = time.monotonic()
    state = {"idle_since": None}  # monotonic instant of last `idled`, or None

    def on_idled() -> None:
        state["idle_since"] = time.monotonic()
        print(f"{_fmt(time.monotonic() - start)} IDLED   (no seat input for ~{args.timeout_ms} ms)")

    def on_resumed() -> None:
        was = state["idle_since"]
        state["idle_since"] = None
        detail = ""
        if was is not None:
            detail = f" after ~{time.monotonic() - was + args.timeout_ms / 1000:.1f}s idle"
        print(f"{_fmt(time.monotonic() - start)} RESUMED{detail}  <- input detected")

    print("=" * 72)
    print("Idle experiment. Try, in order:")
    print("  (a) sit still ~30s   (b) keyboard ONLY   (c) mouse ONLY")
    print(f"notification timeout = {args.timeout_ms} ms; press Ctrl-C to stop.")
    print("=" * 72)

    with WaylandIdleSource(
        resolution_ms=args.timeout_ms, on_idled=on_idled, on_resumed=on_resumed
    ) as source:
        deadline = None if args.duration <= 0 else start + args.duration
        last_tick = 0.0
        try:
            while deadline is None or time.monotonic() < deadline:
                ready, _, _ = select.select([source.fileno()], [], [], 0.5)
                if ready:
                    source.dispatch()
                now = time.monotonic()
                if state["idle_since"] is not None and now - last_tick >= 1.0:
                    idle_for = now - state["idle_since"] + args.timeout_ms / 1000
                    print(f"{_fmt(now - start)}   ...idle for ~{idle_for:5.1f}s")
                    last_tick = now
        except KeyboardInterrupt:
            print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
