# KDence — Project Documentation

## Purpose

KDence is a **local, privacy-preserving activity tracker** for **KDE Plasma 6 on
Wayland**. It answers a single honest question — *"how long was I actually working?"* — by
observing activity (active vs. idle) and window focus (which app), converting those
observations into durations, storing them locally, and serving a read-back API plus a
minimal live view.

All data stays on the user's machine. There is no cloud sync, no telemetry, and no network
egress.

## Intended User

A single desktop user on their own machine (solo use, single writer). Not multi-tenant.

## Tech Stack

| Concern | Choice | Status |
|---|---|---|
| Language / runtime | Python 3.13 | Fixed (`.python-version`) |
| Package / env manager | `uv` | Fixed |
| Test runner | `pytest` | Fixed |
| Lint / format | `ruff` | Fixed |
| Time model | Stitched-heartbeat spans with back-dating (pure `model/`) | **Adopted (Phase 4)** — no dependency |
| Time-span storage | SQLite (stdlib `sqlite3`), single writer, WAL | **Adopted (Phase 4)** — no dependency |
| Read-back API | Stdlib `http.server` (`ThreadingHTTPServer`), 127.0.0.1 | **Adopted (Phase 5)** — no dependency |
| Activity / idle source | Stdlib Wayland wire client for `ext_idle_notifier_v1` | **Adopted (Phase 1)** — no dependency |
| Compositor focus access | KWin script over `org.kde.kwin.Scripting` + `dbus-fast` receiver | **Adopted (Phase 2)** — `dbus-fast` |
| Live view | Static HTML/CSS/JS served by the API; **ECharts 5.5.0 vendored** (not CDN) | **Adopted (Phase 6)** — no runtime egress; design in `docs/design-system.md` |
| Session lifecycle | systemd **user** units bound to `graphical-session.target`; venv interpreter in `ExecStart` | **Adopted (Phase 7)** — no dependency; rendered/tested pure in `service/units.py` |

A frontend **design comp** for the live view is kept at
`docs/references/frontend/` (a dark-terminal dashboard mockup + its runtime) as a visual
reference for Phase 6. It is reference-only, not app code — its tokens and panel/data
contract are translated into [`docs/design-system.md`](design-system.md), the source of
truth the Phase 5 API is shaped against and the Phase 6 view is built from.

Runtime dependencies are added **per build-plan phase** (`uv add`) rather than all up
front, because the build is test-driven and each phase pulls in only what it needs. The
"Proposed" rows above are recommended defaults, not commitments — each is a decision point
in the build plan.

## Architecture

The system decomposes into four loosely-coupled parts (see the build plan for the full
rationale). The key design rule is a **clean seam between pure logic and
hardware-dependent code**:

```
 hardware-dependent (needs a live Wayland session, little logic)
   ┌─────────────┐        ┌─────────────┐
   │  activity/  │        │   focus/    │
   │ active/idle │        │ which app   │
   └──────┬──────┘        └──────┬──────┘
          └──────────┬───────────┘
                     ▼
              ┌─────────────┐   pure logic (fake timestamps, no hardware)
              │ collector/  │──▶│  model/  │  observations → durations
              └──────┬──────┘   └────┬─────┘
                     ▼                ▼
              ┌─────────────┐   ┌─────────────┐
              │  storage/   │◀──│ single-writer│  SQLite spans
              └──────┬──────┘   └─────────────┘
                     ▼
              ┌─────────────┐        ┌─────────────┐
              │    api/     │───────▶│  web/ view  │  read-back + live
              └─────────────┘        └─────────────┘
```

- **`activity/`** — active-vs-idle detection from the Wayland idle signal. On Wayland the
  compositor tracks input at the *seat* level (keyboard + mouse + touch together), which
  collapses the "merge two input streams" problem into one signal. This is *proven* in
  build-plan Step 1.1, not assumed.
- **`focus/`** — the currently focused window's identity, reported out of the compositor
  (KWin scripting / DBus). Window-identity fields and the title-privacy stance are decided
  in Step 2.2.
- **`model/`** — pure time model: turns instantaneous observations into non-overlapping
  durations. Owns the **active→idle boundary rule** (an active span ends near last-input,
  not near detection — the back-dating case). No hardware; fully unit-testable.
