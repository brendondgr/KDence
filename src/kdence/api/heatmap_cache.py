"""The precomputed heat map: build once per local day, persist, serve from memory.

The per-day slots from :func:`kdence.api.heatmap.daily_slots` only cover **completed** days,
so they change exactly once a day -- when a new day completes. :class:`HeatmapCache` rebuilds
them from the span store at most once per local date, keeps them in memory for requests, and
writes them to ``$XDG_CACHE_HOME/kdence/heatmap.json`` so an API restart does not recompute.

The API process runs :meth:`HeatmapCache.start_refresher`, a daemon thread that checks every
few minutes whether the local date has rolled over and rebuilds if so. A request that arrives
before it has run rebuilds on demand, so a missing, stale, or corrupt cache file never breaks
the panel -- it is derived data and is always safe to delete.

The span store stays read-only here (a ``mode=ro`` :class:`SpanReader`); the only write is the
cache file, atomically, mirroring the config files (binding decisions 8 and 10).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from kdence.api import heatmap
from kdence.storage.reader import SpanReader

log = logging.getLogger(__name__)

CACHE_VERSION = 1

# How often the refresher checks for a date rollover. Cheap (a date comparison) unless it has
# rolled, so a few minutes keeps the post-midnight rebuild prompt, including after a suspend.
DEFAULT_CHECK_SECONDS = 300.0


@dataclass(frozen=True)
class Snapshot:
    """One build of the heat map: the per-day slots and what they cover."""

    built_for: _dt.date  # the local date the build ran on; days before it are complete
    built_at: float
    earliest: _dt.date | None  # first day in the archive (None: empty store)
    days: dict[_dt.date, list[float]]

    @property
    def through(self) -> _dt.date | None:
        """The last completed day covered, or ``None`` if the archive has none yet."""
        last = self.built_for - _dt.timedelta(days=1)
        if self.earliest is None or last < self.earliest:
            return None
        return last


def build(
    store_path: str,
    now: float,
    tz: _dt.tzinfo | None = None,
) -> Snapshot:
    """Rebuild every completed day's slots from the span store (read-only)."""
    today = heatmap.local_date(now, tz)
    until = heatmap.local_midnight(today, tz)
    with SpanReader(store_path) as reader:
        intervals = reader.intervals_before(until)
    earliest = heatmap.local_date(intervals[0][0], tz) if intervals else None
    days = heatmap.daily_slots(intervals, until, tz)
    return Snapshot(built_for=today, built_at=now, earliest=earliest, days=days)


def to_dict(snap: Snapshot) -> dict:
    return {
        "version": CACHE_VERSION,
        "built_for": snap.built_for.isoformat(),
        "built_at": snap.built_at,
        "earliest": snap.earliest.isoformat() if snap.earliest else None,
        "days": {d.isoformat(): [round(s, 1) for s in slots] for d, slots in snap.days.items()},
    }


def from_dict(payload: dict) -> Snapshot:
    """Parse a cache file; raises ``ValueError`` on anything unexpected (-> rebuild)."""
    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        raise ValueError("unsupported heat map cache version")
    try:
        days: dict[_dt.date, list[float]] = {}
        for key, slots in payload["days"].items():
            if len(slots) != heatmap.SLOTS_PER_DAY:
                raise ValueError(f"day {key} has {len(slots)} slots")
            days[_dt.date.fromisoformat(key)] = [float(s) for s in slots]
        earliest = payload["earliest"]
        return Snapshot(
            built_for=_dt.date.fromisoformat(payload["built_for"]),
            built_at=float(payload["built_at"]),
            earliest=_dt.date.fromisoformat(earliest) if earliest else None,
            days=days,
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"malformed heat map cache: {exc!r}") from exc


def save(path: str | Path, snap: Snapshot) -> None:
    """Atomically write the snapshot (temp file + ``os.replace``)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".heatmap-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(to_dict(snap), fh, separators=(",", ":"))
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load(path: str | Path) -> Snapshot | None:
    """Read the cache file; ``None`` if it is missing or unreadable (the caller rebuilds)."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return from_dict(json.loads(p.read_text()))
    except (ValueError, OSError):
        return None


class HeatmapCache:
    """The API's in-memory heat map, rebuilt at most once per local date.

    Thread-safe: request threads and the refresher share one lock, so a rollover rebuilds once
    even if several requests race it.
    """

    def __init__(
        self,
        store_path: str,
        cache_path: str | Path,
        now: Callable[[], float] = time.time,
        tz: _dt.tzinfo | None = None,
    ) -> None:
        self._store_path = store_path
        self._cache_path = Path(cache_path)
        self._now = now
        self._tz = tz
        self._lock = threading.Lock()
        self._snap: Snapshot | None = None
        self._loaded = False
        self._stop = threading.Event()

    def current(self) -> Snapshot:
        """The snapshot for today's date, rebuilding (and persisting) it first if stale."""
        with self._lock:
            now = self._now()
            today = heatmap.local_date(now, self._tz)
            if not self._loaded:
                self._snap = load(self._cache_path)
                self._loaded = True
            if self._snap is None or self._snap.built_for != today:
                self._snap = build(self._store_path, now, self._tz)
                try:
                    save(self._cache_path, self._snap)
                except OSError as exc:  # still serve from memory; retry persisting tomorrow
                    log.warning("could not write heat map cache %s: %s", self._cache_path, exc)
            return self._snap

    def window(self, preset: str) -> tuple[Snapshot, heatmap.HeatmapWindow]:
        """Aggregate a preset window (``7``/``30``/``90``/``365``/``all``) from the snapshot."""
        snap = self.current()
        rng = heatmap.resolve_range(preset, snap.earliest, snap.through)
        first, last = rng if rng is not None else (None, None)
        return snap, heatmap.aggregate(snap.days, first, last)

    def start_refresher(self, check_every: float = DEFAULT_CHECK_SECONDS) -> threading.Thread:
        """Run the daily rebuild in a daemon thread: once now, then on each date rollover."""

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.current()
                except Exception:  # never let one failed build end the refresher
                    log.exception("heat map rebuild failed")
                self._stop.wait(check_every)

        thread = threading.Thread(target=loop, name="heatmap-refresher", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()
