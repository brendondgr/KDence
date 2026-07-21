# Phase 4 — Time model and storage

Implementation plan and the **Step 4.1 written design** for turning instantaneous
observations into honest durations, then persisting them. This is the phase the build plan
singles out: *"the pure-logic tests in Step 4.2 are where correctness actually lives."* No
hardware is involved — the model runs on fake timestamps and the store on a temp file.

Read first: `docs/skills/global-project-rules/SKILL.md`, `docs/plans/activity-tracker-build-plan.md`
(Phase 4), and the existing seam in `src/timekeeper/activity/monitor.py` (which already
back-dates the idle start — the model trusts that back-dated instant).

---

## Step 4.1 — The model on paper (design decisions)

### Chosen model: stitched heartbeats with a max-gap cap

Two options were on the table (build plan 4.1): **stitched heartbeats** vs. **open/close
intervals**. We use **stitched heartbeats**, because it makes both honesty rules fall out
naturally and it needs no separate "the app closed" event from the compositor:

- The collector emits one **active heartbeat** per interval carrying `(at, app_class, title)`,
  where `at` is **wall-clock** Unix seconds (`time.time()`), not monotonic — days and
  suspend gaps only make sense on the wall clock.
- Consecutive heartbeats for the **same** window whose gap is `≤ max_gap` **extend** one
  span: `span.end = at`. Active time therefore accrues as the sum of believable
  heartbeat-to-heartbeat gaps.
- A heartbeat for a **different** window **closes** the current span at `at` and **opens** a
  new one starting at `at` — spans are contiguous and non-overlapping by construction.

### The four rules the build plan demands a written answer for

1. **End boundary (active → idle) — the back-dating case.** When the user walks away, the
   active span ends at **last input**, not at detection. The `ActivityMonitor` already
   back-dates the idle start by the idle source's resolution (`idle_since = now − resolution`).
   The collector passes **that** instant to `Timeline.idle(at)`, and the model closes the
   open span at exactly `at`. **The trailing idle window is never counted as active.** This
   is the one people get wrong, so it is Step 4.2 case (b).

2. **Day definition.** A "day" is the **local calendar day** (local midnight to local
   midnight). Storage is deliberately **day-agnostic**: it stores raw spans with absolute
   wall-clock `start_at`/`end_at` (Unix seconds). Spans that cross local midnight are
   **split at query time** by the Phase 5 read-back API, not at write time — so the stored
   record stays a faithful, un-chopped log and the day rule lives in exactly one place.

3. **Suspend gap.** During suspend the idle-notify protocol is silent and heartbeats simply
   stop, so a suspend shows up as a **large gap between heartbeats**. Any gap `> max_gap`
   is treated as a break, not activity: the open span is closed at its **last** in-window
   heartbeat and a fresh span starts at the next heartbeat. The suspended hours never become
   phantom active time. `max_gap` defaults to a small multiple of the heartbeat interval
   (the collector passes `3 × interval`, floored at a few seconds).

4. **Open span on process death.** There is no clean `stop()` on a crash. The store keeps
   the open span's `end_at` **bumped to the latest heartbeat** on every interval and flagged
   `open = 1`. On the next startup the store **finalizes any still-open span at its stored
   `end_at`** (its last heartbeat) and clears the flag — it is **never** extended to restart
   time. No invented hours. This is Step 4.3's crash assertion.

### Known limitations (recorded, not fixed here)

- Wall-clock timestamps can jump on NTP correction; a backwards jump could momentarily
  shrink a span. Acceptable for a personal tracker; noted for the honesty review (Step 8.3).
- Idle periods are **not stored at all** — idle is the absence of a span. The store holds
  only active spans, which keeps it small and makes "total active" a plain sum.

---

## Deliverables

| Step | Deliverable | Kind | Test / Pass condition |
|---|---|---|---|
| 4.1 | This written design (model choice + the four rules) | Doc | Rules stated for end-boundary, day, suspend, crash. |
| 4.2 | `model/timeline.py` — pure `Span` / `OpenSpan` / `Timeline` | Pure | `tests/model/test_timeline.py`: cases (a)–(d) assert durations. **The** critical suite. |
| 4.3 | `storage/store.py` — single-writer SQLite under the model | Storage | `tests/storage/test_store.py`: spans match; crash rule fires (no invented time). |
| 4.3 | `collector --store PATH` + `python -m timekeeper.storage` dump | Wiring | Live check: run the collector a few minutes, dump, spans match what you saw. |
| 4.4 | Regression checkpoint | — | Phases 1–3 suites + 4.2 all green. |

## The seam (mirrors Phases 1–2)

- **Pure** (`model/`): `Timeline` consumes `active(at, app, title)` / `idle(at)` / `stop(at)`
  events with injected timestamps and produces `Span`s. Zero hardware, zero SQL.
- **Storage** (`storage/`): `Store` subscribes to the `Timeline`'s `on_open` / `on_extend`
  / `on_close` callbacks and maps each to one SQLite write (INSERT open row / UPDATE end /
  finalize). Single writer, WAL mode so Phase 5 readers never block it.
- **Collector**: unchanged live sources feed the `Timeline`; `--store` plugs a `Store` in
  behind it. Print-only (Phase 3) stays the default.

## Storage schema

```sql
CREATE TABLE spans (
    id        INTEGER PRIMARY KEY,
    app_class TEXT,              -- NULL on the bare desktop (active but appless)
    title     TEXT,              -- NULL unless titles were captured (privacy: default off)
    start_at  REAL NOT NULL,     -- Unix seconds (wall clock)
    end_at    REAL NOT NULL,     -- Unix seconds; == last heartbeat while open
    open      INTEGER NOT NULL   -- 1 while current, 0 once finalized
);
```

`sqlite3` is **stdlib** — no new runtime dependency. WAL is enabled for reader/writer
isolation. At most one row may have `open = 1` at any time.

## Manual / live checks (handed off — need a human)

- Run `uv run python -m timekeeper.collector --store /tmp/tk.db` for a few minutes across a
  couple of apps, then `uv run python -m timekeeper.storage /tmp/tk.db` and confirm the
  spans match what you did. Kill it mid-span and re-run the dump: the last span is closed at
  its last heartbeat (no gap-hour invented).