- **`storage/`** — single-writer SQLite datastore under the tested model; reads must not
  block or corrupt writes.
- **`collector/`** — merges the two live signals and owns the daemon loop that writes spans.
- **`api/`** — read-back query layer: current state, today's per-app totals, and a timeline.
  Pure aggregates (`api/queries.py`) served by a thin stdlib `http.server`; reads run over
  **read-only** SQLite connections so they never block the writer. The local-day rule and any
  midnight split live here, not in storage.
- **`web/`** — a minimal live view (dark-terminal dashboard) that agrees with the API and
  with reality. Static assets served by the API itself; polls every ~2s; charts are ECharts
  vendored locally. No runtime network egress.
- **`browser/`** — browser-activity seam: the active tab's **site** (hostname) as a
  sub-dimension *under browsers only*. Pure `site.py` (hostname → public host / generic
  `(local app)` bucket) and `tracker.py` (focus-gated latest-tab-per-engine, TTL) plus a
  loopback-only `ingest.py` the collector runs. A cross-browser WebExtension in
  `browser-extension/` reads the active tab and POSTs its hostname to `127.0.0.1`; the site
  rides on the browser's spans and surfaces only in the per-application table drill-down —
  the charts still treat each browser as one entity.
- **`detail/`** — in-app detail providers: *what you were doing inside* a focused app, the
  generalisation of the browser-only `site` sub-dimension. Pure policies (`caption.py`:
  window title → document/tab label; `mpris/policy.py`: media metadata → track label) plus a
  focus-gated `mpris/tracker.py` and a thin `mpris/source.py` (D-Bus, `dbus-fast`). The
  collector's `collector/providers.py` registry queries providers in priority order
  (site → mpris → caption) and the winner rides on the span's generic `detail`/`detail_source`
  columns. **Opt-in and default OFF** (privacy): each provider is enabled explicitly and
  honours an app-class denylist; local file paths are generalised to `(local file)`.
- **`grouping/`** — application grouping: rolls per-application totals up into user-defined
  **categories** (Work, Entertainment, Social, Games, …). Pure `palette.py` (a 12-colour
  starting palette + a `variant()` that shades member apps relative to their category) and
  `categories.py` (definitions + an `app_class → category` map, opinionated defaults, atomic
  load/save). It is *configuration*, kept in `categories.json` off the span store, so the
  store's single-writer isolation is untouched. The rollup (`group_totals`) lives in
  `api/queries.py`; the dashboard's totals table toggles between by-app and by-category.

## Major Decisions

1. **Python + `uv`, Python 3.13.** Matches repo conventions and the tracker's system-level needs.
2. **Pure logic isolated from hardware.** The time model is fully unit-tested with fake
   timestamps; DBus/KWin/Wayland parts carry almost no logic. This seam is what makes
   per-step testing possible.
3. **Activity is one signal.** Seat-level input tracking on Wayland; verified in Step 1.1.
4. **Local-only / privacy-first.** No network egress; window titles treated as sensitive.
5. **Dependencies added per phase**, not up front — the build is test-driven.
6. **Web surface kept minimal.** The upstream `website-architecture` / `ui-frontend` /
   accessibility skills are **not present** in this repo and are intentionally out of
   scope: the live view is a small local surface backed by the read-back API, not a
   public web app. Revisit only if the view grows into a real front end.
7. **Agent tooling: Claude Code, OpenAI Codex, and Cursor** are configured; pointer files
   live in `.claude/skills/`, `.agents/skills/`, and `.cursor/rules/` respectively, each
   routing to the canonical `docs/skills/`. Other tools can be added the same way.
8. **Lean root.** Only `docs/`, `src/`, `tests/` exist as visible top-level folders;
   phase-specific dirs (`web/`, `scripts/`, `utils/`, component subpackages) are created
   when their build-plan phase begins rather than pre-scaffolded empty.
9. **Idle is read from the compositor, not DBus.** A probe confirmed
   `GetSessionIdleTime` is `NotSupported` on Wayland. `activity/` therefore speaks the
   `ext_idle_notifier_v1` protocol directly over the Wayland socket using only the
   standard library (no `pywayland`/CFFI compile, no `sudo`, no third-party dependency).
   The event-based signal (`idled`/`resumed`) is turned into a threshold decision by the
   pure `ActivityMonitor`, which owns the clock — keeping the hardware/logic seam clean.
