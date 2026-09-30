# Time-of-Day Heat Map — Plan + build record

A dashboard row under *Activity distribution* / *Breakdown* showing, for every five-minute slot
of the day, how active that slot usually is — so both "which hours" and "which five minutes of
those hours" read off one picture. It is computed from the existing archive (no new collection),
defaults to **all time**, offers shorter windows, and is **precomputed daily** rather than
re-derived on every request.

## Decisions

- **Shape.** 24 hour columns × 12 five-minute rows (`:00` at the top), plus an hourly bar strip
  above that sums each column. Wide rather than tall so it fits as a dashboard row and on a phone.
- **Value.** Average active minutes per slot per **calendar** day in the window (0–5). A day the
  machine was off counts as zero — "on an average day" is the honest denominator. The tooltip
  adds how many of those days the slot was active at all, plus the raw total.
- **Completed days only.** Today is excluded, so a day's slots are final once computed. That is
  what makes a once-a-day precompute correct rather than an approximation.
- **Windows.** `7 / 30 / 90 / 365 / all` completed days ending yesterday, clamped to the archive's
  first day. Independent of the date navigation: this is a long-horizon pattern, not a period view.
- **Where the "background service" lives.** A daemon thread in the API process
  (`HeatmapCache.start_refresher`) checks every 5 minutes whether the local date rolled over and
  rebuilds once if so; a request that beats it rebuilds on demand. A separate systemd timer was
  considered and rejected: the API is the only consumer and is always running, so a timer would
  add a unit, installer surface, and a cross-process file handshake for no gain.
- **Persistence.** `$XDG_CACHE_HOME/kdence/heatmap.json` (atomic write), so a restart reuses the
  day's build. It is derived: missing / stale / corrupt → rebuild. ~100 KB for 71 days.
- **Cost.** A full rebuild reads only `(start_at, end_at)` via `SpanReader.intervals_before` and
  took ~0.1 s over ~82k spans / 71 days. Full rebuild (not incremental) keeps it self-healing.
- **Privacy.** Only per-slot second counts are cached — no app class, title, or detail. Local
  disk only; no new network surface beyond the loopback route.
- **Dependencies.** None added. ECharts' built-in heatmap + visualMap.

## Steps (all done)

1. **Pure binning** — `src/kdence/api/heatmap.py`: `daily_slots`, `resolve_range`, `aggregate`.
   Pass: seconds split exactly on five-minute wall-clock boundaries, spans across midnight land
   on both days, nothing at/after the cut-off is binned, totals reconcile with the intervals.
2. **Daily cache** — `src/kdence/api/heatmap_cache.py` + `storage/paths.py` cache helpers +
   `SpanReader.intervals_before`. Pass: one build per local date (in memory and across a fresh
   process via the file), exactly one rebuild on rollover, a corrupt file is rebuilt.
3. **Route** — `GET /api/heatmap?days=…` in `api/server.py`; `--heatmap-cache` on `kdence.api`,
   which also starts the refresher. Pass: completed days only, bad `days` → 400.
4. **Panel** — `index.html` / `styles.css` / `app.js` (`renderHeatmap`, `fetchHeatmap`). Pass:
   renders against the real archive on desktop and at 375 px with no horizontal overflow;
   tooltips and the range toggle work; re-renders only when the build or window changes.

Tests: `tests/api/test_heatmap.py` (12).

## Live gate

- After a real local midnight with the deployed API running, the panel's caption advances to
  include yesterday without a restart (listed in [checklist.md](../checklist.md)).

## Possible follow-ups (not built)

- A weekday / weekend filter (the per-day cache already supports it — sum a subset of days).
- Colour the cells by dominant category instead of intensity.
