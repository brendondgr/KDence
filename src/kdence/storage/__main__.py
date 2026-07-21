"""Dump a KDence span store -- the Step 4.3 verification helper.

Read-only. After running the collector with ``--store PATH`` for a while, run this to see
the stored spans and confirm they match what you actually did. The real query layer (today's
per-app totals, timelines) is Phase 5; this is just enough to eyeball the raw data.

Usage:
    uv run python -m kdence.storage PATH        # list spans + total
"""

from __future__ import annotations

import argparse
import time

from kdence.storage.store import Store


def _fmt_clock(unix_seconds: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(unix_seconds))


def _fmt_dur(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump a KDence span store (Step 4.3 check)")
    parser.add_argument("path", help="path to the SQLite store written by the collector")
    args = parser.parse_args(argv)

    with Store(args.path) as store:
        rows = store.read_spans()
        total = store.total_active_seconds()

    if not rows:
        print(f"{args.path}: no spans recorded yet.")
        return 0

    print(f"{args.path}: {len(rows)} span(s), {_fmt_dur(total)} active total\n")
    print(f"{'start':<19}  {'end':<19}  {'dur':>9}  app")
    for r in rows:
        flag = " (open)" if r.open else ""
        app = r.app_class or "(desktop)"
        if r.title:
            app = f"{app} — {r.title}"
        print(
            f"{_fmt_clock(r.start_at):<19}  {_fmt_clock(r.end_at):<19}  {_fmt_dur(r.duration):>9}  {app}{flag}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
