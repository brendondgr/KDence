# Dashboard Refinement — Plan (feedback pass)

Front-end-only polish of the Phase 6/9 live view from user feedback. No API/Python change —
every value needed is already served by `/api/summary`, `/api/buckets`, `/api/timeline`, and
`/api/current`. The comp tokens in `docs/design-system.md` still hold.

## Feedback → change

1. **One compact top row of stats.** Collapse the tall "current session" bar *and* the 5 KPI
   cards into a single row of small tiles, in this order: Active Time, Idle Time, Focus
   Switches, App Views, Longest Session, Focus Window, Stage (state), Current Session, Active
   Today. The first five reflect the *viewed window*; the last four are *live-now* (blank/"—"
   in a historical view).
2. **Combine the two time-series charts.** Merge "Activity distribution" (per-app stacked bars)
   and "Active vs. idle over time" (idle line) into one chart on the shared bucket x-axis —
   stacked active bars + an idle line overlay. Keep the "Application share" donut beside it.
3. **Remove "Focus timeline · today."** Drop the panel and its code.
4. **Real-time.** Confirm the live view actually polls + ticks (it does when `isLive()`), and —
   critically — the *running* systemd `timekeeper-api` must be **restarted** to pick up the new
   endpoints/assets, else the new page 404s on `/api/extent` and shows "offline" (the likely
   cause of "doesn't update"). Restart it as the deploy step.

## Steps (each verified in the in-session browser against a seeded store)

- **1 — Top strip.** `index.html`: replace `.current` + `#kpis` with one `#topstats` row of 9
  `.stat` tiles (stable ids). `styles.css`: `.topstats` responsive grid + compact `.stat`.
  *Validate:* all nine tiles render in a single row on desktop; live tiles tick.
- **2 — Combined chart + removals.** `index.html`: one chart panel (bars+line) + donut; delete
  the trend panel and the focus-timeline panel. `styles.css`: drop `.chart.trend`/`.band*` if
  unused. *Validate:* the combined chart shows both per-app bars and the idle line on one axis.
- **3 — app.js rewire.** `renderTopStats(...)` fills the strip (folding in the old
  `renderCurrent`/`renderKpis`); `renderCharts(...)` builds bars+line + donut (drop trend);
  delete `renderFocusBand`; `refresh()` fetches summary+buckets+timeline(+current when live);
  `tick()` updates the session + today tiles. *Validate:* live today ticks; a historical day
  fills the range tiles and blanks the live ones; totals reconcile with the API.
- **4 — Deploy + verify.** `ruff`/tests unaffected (no Python change); `systemctl --user
  restart timekeeper-api`; confirm the real dashboard at `127.0.0.1:8765` loads live.

## Commit

Single commit (front-end): `dashboard: compact top-stat strip, combined activity chart, drop focus timeline`.
