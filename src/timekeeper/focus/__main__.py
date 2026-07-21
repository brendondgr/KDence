"""Step 2.3 live check -- print the focused window, updating on every change.

Wires the KWin focus source into the pure reporter and prints each focus change as it
happens (so you can watch latency). Switch between a few apps and confirm the line
tracks them; click the desktop to see "(no window)".

Usage:
    uv run python -m timekeeper.focus [--titles] [--poll 1.0]

``--titles`` opts into capturing window captions (off by default -- titles leak
document names and URLs).
"""

from __future__ import annotations

import argparse
import asyncio

from timekeeper.focus.kwin_source import KWinFocusSource
from timekeeper.focus.reporter import FocusReporter


async def _run(args: argparse.Namespace) -> None:
    def on_change(identity: object) -> None:
        print(f"focus -> {identity.label}")  # type: ignore[attr-defined]

    reporter = FocusReporter(capture_titles=args.titles, on_change=on_change)
    source = KWinFocusSource(on_focus=reporter.update)
    await source.connect()
    print(
        f"Live focus -- titles={'on' if args.titles else 'off'}. "
        "Switch apps to see it track; Ctrl-C to stop."
    )
    try:
        while True:
            await asyncio.sleep(args.poll)
    finally:
        await source.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live focused-window reporter (Step 2.3)")
    parser.add_argument(
        "--titles",
        action="store_true",
        help="capture window titles too (default off; titles are sensitive)",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=1.0,
        help="seconds between idle wakeups of the event loop (default: 1.0)",
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
