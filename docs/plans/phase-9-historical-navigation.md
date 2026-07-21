# Historical Navigation — Plan (added scope, "Phase 9")

## 1. Introduction

The original 8-phase build plan captures activity **durably and forever** — the SQLite store
keeps every active span (app class, optional title, absolute wall-clock start/end) and never
prunes — but the *read* side only computes **today / this week / this month relative to
`now`**. There is no way to jump to an arbitrary date, scrub back through months or years, or
set a custom range. This plan adds that historical-navigation layer, which is the whole point
of using Apache ECharts: scrubbing rich detail across arbitrary windows.

The approach: (1) make the store live at a **persistent** path so data survives reboots
(today's `/tmp` default is RAM-backed `tmpfs` on this machine and is wiped on reboot — an
urgent fix), (2) generalize the pure query window to any **anchored period or custom range**,
(3) expose **date-aware endpoints**, a **data-extent** endpoint, and a bounded **server-side
bucket** endpoint for long ranges, and (4) give the dashboard a **period selector, prev/next
navigation, and date/month/year/custom pickers**. Pure logic stays separable and unit-tested;
each step keeps the build plan's Review + Test + Pass rhythm and ends in a commit (no push).

## 2. Gaps & Unanswered Questions

- **Retention policy.** *Assumption*: keep everything forever (the user's stated goal —
  understand months/years). No pruning or rollup-and-delete.
- **Coarse aggregation for long ranges.** *Assumption*: auto-select bucket granularity by
  window length — hourly for ≤ ~2 days, daily for ≤ ~3 months, weekly for ≤ ~2 years,
  monthly beyond — overridable via a `granularity` param. Keeps chart payloads bounded and
  readable. Tunable.
- **Custom-range input format.** *Assumption*: `YYYY-MM-DD` local dates; the server converts
  to local-midnight `[start, end)` bounds. `anchor`/`date` selects the period *containing*
  that date.
- **Timezone / DST over long history.** *Assumption*: interpret windows in the machine's
  current local zone at query time; the small DST-boundary skew is a recorded known limit
  (as in Phase 4.1), acceptable for a personal tracker.
- **Preserving the existing `/tmp/kdence.db` data.** The current collector writes to `/tmp`,
  which will be lost on reboot. *Human intervention is needed*: decide whether to copy the
  current `/tmp/kdence.db` to the new persistent path, or treat it as disposable demo data. (It
  can be copied with a single `cp` before the next reboot if you want to keep it.)
- **Where the persistent default lives.** *Assumption*: `$XDG_DATA_HOME/kdence/kdence.db`
  (fallback `~/.local/share/kdence/kdence.db`). This also becomes the path the Phase 7
  systemd user unit points at.

## 3. Hierarchical Step-by-Step Instructions

### Step 1 — Persistent store location (data must survive reboots)
- **Locations**: new `src/kdence/storage/paths.py` (`default_store_path()` →
  `$XDG_DATA_HOME/kdence/kdence.db`, creating the parent dir); `src/kdence/collector/__main__.py`
  and `src/kdence/api/__main__.py` (make `--store` **default** to `default_store_path()`
  instead of `/tmp`/required); `tests/storage/test_paths.py`.
- **Rationale**: `/tmp` is `tmpfs` (RAM) here, so a months/years archive cannot live there —
  it is erased on reboot. A persistent XDG default is the enabling change for the entire goal
  and the path Phase 7's service will use.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit (no push): `Historical Navigation (1/5) Complete: persistent XDG store path, default for collector + API`.

### Step 2 — Generalize the query window (pure logic)
- **Locations**: `src/kdence/api/queries.py` — extend `range_window(now, range, tz,
  anchor=None)` to build the period **containing `anchor`** (not `now`); add `"day"` and
  `"year"` to `RANGES`; add `custom_window(start, end)`; add a pure `bucket_series(spans,
  window, granularity)` returning per-bucket active seconds + per-app breakdown.
  `tests/api/test_queries.py`.