10. **Focus comes from a KWin script, via `dbus-fast`.** On Plasma 6 / Wayland there is no
    DBus property for the active window's class. `focus/` loads a KWin script (over
    `org.kde.kwin.Scripting`) that connects to `workspace.windowActivated` and calls back
    out via `callDBus` — the only reliable egress from KWin's sandboxed engine (`print` is
    swallowed; timers are unavailable). A small **local** DBus service (`dbus-fast`,
    pure-Python — no compiler) receives the calls. `dbus-fast` is the first runtime
    dependency; it installs cleanly where `pywayland` did not. Proven live in Step 2.1.
11. **Window titles are opt-in (default off).** `focus/` keeps the app class always but
    drops titles unless `capture_titles=True`, because captions leak document names and
    URLs (the privacy rule: default to the more private option). The live view is designed
    to be meaningful with the app class alone.
12. **Time model = stitched heartbeats with back-dating.** `model/Timeline` turns per-interval
    `active` heartbeats into contiguous, non-overlapping spans: same-window heartbeats within
    a `max_gap` extend one span; a different window starts a new contiguous one. Two honesty
    rules are baked in — the active span ends at the **back-dated last-input** instant on
    idle (not at detection, so trailing idle is never counted), and any heartbeat gap larger
    than `max_gap` (a suspend/stall) is **not** active time. Idle is stored as the *absence*
    of a span. Fully hardware-free; proven in `tests/model` (the four named cases). Written
    up in `docs/plans/phase-4-time-model-and-storage.md`.
13. **Storage is single-writer SQLite (stdlib), day-agnostic.** `storage/Store` persists one
    SQLite write per model event (open / extend / close) in WAL mode so Phase 5 readers never
    block the writer; at most one row is ever `open=1`. On startup it finalizes any span left
    `open` by a crash **at its last stored heartbeat** — never extended to restart time (no
    invented hours). Spans store absolute wall-clock `start_at`/`end_at`; the "local day"
    definition and any midnight split live in the Phase 5 read layer, not at write time.
    `sqlite3` is stdlib, so Phase 4 added **no** runtime dependency.
14. **Read-back API is stdlib `http.server`, not FastAPI.** Confirmed at Step 5.1 (the plan
    proposed FastAPI+Uvicorn but flagged it for confirmation). The read surface is ~4 local
    GET endpoints returning JSON to a single user on `127.0.0.1`; a `ThreadingHTTPServer`
    (thread per request) handles concurrent reads with **no new dependency**, matching the
    project's stdlib-first pattern. Correctness lives in a pure query module
    (`api/queries.py`) — totals, per-app share, timeline, current-state, and local
    TODAY/WEEK/MONTH windowing — unit-tested without HTTP; the server is a thin shell.
15. **Reads are isolated from the writer by construction.** Each request opens its own
    read-only (`mode=ro`) connection against the WAL database, so any number of readers run
    without blocking or corrupting the collector's single writer, and threads never share a
    connection. "Current session" is derived from the store's open row rather than a live
    channel to the collector, keeping the isolation clean.
16. **Live view: vendored ECharts, served by the API, polling (not streaming).** Confirmed at
    Step 6.1 (the plan offered hand-rolled SVG vs. vendored ECharts; vendored chosen for the
    closest match to the comp). ECharts 5.5.0 and JetBrains Mono woff2 are committed under
    `web/static/vendor/` and loaded locally, so there is **no runtime network egress**. The
    Phase 5 `http.server` gained a traversal-safe static route serving the dashboard at `/`.
    The page polls `/api/current` + `/api/summary` + `/api/timeline` every ~2s (data changes
    ~every collector interval, so polling beats streaming) and buckets the timeline spans
    client-side for the charts — **no API change** was needed. Assets live inside the package
    (`src/kdence/web/`, resolved via `STATIC_DIR`) like the `focus/` KWin asset, so the
    top-level `web/` from the original layout plan was not created.
