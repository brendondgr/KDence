"""Single-writer SQLite datastore under the tested time model (build-plan Step 4.3).

The store carries *no* time logic -- that all lives in :class:`~kdence.model.timeline.Timeline`
and is proven hardware-free in ``tests/model``. The store's only job is to persist what the
model emits, one SQLite write per model event, and to enforce the two disciplines the build
plan calls out:

- **Single writer.** One connection, WAL mode, so Phase 5 read-back never blocks or
  corrupts the writer. At most one row is ever ``open = 1``.
- **Open span on crash.** The open span's ``end_at`` is bumped to the latest heartbeat on
  every ``on_extend``. If the process dies without a clean close, the next :func:`Store`
  startup finalizes any still-open row **at its stored ``end_at``** (its last heartbeat) --
  never extended to restart time. That is :meth:`recover_open_spans`, run in ``__init__``.

Wire it to a :class:`Timeline` with :meth:`bind`, which returns a ready timeline whose
callbacks write through this store. ``sqlite3`` is stdlib -- no new dependency.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kdence.model.timeline import OpenSpan, Span, Timeline

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    id            INTEGER PRIMARY KEY,
    app_class     TEXT,
    title         TEXT,
    site          TEXT,
    detail        TEXT,
    detail_source TEXT,
    start_at      REAL NOT NULL,
    end_at        REAL NOT NULL,
    open          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_spans_start ON spans (start_at);
CREATE INDEX IF NOT EXISTS idx_spans_open ON spans (open);
"""

# Columns added after the original schema shipped, applied to pre-existing databases so a
# months-old store keeps its history. Additive only (new nullable columns) -- never destructive.
# ``site`` was the first (browser-only) sub-dimension; ``detail``/``detail_source`` generalise it
# to any in-app detail (site | caption | mpris). Legacy ``site`` rows are coalesced on read.
_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("site", "ALTER TABLE spans ADD COLUMN site TEXT"),
    ("detail", "ALTER TABLE spans ADD COLUMN detail TEXT"),
    ("detail_source", "ALTER TABLE spans ADD COLUMN detail_source TEXT"),
)


@dataclass(frozen=True)
class SpanRow:
    """A persisted span as read back from the store.

    ``site`` is the **legacy** browser-only column (populated for rows written before the
    generic ``detail`` sub-dimension landed). New rows write ``detail`` + ``detail_source``
    instead. The ``effective_*`` properties coalesce the two so every consumer sees one thing
    regardless of when the row was written -- old browser rows surface as ``detail_source="site"``.
    """

    id: int
    app_class: str | None
    title: str | None
    start_at: float
    end_at: float
    open: bool
    site: str | None = None  # legacy browser-only sub-identity; coalesced via effective_*
    detail: str | None = None  # generic in-app sub-identity (site/document/track)
    detail_source: str | None = None  # provider that produced ``detail``: site|caption|mpris

    @property
    def duration(self) -> float:
        return max(0.0, self.end_at - self.start_at)

    @property
    def effective_detail(self) -> str | None:
        """The in-app detail value, coalescing a legacy ``site`` row into the generic field."""
        return self.detail if self.detail is not None else self.site

    @property
    def effective_source(self) -> str | None:
        """The detail provider: the stored ``detail_source``, or ``"site"`` for a legacy row."""
        if self.detail_source is not None:
            return self.detail_source
        return "site" if self.site is not None else None

    @property
    def effective_site(self) -> str | None:
        """The browser host for this row, or ``None`` if its detail is not a site.

        Browsers (legacy ``site`` rows and new ``detail_source="site"`` rows) surface their
        host here; caption/mpris rows return ``None``, so the site-only drill-down and the
        site-category rollup ignore them.
        """
        return self.effective_detail if self.effective_source == "site" else None


class Store:
    """A single-writer SQLite span store.

    Args:
        path: database file path, or ``":memory:"`` for an ephemeral test store.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        # check_same_thread stays True: single-writer, one owning thread by design.
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        # WAL lets Phase 5 readers run without blocking this writer. Memory DBs reject it
        # harmlessly; ignore the failure there.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()
        # Row id of the current open span, if any (mirrors the single open=1 row).
        self._open_id: int | None = None
        self.recover_open_spans()

    def _migrate(self) -> None:
        """Apply additive column migrations to a pre-existing store (idempotent).

        ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so a database written
        by an older version is upgraded here -- each missing column added as a nullable field
        so historical rows read back with ``NULL`` and nothing is lost.
        """
        have = {row["name"] for row in self._conn.execute("PRAGMA table_info(spans)")}
        for column, ddl in _MIGRATIONS:
            if column not in have:
                self._conn.execute(ddl)

    # -- lifecycle -------------------------------------------------------------

    def recover_open_spans(self) -> int:
        """Finalize any span left ``open`` by a crashed prior run.

        Closes each at its stored ``end_at`` (its last heartbeat) -- the "no invented
        hours" rule. Returns how many rows were recovered. Runs automatically at startup.
        """
        cur = self._conn.execute("UPDATE spans SET open = 0 WHERE open = 1")
        self._conn.commit()
        self._open_id = None
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- model wiring (the writer path) ---------------------------------------

    def bind(self, *, max_gap_seconds: float) -> Timeline:
        """Return a :class:`Timeline` whose spans persist through this store."""
        return Timeline(
            max_gap_seconds=max_gap_seconds,
            on_open=self._on_open,
            on_extend=self._on_extend,
            on_close=self._on_close,
        )

    def _on_open(self, span: OpenSpan) -> None:
        cur = self._conn.execute(
            "INSERT INTO spans (app_class, title, detail, detail_source, start_at, end_at, open) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (span.app_class, span.title, span.detail, span.detail_source, span.start, span.end),
        )
        self._open_id = cur.lastrowid
        self._conn.commit()

    def _on_extend(self, span: OpenSpan) -> None:
        if self._open_id is None:
            return
        self._conn.execute(
            "UPDATE spans SET end_at = ? WHERE id = ?",
            (span.end, self._open_id),
        )
        self._conn.commit()

    def _on_close(self, span: Span) -> None:
        if self._open_id is None:
            return
        self._conn.execute(
            "UPDATE spans SET end_at = ?, open = 0 WHERE id = ?",
            (span.end, self._open_id),
        )
        self._open_id = None
        self._conn.commit()

    # -- reads (verification here; the real query layer is Phase 5) ------------

    def read_spans(self) -> list[SpanRow]:
        """All spans, oldest first."""
        rows = self._conn.execute(
            "SELECT id, app_class, title, site, detail, detail_source, start_at, end_at, open "
            "FROM spans ORDER BY start_at, id"
        ).fetchall()
        return [
            SpanRow(
                id=r["id"],
                app_class=r["app_class"],
                title=r["title"],
                site=r["site"],
                detail=r["detail"],
                detail_source=r["detail_source"],
                start_at=r["start_at"],
                end_at=r["end_at"],
                open=bool(r["open"]),
            )
            for r in rows
        ]

    def total_active_seconds(self) -> float:
        """Sum of every stored span's duration (idle is simply absent)."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(end_at - start_at), 0.0) AS s FROM spans"
        ).fetchone()
        return float(row["s"])
