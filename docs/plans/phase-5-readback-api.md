# Phase 5 — Read-back API

Implementation plan for the query layer that turns stored spans into the shapes the live
view needs, isolated from the writer. It is the bridge between the datastore (Phase 4) and
the view (Phase 6): every endpoint is shaped to a panel in
[`docs/design-system.md`](../design-system.md).

Read first: `docs/skills/global-project-rules/SKILL.md`, the build plan (Phase 5),
`docs/design-system.md` (the panel → data contract), and the Phase 4 storage/model so the
day rule and reader/writer isolation carry over.

---

## Decisions settled here

- **HTTP stack: stdlib `http.server` (`ThreadingHTTPServer`), not FastAPI.** Confirmed at
  Step 5.1 (the build plan proposed FastAPI+Uvicorn but flagged it for confirmation). The
  read surface is ~4 local GET endpoints returning JSON to a single user on `127.0.0.1`;
  the stdlib server with a thread per request handles concurrent reads with **zero new
  dependencies**, matching the project's stdlib-first pattern (hand-rolled Wayland client,
  stdlib `sqlite3`). No async, no validation framework, no OpenAPI is warranted.
- **Reader/writer isolation via read-only connections.** Each request opens its **own**
  `sqlite3` connection in `mode=ro` (URI) against the WAL database, so reads never block or
  corrupt the collector's single writer, and threads never share a connection.
- **The "current session" comes from the store's open row, not the collector.** While
  active the writer keeps exactly one `open = 1` row, its `end_at` bumped every interval; on
  idle it closes that row. So the reader derives current state from the store alone
  (preserving isolation): an open row ⇒ active in that app with a running session; no open
  row ⇒ idle / daemon not running. Freshness is bounded by the collector interval and
  surfaced as `as_of` so the view can flag staleness.
- **The local-day rule lives here (storage is day-agnostic).** Spans are stored as absolute
  wall-clock `start_at`/`end_at`; this layer computes the local **TODAY / WEEK / MONTH**
  window and **clamps** each span to it, so a span crossing local midnight contributes only
  its in-window part. This is the one place the day definition is applied (Phase 4.1 rule).

## The seam (mirrors the rest of the project)

- **Pure** (`api/queries.py`): given a list of `SpanRow` + a `[start, end)` window + `now`,
  compute `active_seconds`, `per_app_totals`, `timeline`, and `current_state`. Plus
  `range_window(now, range, tz)` computing the local TODAY/WEEK/MONTH bounds. No SQL, no
  HTTP — this is where correctness lives and where the Step 5.2 boundary tests hit.
- **Reader** (`storage/reader.py`): a read-only `SpanReader` (mode=ro) returning `SpanRow`s
  overlapping a window, plus the current open row. Missing DB ⇒ empty (no crash).
- **Server** (`api/server.py` + `__main__.py`): a thin `ThreadingHTTPServer` routing GETs to
  the pure layer, one read-only connection per request, JSON out, `127.0.0.1` only.

## Endpoints (shaped to the design-system panels)

| Endpoint | Backs which panel | Shape |
|---|---|---|
| `GET /api/current` | Current session | `{active, app_class, title, session_seconds, as_of}` |
| `GET /api/summary?range=today\|week\|month` | KPI cards, Per-application totals, Application share | `{range, window, active_seconds, apps:[{app_class, seconds, sessions, share}]}` |
| `GET /api/timeline?range=…` | Active vs. idle over time, Focus timeline | `{range, window, spans:[{app_class, title, start, end, seconds}]}` |
| `GET /api/health` | — (liveness) | `{ok, store, exists}` |

Idle is **excluded** everywhere by construction: idle is the absence of a span. Titles are
served only when the collector captured them (default off); the view is meaningful with the
app class alone.

## Deliverables & tests

| Step | Deliverable | Test / Pass condition |
|---|---|---|
| 5.1 | `api/queries.py` (pure) | `tests/api/test_queries.py`: totals/per-app/timeline/current reconcile with hand-computed values; clamping correct. |
| 5.1 | `storage/reader.py` (read-only) | Exercised via the server tests; missing DB ⇒ empty. |
| 5.1 | `api/server.py` + `__main__.py` | `tests/api/test_server.py`: each endpoint's numbers equal the hand-computed totals for the same window; **concurrency** — hammer a read endpoint while a writer runs, assert no errors / no garbled rows. |
| 5.2 | Boundary handling | `tests/api/test_queries.py`: empty day → zeros, no crash; a single open span → active and counted to `now`; a span across local midnight splits per the day rule. |

All Phase 5 tests are **headless** (localhost HTTP + SQLite; no Wayland), so they carry no
`live` marker and run anywhere.

## Commands

```bash
uv run python -m kdence.api --store /tmp/kdence.db            # serve on 127.0.0.1:8765
curl -s 127.0.0.1:8765/api/summary?range=today | python -m json.tool
uv run pytest tests/api                                       # the Phase 5 suites
```

## Not in scope (deferred)

- Serving the `web/` view and vendored ECharts — that is Phase 6 (the server gains a static
  route then).
- Auth / multi-user — out of scope by project decision (single local user).