17. **Session lifecycle is systemd user units, rendered as pure text.** Phase 7 makes both
    processes start with the graphical session (`After=`/`PartOf=`/`WantedBy=graphical-session.target`,
    so DBus and the compositor are up first) and restart on failure with a start-rate backoff.
    The unit *content* — the ordering, restart policy, `ExecStart`, durable store, and
    local-only bind — is generated by a pure module (`service/units.py`) and unit-tested
    without systemd; only enabling the units and surviving a real logout/login is a live gate.
    `ExecStart` uses the **project venv interpreter** (not `uv run`) so the service does no
    sync/network at start. The unit passes an **explicit** durable
    `--store %h/.local/share/kdence/kdence.db`; this deliberately does **not** change the
    collector's default (the persistent-default work stays deferred as Phase 9), but it means
    the service writes to reboot-surviving storage today. No runtime dependency was added.
18. **Historical navigation: durable default + anchored/custom windows + server buckets.**
    Phase 9 makes the forever-archive explorable. The store default moved off RAM-backed `/tmp`
    to `$XDG_DATA_HOME/kdence/kdence.db` (`storage/paths.py`), so data survives reboots by
    default (the Phase 7 units already used this path). The pure query layer gained
    `range_window(anchor=…)` (the period *containing* any date), `day`/`year`, `custom_window`,
    and a calendar-aligned `bucket_series` with `auto_granularity`; the server exposes
    date-aware `/api/summary`&`/api/timeline`, `/api/extent` (the navigable range), and
    `/api/buckets` (bounded series). The view drives its charts from `/api/buckets` so a
    year/all-time view never ships every raw span, and adds a Day/Week/Month/Year/Custom
    selector + prev/next + a date picker bounded by the extent. Plain `?range=today` is
    unchanged (back-compat). No runtime dependency was added; the DST-boundary skew over long
    history is a recorded accepted limit (`docs/honesty-review.md`).
19. **Browser activity: active-tab site as a browser-only sub-dimension, via a WebExtension →
    loopback.** The active tab's URL cannot be read from the compositor on Wayland, so a small
    cross-browser WebExtension (`browser-extension/`; one MV2 Gecko build for LibreWolf/Firefox,
    one MV3 Chromium build for Brave/Chromium/Chrome) reads it and POSTs the **hostname only**
    to a loopback listener the collector runs (`browser/ingest.py`, `127.0.0.1:<ingest port>`,
    default `5786`, refuses any non-loopback bind). Pure logic classifies it: `site.py` collapses loopback / RFC1918 /
    link-local / `.local` / bare single-label hosts into one generic `(local app)` bucket and
    normalises public hosts (lowercased, `www.` stripped); `tracker.py` keeps the latest tab
    per engine with a TTL and only attributes a site to the *focused* browser. The site rides on
    the span via a new nullable `site` column (additive, migrated store — **not** the sensitive
    opt-in `title` field) and surfaces **only** in the per-application table drill-down; the
    distribution/donut charts still treat each browser as a single entity. Privacy invariants:
    loopback-only, hostname-only, local stays generic, titles untouched. No runtime Python
    dependency was added (the extension is separate, unpacked per browser).
20. **Application grouping: user categories as config, edited live, off the span store.**
    Per-app totals roll up into user-defined categories. The definitions + `app_class →
    category` map live in `$XDG_CONFIG_HOME/kdence/categories.json` (`grouping/`), **not**
    the span store — so its single-writer isolation holds and the API stays read-only *w.r.t.
    spans*. The API gains its first mutation, `POST /api/categories`, which validates strictly
    and atomically writes **only** that config file (loopback, no cross-origin CORS headers).
    A reserved, non-deletable **Uncategorized** catches everything unassigned so group totals
    always reconcile with per-app totals; an opinionated `DEFAULT_ASSIGNMENTS` seed powers
    "Auto-categorize" (browsers are intentionally unseeded). Colours: a **12-colour** starting
    palette, with member apps painted as deterministic lightness **variants** of their
    category's base (computed server-side so there's one tested implementation). Charts stay
    per-app in v1; grouping is a table + summary feature. No runtime dependency (stdlib JSON).
