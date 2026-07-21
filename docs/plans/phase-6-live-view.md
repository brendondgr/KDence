# Phase 6 — Live view

Implementation plan for the minimal live surface: a dark-terminal dashboard that shows the
current app, active/idle, and today's totals updating, built against
[`docs/design-system.md`](../design-system.md) and served by the Phase 5 read-back API.

Read first: `docs/skills/global-project-rules/SKILL.md`, the build plan (Phase 6),
`docs/design-system.md` (tokens + panel/data contract), and the comp under
`docs/references/frontend/` (the visual target).

---

## Decisions settled here

- **Charts: ECharts 5.5.0, vendored locally (not CDN).** Confirmed at Step 6.1 (the plan
  offered hand-rolled SVG vs. vendored ECharts; vendored chosen for the closest match to the
  comp — tooltips, animations, the stacked/pie/area configs carry straight over). The
  library is committed at `web/static/vendor/echarts.min.js`; the page loads it locally, so
  there is **no runtime network egress** (the project's hard privacy rule).
- **Font: JetBrains Mono, vendored woff2 (weights 400/500/600/700).** Same no-egress reason;
  committed under `web/static/vendor/fonts/` with an `@font-face` sheet, falling back to
  `ui-monospace, monospace` if a face fails to load.
- **Push mechanism: polling, not streaming.** The build plan's review note is explicit —
  don't stream data that changes every ~2s. The page polls the API every 2s and ticks the
  two live counters locally each second between polls (frozen while idle). Polling also
  gives Step 6.2 resilience for free: a failed fetch shows an "offline" state and keeps
  retrying, recovering when the API/collector returns.
- **The view is served by the API.** The Phase 5 `http.server` gains a static route (any
  non-`/api/` GET serves a file under `web/static/`, with path-traversal protection), so
  `python -m kdence.api --store DB` serves both the JSON and the dashboard at `/`.
- **Assets live inside the package (`src/kdence/web/`).** Located via a module-relative
  `STATIC_DIR`, mirroring how `focus/` already ships its KWin `.js` asset — robust whether
  run from source or installed, and it keeps the root lean (supersedes the earlier
  top-level `web/` guess in `structure.md`).

## No API changes needed

Phase 5 already returns everything: `/api/current` (current session), `/api/summary?range=`
(active total + per-app totals/share/sessions), and `/api/timeline?range=` (the raw active
spans). The charts that need time buckets (stacked distribution, active/idle trend, focus
band) **bucket the timeline spans client-side** — hourly for TODAY, daily for WEEK/MONTH —
exactly the split the design-system contract intends. Idle stays excluded from totals; the
trend's idle band is derived as `elapsed_in_bucket − active_in_bucket` for context only.

## Panels → data source (all from the Phase 5 API)

| Panel | Source | Notes |
|---|---|---|
| Current session bar (window / state / session / active today) | `/api/current` + `/api/summary?range=today` | session + active-today tick locally, freeze when idle |
| Range toggle TODAY/WEEK/MONTH | re-fetch `summary` + `timeline` for the range | |
| 5 KPI cards | `summary` + `timeline` (client-derived) | focus-switches, apps-used, longest streak from spans |
| Activity distribution (stacked bar) | `timeline` bucketed per app | ECharts stacked bar |
| Application share (donut) | `summary.apps` | ECharts pie, center = active total |
| Active vs. idle over time (trend) | `timeline` bucketed + derived idle | ECharts area lines |
| Focus timeline · today (band) | `timeline` (today) per-hour dominant app | plain HTML segments |
| Per-application totals (table) | `summary.apps` | plain HTML grid + share bars |

**App identity in the UI:** a small known map gives nice names/colors for common classes
(code, firefox, konsole, …); unknown classes fall back to a prettified last path segment and
a categorical-palette colour assigned by rank, stable across all panels in a refresh.
Desktop (null class) renders as "(desktop)". Titles are shown only if the collector captured
them (default off) — the view is meaningful with the class alone.

## Deliverables & tests

| Step | Deliverable | Test / Pass condition |
|---|---|---|
| 6.1 | `web/static/{index.html,styles.css,fonts.css,app.js}` + vendored ECharts/font | Static-route tests (headless): server serves `/`, the vendored JS, correct content types; traversal blocked; missing file → 404. |
| 6.1 | Static route in `api/server.py` | Existing Phase 5 API tests still pass (routes unaffected). |
| 6.1 | Live behaviour | **Manual/live:** open the view while the collector writes; the app, state, session, and today's total track reality and the total **freezes** when idle. Also verified in-session via the browser tool against a seeded store. |
| 6.2 | Resilience | **Manual:** restart the collector/API with the view open; it shows "offline" then recovers, never wedges. (Fetch errors are caught; polling continues.) |

Automated coverage is the static-serving tests plus an in-session browser render against a
seeded store; the "watch it while you actually work" checks are inherently manual and handed
off, like the earlier live gates.

## Commands

```bash
uv run python -m kdence.collector --store /tmp/kdence.db   # writer (terminal 1)
uv run python -m kdence.api       --store /tmp/kdence.db   # serves the view at http://127.0.0.1:8765/
# open http://127.0.0.1:8765/ in a browser
uv run pytest tests/api                                    # includes the static-route tests
```

## Not in scope

- Auth / multi-user (single local user, by project decision).
- Historical drill-down beyond TODAY/WEEK/MONTH; the comp's range set is the surface.