- **Rationale**: A window anchored on a chosen date is what unlocks reaching March or last
  year; a custom window unlocks report ranges; `bucket_series` is the bounded aggregation the
  charts use across long spans. All pure, so correctness is proven without HTTP.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit (no push): `Historical Navigation (2/5) Complete: anchored/custom windows + pure bucket_series`.

### Step 3 — Date-aware endpoints, data extent, and bucket endpoint (server)
- **Locations**: `src/kdence/api/server.py` — `/api/summary` & `/api/timeline` accept
  `date`/`anchor`/`start`/`end`; new `/api/extent` (earliest/latest span + days tracked) via
  new `SpanReader.extent()` in `src/kdence/storage/reader.py`; new
  `/api/buckets?start=&end=&granularity=` calling `bucket_series`. `tests/api/test_server.py`.
- **Rationale**: The UI must know the navigable range (extent) to bound its picker and disable
  stepping past the data; long ranges need bounded, pre-bucketed series rather than shipping
  every raw span. Raw-span detail stays available via `timeline` for day views.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit (no push): `Historical Navigation (3/5) Complete: date-aware endpoints + /api/extent + /api/buckets`.

### Step 4 — Dashboard navigation (view)
- **Locations**: `src/kdence/web/static/index.html` (Day/Week/Month/Year/Custom selector,
  ◀ ▶ step arrows, `type=date`/month/year + custom start–end pickers, a "Today" button, a
  concrete period label); `styles.css` (controls); `app.js` (state gains
  `{granularity, anchor, customStart/End}`; fetches use the date params and `/api/buckets`;
  ECharts renders the returned buckets; "next" disabled at the latest data; picker bounds
  come from `/api/extent`).
- **Rationale**: This is the actual "switch, swap, change the dates" capability, and where
  ECharts earns its place — scrubbing arbitrary historical windows.
- **Action**: Undergo the verification/tests/validation process for this phase (headless
  endpoint tests + an in-session browser check against a seeded multi-month store; the
  interactive scrub is a manual/live check). Once validated, commit (no push):
  `Historical Navigation (4/5) Complete: period selector + date navigation in the live view`.

### Step 5 — Regression, docs, and honesty note
- **Locations**: `docs/plans/activity-tracker-build-plan.md`, `docs/design-system.md`
  (range → full date navigation), `docs/structure.md`, `docs/documentation.md`,
  `docs/workflow.md`, `docs/checklist.md`. Re-run the full headless suite + lint.
- **Rationale**: keep docs the source of truth and record the decisions (persistent path,
  anchored/custom windows, server buckets, auto-granularity).
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit (no push): `Historical Navigation (5/5) Complete: regression + docs for date navigation`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Persistent store path | XDG default so data survives reboots; collector + API default to it | `src/kdence/storage/paths.py`, `collector/__main__.py`, `api/__main__.py` |
| Path unit tests | Honors `XDG_DATA_HOME`, creates the dir, correct filename | `tests/storage/test_paths.py` |
| Anchored/custom windows + buckets | `range_window(anchor=…)`, `day`/`year`, `custom_window`, `bucket_series` (pure) | `src/kdence/api/queries.py` |
| Query unit tests | Anchored past periods, `day`/`year` bounds, custom clamp, bucket reconciliation | `tests/api/test_queries.py` |
| Date-aware endpoints | `date`/`anchor`/`start`/`end` params; `/api/extent`; `/api/buckets` | `src/kdence/api/server.py`, `src/kdence/storage/reader.py` |
| Server tests | Extent + buckets reconcile with the raw store; date selects the right period | `tests/api/test_server.py` |
| Dashboard navigation | Period selector, prev/next, date/month/year/custom pickers, bounded by extent | `src/kdence/web/static/{index.html,styles.css,app.js}` |
| Docs update | Build plan Phase 9 section, design-system range, structure/documentation/workflow/checklist | `docs/…` |
