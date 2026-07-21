"""Read-only span reader -- the Phase 5 query path, isolated from the writer.

Each :class:`SpanReader` opens its *own* SQLite connection in ``mode=ro`` against the WAL
database the collector writes. WAL lets any number of these readers run without blocking or
corrupting the single writer, and a per-connection reader means threads never share state.
A missing database is treated as empty (the view should render "no data yet", not crash).

This is deliberately separate from :class:`~kdence.storage.store.Store` (the writer):
the reader can never write, which is the isolation the build plan asks for at Step 5.1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kdence.storage.store import SpanRow


def _row(r: sqlite3.Row) -> SpanRow:
    # ``site`` is a later, additive column; a read-only reader against a not-yet-migrated
    # store simply omits it from the SELECT, so fall back to None when it is absent.
    keys = r.keys()
    return SpanRow(
        id=r["id"],
        app_class=r["app_class"],
        title=r["title"],
        site=r["site"] if "site" in keys else None,
        start_at=r["start_at"],
        end_at=r["end_at"],
        open=bool(r["open"]),
    )


class SpanReader:
    """A read-only view over the span store.

    Args:
        path: the database file the collector writes. If it does not exist, every read
            returns empty -- no error.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._exists = Path(self._path).exists()
        self._conn: sqlite3.Connection | None = None
        # Default to the full column set; narrowed below if the store predates a column.
        self._columns = "id, app_class, title, site, start_at, end_at, open"
        if self._exists:
            # mode=ro: the connection physically cannot write. Reads run against WAL.
            self._conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
            self._conn.row_factory = sqlite3.Row
            self._columns = self._available_columns()

    def _available_columns(self) -> str:
        """The SELECT column list, dropping any additive column this DB has not been migrated
        to yet (a read-only reader cannot ALTER it in)."""
        assert self._conn is not None
        have = {row["name"] for row in self._conn.execute("PRAGMA table_info(spans)")}
        wanted = ("id", "app_class", "title", "site", "start_at", "end_at", "open")
        return ", ".join(c for c in wanted if c in have)

    @property
    def exists(self) -> bool:
        return self._exists

    def all_spans(self) -> list[SpanRow]:
        """Every span, oldest first."""
        if self._conn is None:
            return []
        rows = self._conn.execute(
            f"SELECT {self._columns} FROM spans ORDER BY start_at, id"
        ).fetchall()
        return [_row(r) for r in rows]

    def spans_overlapping(self, start: float, end: float) -> list[SpanRow]:
        """Spans intersecting ``[start, end)``, oldest first.

        A span overlaps when it starts before the window ends and ends after it starts. The
        current open row (``end_at`` bumped to ~now) is included when it overlaps.
        """
        if self._conn is None:
            return []
        rows = self._conn.execute(
            f"SELECT {self._columns} FROM spans WHERE start_at < ? AND end_at > ? ORDER BY start_at, id",
            (end, start),
        ).fetchall()
        return [_row(r) for r in rows]

    def extent(self) -> tuple[float, float, int] | None:
        """``(earliest start_at, latest end_at, span count)`` across all spans, or ``None``.

        The navigable range the UI bounds its date picker to (Phase 9). ``None`` when the
        store is empty or missing -- there is nothing to navigate yet.
        """
        if self._conn is None:
            return None
        r = self._conn.execute(
            "SELECT MIN(start_at) AS lo, MAX(end_at) AS hi, COUNT(*) AS n FROM spans"
        ).fetchone()
        if r is None or r["n"] == 0 or r["lo"] is None:
            return None
        return float(r["lo"]), float(r["hi"]), int(r["n"])

    def latest_end(self) -> float | None:
        """The newest heartbeat (``max(end_at)``) across all spans, or ``None`` if empty."""
        if self._conn is None:
            return None
        r = self._conn.execute("SELECT MAX(end_at) AS m FROM spans").fetchone()
        return None if r["m"] is None else float(r["m"])

    def open_span(self) -> SpanRow | None:
        """The current open span (there is at most one), or ``None``."""
        if self._conn is None:
            return None
        r = self._conn.execute(
            f"SELECT {self._columns} FROM spans WHERE open = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return _row(r) if r is not None else None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> SpanReader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
