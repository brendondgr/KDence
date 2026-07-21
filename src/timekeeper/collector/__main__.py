"""Step 3.1 (live) -- the merged console line you'd bet money on.

One process, one asyncio loop, two live signals:

- the Wayland idle source drives the pure :class:`ActivityMonitor` (active vs. idle),
  its socket integrated via ``loop.add_reader``;
- the KWin focus source drives the pure :class:`FocusReporter` (which app).

Once per interval it prints the merged line ("app X — active", or "— idle" once you've
been away past the threshold). Watch it while you work in one app, switch apps, then
walk away: the line must track app changes and flip to idle after the threshold. Nothing
is stored yet -- persistence is Phase 4.

Usage:
    uv run python -m timekeeper.collector [--threshold 5] [--interval 2] [--titles]

``--threshold`` defaults short (demo-sized); real use is IDLE_THRESHOLD_SECONDS (300).
"""

from __future__ import annotations

import argparse
import asyncio
import time

from timekeeper.activity.monitor import ActivityMonitor
from timekeeper.activity.wayland_idle import WaylandIdleSource
from timekeeper.collector.merge import merge
from timekeeper.focus.kwin_source import KWinFocusSource
from timekeeper.focus.reporter import FocusReporter


async def _run(args: argparse.Namespace) -> None:
    monitor = ActivityMonitor(
        threshold_seconds=args.threshold,
        resolution_seconds=args.resolution_ms / 1000,
    )
    reporter = FocusReporter(capture_titles=args.titles)

    idle = WaylandIdleSource(
        resolution_ms=args.resolution_ms,
        on_idled=monitor.mark_idled,
        on_resumed=monitor.mark_resumed,
    )
    idle.connect()
    loop = asyncio.get_running_loop()
    loop.add_reader(idle.fileno(), lambda: idle.dispatch())

    focus = KWinFocusSource(on_focus=reporter.update)
    await focus.connect()

    print(
        f"Live merge -- threshold={args.threshold:g}s, interval={args.interval:g}s, "
        f"titles={'on' if args.titles else 'off'}. Ctrl-C to stop."
    )
    try:
        while True:
            await asyncio.sleep(args.interval)
            sample = merge(monitor.state_at(), reporter.current)
            print(f"[{time.strftime('%H:%M:%S')}] {sample.line}")
    finally:
        loop.remove_reader(idle.fileno())
        idle.close()
        await focus.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live merged activity+focus line (Step 3.1)")
    parser.add_argument("--threshold", type=float, default=5.0, help="idle threshold seconds")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between lines")
    parser.add_argument("--resolution-ms", type=int, default=1000, help="idle notify timeout (ms)")
    parser.add_argument("--titles", action="store_true", help="capture window titles (sensitive)")
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