21. **Site visualization + site-level categories.** The browser per-site drill-down is a compact
    **bar chart** (proportional bars, host + time) rather than text rows. Categories can also
    assign **hostnames** (a `site_assignments` map beside `assignments`, with an opinionated
    `DEFAULT_SITE_ASSIGNMENTS` seed): in *By group* mode a browser's time then **splits across
    categories by site** — each site placed by `resolve_site`, unassigned sites (and the browser's
    un-sited time) falling back to the browser app's own category, so every second lands in
    exactly one category and group totals still reconcile with the active total. `group_totals`
    gained an optional `site_totals` argument (default `None` keeps the whole-app behaviour). The
    editor grew a *Browser sites* section; no runtime dependency.
22. **One env-driven installer; canonical ports 5785/5786.** `install.sh` is the single,
    idempotent install/restart path: it reads `./.env` (`KDENCE_*` keys), generates the systemd
    user units from the **tested** `service/units.py` renderer (ports passed to `kdence.service
    install` — no `sed`), aligns the browser extension to the ingest port, and enables +
    restarts both services (re-running it *is* the restart), verifying `/api/health` at the end.
    The canonical defaults are **API 5785** and **tab-ingest 5786** (overridable in `.env`). It
    **never silently bumps** a busy port — a foreign owner is a hard error naming the `.env` key
    to change — because the earlier silent auto-bump is exactly what let the extension's target
    port and the collector's ingest port diverge (so no site data was recorded). The extension's
    committed default is 5786, so aligning is a no-op unless the port is customised.

