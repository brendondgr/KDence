"""Step 3.1 (live) -- the merged console line you'd bet money on.

One process, one asyncio loop, two live signals:

- the Wayland idle source drives the pure :class:`ActivityMonitor` (active vs. idle),
  its socket integrated via ``loop.add_reader``;
- the KWin focus source drives the pure :class:`FocusReporter` (which app).

Once per interval it prints the merged line ("app X — active", or "— idle" once you've
been away past the threshold). Watch it while you work in one app, switch apps, then
walk away: the line must track app changes and flip to idle after the threshold.

With ``--store PATH`` (Phase 4) it also persists spans through the pure time model into a
single-writer SQLite store: each interval feeds a wall-clock ``active`` heartbeat, and on
idle the active span is closed at the *back-dated last-input* instant (not detection), so
the trailing idle window is never counted. Dump the result with
``python -m timekeeper.storage PATH``. Without ``--store`` it is print-only (Phase 3).

Usage:
    uv run python -m timekeeper.collector [--threshold 5] [--interval 2] [--titles]
                                          [--store PATH]

``--threshold`` defaults short (demo-sized); real use is IDLE_THRESHOLD_SECONDS (300).
"""

from __future__ import annotations

import argparse
import asyncio
import time

from timekeeper.activity.monitor import ActivityMonitor, ActivityState
from timekeeper.activity.wayland_idle import WaylandIdleSource
from timekeeper.collector.merge import merge
from timekeeper.focus.kwin_source import KWinFocusSource
from timekeeper.focus.reporter import FocusReporter
from timekeeper.model.timeline import Timeline
from timekeeper.storage.paths import default_store_path
from timekeeper.storage.store import Store


async def _run(args: argparse.Namespace) -> None:
    monitor = ActivityMonitor(
        threshold_seconds=args.threshold,
        resolution_seconds=args.resolution_ms / 1000,
    )
    reporter = FocusReporter(capture_titles=args.titles)

    store: Store | None = None
    timeline: Timeline | None = None
    store_path = _resolve_store(args)
    if store_path is not None:
        store = Store(store_path)
        # A heartbeat gap larger than this means a suspend/stall, not activity.
        timeline = store.bind(max_gap_seconds=max(args.interval * 3, 5.0))

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

    where = f", store={store_path}" if store_path is not None else " (print-only)"
    print(
        f"Live merge -- threshold={args.threshold:g}s, interval={args.interval:g}s, "
        f"titles={'on' if args.titles else 'off'}{where}. Ctrl-C to stop."
    )
    try:
        while True:
            await asyncio.sleep(args.interval)
            state = monitor.state_at()
            sample = merge(state, reporter.current)
            print(f"[{time.strftime('%H:%M:%S')}] {sample.line}")
            if timeline is not None:
                now = time.time()
                if state is ActivityState.ACTIVE:
                    timeline.active(now, sample.app_class, sample.title)
                else:
                    # Close the active span at the real last-input instant (back-dated),
                    # in wall-clock terms -- the honesty rule from Phase 4.1.
                    timeline.idle(now - monitor.idle_seconds())
    finally:
        loop.remove_reader(idle.fileno())
        idle.close()
        await focus.close()
        if timeline is not None:
            timeline.stop(time.time())  # clean shutdown finalizes the open span
        if store is not None:
            store.close()


def _resolve_store(args: argparse.Namespace) -> str | None:
    """Where to persist, if anywhere. ``--no-store`` -> print-only (the Phase 3 demo mode);
    an explicit ``--store`` wins; otherwise the durable XDG default (Phase 9)."""
    if args.no_store:
        return None
    if args.store:
        return args.store
    return str(default_store_path())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live merged activity+focus line (Steps 3.1 / 4.3)"
    )
    parser.add_argument("--threshold", type=float, default=5.0, help="idle threshold seconds")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between lines")
    parser.add_argument("--resolution-ms", type=int, default=1000, help="idle notify timeout (ms)")
    parser.add_argument("--titles", action="store_true", help="capture window titles (sensitive)")
    parser.add_argument(
        "--store",
        metavar="PATH",
        help="persist spans to this SQLite file (default: the durable XDG store path)",
    )
    parser.add_argument(
        "--no-store", action="store_true", help="print-only, do not persist (Phase 3 demo mode)"
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