23. **In-app detail: a generic `detail` sub-dimension with opt-in providers (Phase 13).** The
    browser-only `site` column is generalised to a nullable **`detail`** + **`detail_source`**
    (`site` | `caption` | `mpris`) carried through the model, merge, and store via the same
    additive, idempotent migration — a legacy `site` value is **coalesced** on read
    (`SpanRow.effective_*`), so months of history and the browser drill-down keep working with
    no backfill. A `collector/providers.py` registry resolves one `(detail, source)` per interval
    in priority order **site → mpris → caption** (so a focused browser still wins with its host).
    Two new sources land: **caption** (the KWin script now also fires on a focused window's
    `captionChanged`, so an in-window document/tab switch is seen; a pure `detail/caption.py`
    strips the app-name suffix and generalises file paths) and **MPRIS** (a pure policy + a
    focus-gated tracker fed by a `dbus-fast` source that *polls* the session bus on the collector
    interval — same D-Bus seam as focus, **no new dependency**). MPRIS labels what was playing but
    does **not** invent active time (honesty limit #1 stays). The per-application drill-down
    generalises from `sites[]` to `details[]` (labelled by source) for **every** app; charts still
    treat each app as one entity. **Privacy is first-class and the regression is opt-in:** every
    provider is OFF unless listed in `KDENCE_DETAIL_PROVIDERS`, an app-class `KDENCE_DETAIL_DENYLIST`
    suppresses sensitive apps, and local files/paths never leave the machine by name. Two robustness
    bugs in the touched code were fixed in passing: the **focus-freeze** (the KWin script is now
    re-injected via `isScriptLoaded` if the compositor evicts it, instead of silently freezing focus
    and mislabelling hours) and the **fatal tab-ingest bind** (a busy ingest port now logs and
    continues instead of crash-looping the whole collector). The browser engine map also moved to an
    optional `browsers.json` (bundled default extended, so Zen/Vivaldi/Opera/Edge work with no code
    change). AT-SPI2 (a deeper accessibility-bus source) is recorded as `[future]`, not built.

## Current Status

**Phases 1–9 complete (headless + review); browser activity, application grouping + site categories + in-app detail (Phase 13) added; live gates pending.** Phase 0 gates (platform confirmed:
Wayland, Plasma 6.7.3; trustworthy test runner), Phase 1 (Wayland idle source + pure activity
monitor), Phase 2 (KWin-script focus source + pure identity/reporter), Phase 3 (live merge of
both signals), Phase 4 (pure time model + single-writer SQLite storage under it), Phase 5
(read-back query layer over a stdlib HTTP server, isolated from the writer), Phase 6 (the
live-view dashboard served by that API), Phase 7 (session lifecycle — systemd user units —
plus the soak sampler/summary), and Phase 9 (historical navigation — durable store, anchored/
custom windows + `/api/extent` + `/api/buckets`, and date navigation in the view) are done and
validated — **114 synthetic tests pass headless** (including the four named Step 4.2 honesty
cases, the crash-recovery test, the Phase 5 endpoint-reconciliation + concurrent read/write
cases, the Phase 6 static-route/traversal tests, the Phase 7 unit-content + soak-slope tests,
and the Phase 9 anchored-window / bucket-reconciliation / extent tests). The view was verified in-session
against both a seeded store and the **live running collector** (the API returned a real active
`brave-browser` session; the per-app table reconciled with the store). Phases 4–7 each added
**no** runtime dependency (stdlib `sqlite3` / `http.server` / `/proc` + `systemctl`; ECharts +
the font are vendored assets, not Python deps); the only runtime dep remains `dbus-fast`
(Phase 2). Remaining **manual checks** (need a human): keyboard-only vs mouse-only idle reset
(Phase 1); two-app focus switching and keyboard return-to-active (Phases 2–3); a live
persistence eyeball + hard-kill crash-recovery (Phase 4); watching the view track reality /
freeze on idle / recover after a collector restart (Phase 6); and the Phase 7 live gates. The
Phase 7 units are now **installed, enabled, and verified up** — the systemd-managed collector +
API run against the durable store and track a real live session — though **logout/login
survival, kill→restart, and the full-day soak** still need a human. **Phase 8** is done bar its
one live gate: the **full regression sweep passed** (87 headless tests green in a single pass,
`ruff` clean) and the **honesty review** is written (`docs/honesty-review.md` — presence ≠
productivity, with 7 known limits tagged accepted/future); the **cold-start stopwatch E2E**
(Step 8.1) remains a human measurement gate. **Phase 9** (historical navigation) is implemented
and its endpoints verified in-session against a 7-month seeded store (live/month/year/day/custom
all reconciled); its remaining gate is the interactive scrub over your own real archive as it
grows. **Browser activity** (added scope) is implemented and headless-verified: the site policy,
tracker, loopback ingest, migrated `site` column, per-browser `/api/summary` drill-down, and
manifest privacy invariants all pass, and the expandable table was verified in-browser against a
seeded store (LibreWolf/Brave expand to per-host breakdowns that reconcile; charts unchanged).
Its live gate is loading the WebExtension in a real browser and confirming attribution.
**Application grouping** (added scope) is implemented and verified: the palette/variant maths,
category config (defaults, validation, atomic round-trip), the `group_totals` rollup, and the
`/api/categories` read+write all pass headless, and the grouped-table toggle + inline editor
were verified in-browser (group rollup with member colour variants, reassignment persisted to
`categories.json` and re-rolled, by-app mode + charts unchanged). **Site visualization + site
categories** (added scope) is implemented and verified: the browser drill-down is a mini bar
chart, categories can assign hostnames, and `group_totals` splits a browser across categories by
site (verified in-browser — default seed sorts github→Work, youtube/twitch→Entertainment,
reddit→Social; reassigning a site re-rolls and reconciles). **In-app detail** (Phase 13, added
scope) is implemented and headless-verified: the generic `detail`/`detail_source` column +
additive migration + legacy-`site` coalescing, the provider registry (priority + denylist), the
pure caption and MPRIS policies/trackers, the config-driven browser map, the non-fatal ingest and
focus-script re-inject, and the generalised `details[]` drill-down all pass; the seeded dashboard
shows per-app detail bars tagged by source (site/caption/mpris) and the numbers reconcile, and the
MPRIS D-Bus read path was exercised live on-machine. Its **live gates (human):** confirm KWin fires
`captionChanged` for a focused window on Plasma 6.7, and eyeball live caption + MPRIS attribution
while switching documents / playing media. The whole suite is now **286 headless tests**
(`-m "not live"`), `ruff` clean. Execution follows
`docs/plans/activity-tracker-build-plan.md`; per-phase detail lives under `docs/plans/`.

For what the numbers do and do not mean, see **`docs/honesty-review.md`**.

See `docs/checklist.md` for the Definition of Done and remaining work.
