# Phase 13 — In-app detail (what you were doing inside each app)

> Added scope. Detailed plan for the "drill-down per app" feature: seeing **where you were
> and what you were doing** inside each application — the document in an editor, the file in a
> viewer, the folder in a file manager, the track in a media player — as a generalisation of the
> browser per-site drill-down that already ships (Phase 10/12).

## 1. Introduction

KDence already answers *"how long, in which app"* and, for **browsers only**, *"on which site"*
(the WebExtension → loopback → `site` sub-dimension). This phase generalises that one
browser-specific column into a **provider-based `detail` sub-dimension** that works for
**non-browser apps too**, so the per-application drill-down can show what you were actually
doing: the Kate buffer, the Okular PDF, the Dolphin folder, the VLC/mpv track. The browser URL
drill-down is preserved unchanged — it simply becomes one provider (`site`) among several.

The approach keeps the project's core seam intact: **all hardware access stays in the collector
and two thin D-Bus/KWin sources; all policy stays in pure, unit-tested modules.** Three detail
sources are added, ranked by how structured and reliable they are:

1. **Caption stream (Tier 1)** — the focused window's title, which KDE/Qt/GTK apps update as you
   change document/file/tab. Highest coverage, near-zero cost. Requires a small KWin-script fix
   (today we only hear *window activation*, never a caption change *within* a focused window).
2. **MPRIS (Tier 2)** — structured media metadata (title/artist/album, PlaybackStatus) over the
   D-Bus seam we already own (`dbus-fast`). Covers VLC, mpv, Elisa, Spotify, and the browsers.
3. **AT-SPI2 (Tier 3)** — deferred as `[future]`; recorded, not built (chatty a11y bus, uneven
   toolkit coverage, slated for replacement upstream).

Plus one small extensibility change: the hardcoded browser engine map moves to config so a new
browser works without a code change.

**Privacy is the real design cost and is treated as first-class.** Captions and media metadata
leak document names, file paths, and viewing habits — a deliberate regression against the
title-privacy stance (decision #4 / #11). Per the confirmed decision, **all new detail providers
are opt-in and default OFF**; each carries a generalisation policy (local file paths → a generic
bucket) and an app-class **denylist**. The existing browser-`site` behaviour (already gated by
loading the extension) is unchanged.

## 2. Gaps & Unanswered Questions

**Resolved with the user (this session):**

- **Scope** — build Tiers 1 + 2 **and** config-driven browsers + full per-provider privacy
  controls. Defer AT-SPI2 as `[future]`.
- **Privacy default** — new detail capture (caption, MPRIS) is **opt-in, default OFF**
  (`KDENCE_DETAIL_PROVIDERS=`empty by default). Local file paths generalise to a bucket. This
  matches the existing `--titles` stance.

**Assumptions (simple gaps, proceeding):**

- **Column strategy — additive, never destructive.** The existing `site` column and its months of
  history are preserved. We *add* `detail` + `detail_source` columns (additive migration, the
  pattern `store.py` already uses). Reads coalesce a legacy `site` value as
  `detail_source = "site"`, so old data and the browser drill-down keep working with no backfill.
- **Provider priority** — `site` (browsers) → `mpris` (media players) → `caption` (everything
  else). Each provider returns `None` when not applicable, so for a focused browser `site` still
  wins (no regression); VLC resolves via `mpris`; Kate via `caption`. Order is the order of
  `KDENCE_DETAIL_PROVIDERS` (site is always in the chain; caption/mpris only when opted in).
- **MPRIS "playing while focused" presence** — the *detail label* (track/title) is built now.
  Turning passive playback into a **non-idle span state** touches the time-model honesty
  invariants; it is recorded as `[future]` in the honesty review and **not** folded into "active"
  in this phase (per the plan's own caution — inventing active time would undercut the project).
- **Two known robustness bugs are fixed opportunistically** because this phase reworks exactly
  those files: (1) the **focus-freeze** — `KWinFocusSource` never re-injects an evicted script — is
  fixed by the liveness/re-inject added for the caption stream (Step 13.3); (2) the **ingest bind
  being fatal** (a busy ingest port crash-loops the whole collector) is made non-fatal in
  Step 13.5. Both are in scope because the caption/provider work lands in the same modules.

**Complex gaps needing human verification (live gates — a human at the keyboard):**

- **Does KWin actually emit `captionChanged` for the focused window on this Plasma 6.7?** The
  whole caption tier rests on it. *Human intervention needed:* Step 13.0 is an explicit live probe
  before anything is built on it.
- **Live attribution** for caption + MPRIS (switch documents, play media) needs a human to eyeball
  the drill-down against reality. Marked as live gates on the relevant steps.

## 3. Hierarchical Step-by-Step Instructions

Each step keeps the build plan's **Review + Test + Pass** rhythm. Headless steps must add tests
that run with `uv run pytest -m "not live"`; live steps add `@pytest.mark.live` smoke tests plus a
human gate. Commit at the end of every validated step (commit only — do not push).

### Step 13.0 — Live gate: prove KWin emits `captionChanged` for the focused window
- **Locations:** a throwaway probe under `src/kdence/focus/` (mirroring `kwin_focus_report.js` /
  the Step 2.1 approach) driven from a short `python -m` harness; notes appended to
  `docs/plans/phase-0-platform-notes.md`.
- **Rationale:** The KWin scripting API emits a signal when a property changes and you re-read the
  property. `KWin::Window` *should* expose `captionChanged`, but Tier 1 is load-bearing on it, so
  we prove it live before building — exactly like Steps 1.1 and 2.1 gated their phases.
- **Review:** Confirm the probe connects `workspace.activeWindow.captionChanged` (and re-binds on
  `windowActivated`) and reports the new caption out via `callDBus`.
- **Test (live):** With the probe running, change the document/tab in one focused window (Kate
  buffer switch, Okular page/file) **without** changing focus; confirm a new caption is reported.
- **Pass:** A caption change *within* a single focused window is observed outside the compositor.
  If it fails, stop and reconsider the caption tier before writing more.
- **Action:** Validate; commit: `In-App Detail (1/8) Complete: proved KWin captionChanged live and recorded the platform fact`.

### Step 13.1 — Generalise the sub-dimension: `detail` + `detail_source` (+ provider registry scaffold)
- **Locations:** `model/timeline.py` (`Span`/`OpenSpan`: `site` → `detail` + `detail_source`; the
  same-window split keyed on detail change), `collector/merge.py` (`MergedSample` + `merge()`
  signature carry `detail`/`detail_source`), `storage/store.py` (`_MIGRATIONS` adds `detail`,
  `detail_source`; `SpanRow`; writer path; read coalescing legacy `site`), `storage/reader.py`
  (expose `detail`/`detail_source`, coalescing `site`; keep `_available_columns()` graceful),
  and a new `collector/providers.py` defining a `DetailProvider` protocol
  (`detail_for(app_class, now) -> (value, source) | None`) + an ordered registry. Tests in
  `tests/model`, `tests/storage`, `tests/collector`.
- **Rationale:** One generic sub-dimension replaces the browser-only special case, so every
  downstream consumer (model split, store, queries, view) has a single thing to carry. Additive
  migration preserves history; coalescing `site` keeps the browser drill-down and site-categories
  working with zero backfill.
- **Review:** Confirm the migration is additive-only and idempotent; a legacy DB with `site`
  populated reads back as `detail_source="site"`; the model splits a span on any detail change.
- **Test (headless):** model split-on-detail-change; store round-trip of `detail`/`detail_source`;
  legacy-`site` coalescing; a not-yet-migrated store still reads. Registry returns the
  highest-priority non-None provider result.
- **Pass:** All green; the existing browser-site tests still pass through the generalised column.
- **Action:** Validate; commit: `In-App Detail (2/8) Complete: generalised the span sub-dimension to detail/detail_source with additive migration + provider registry`.

### Step 13.2 — Pure caption policy + per-app parsers
- **Locations:** new `src/kdence/detail/caption.py` (pure; `(app_class, caption) -> detail | None`),
  a small per-app-class parser table (strip `" — Kate"`/`" — Okular"`-style suffixes, split
  `"file.pdf — Okular"`), a **generalisation rule** (paths / `file://` / obvious local files →
  `(local file)` sentinel, mirroring `site.LOCAL_APP`), and denylist handling. Tests in
  `tests/detail/test_caption.py`.
- **Rationale:** Captions are unstructured and app-specific; parsing them is pure and testable and
  must never leak a full local path. Mirrors `browser/site.py` exactly (policy in one pure module).
- **Review:** Confirm parsers are data-driven and default to a safe passthrough; the generalisation
  rule collapses local file paths; a denylisted class yields `None`.
- **Test (headless):** representative captions for Kate/Okular/Dolphin/LibreOffice/Konsole →
  expected labels; a path-bearing caption → `(local file)`; denylisted class → `None`.
- **Pass:** All caption cases assert with zero hardware.
- **Action:** Validate; commit: `In-App Detail (3/8) Complete: pure caption policy + per-app parsers + local-file generalisation`.

### Step 13.3 — Wire the caption stream through KWin (+ fix focus-freeze)
- **Locations:** `focus/kwin_focus_report.js` (connect the focused window's `captionChanged`,
  re-report, disconnect/re-bind on the next `windowActivated`), `focus/kwin_source.py` (forward
  caption changes; add a **liveness re-inject** — poll `isScriptLoaded`/re-load if evicted, fixing
  the focus-freeze bug), `collector/__main__.py` (maintain the focused window's raw caption and
  feed a `CaptionProvider` from `detail/caption.py`, only when opted in). Live test in
  `tests/focus/test_kwin_live.py`; headless test for the re-inject decision logic if extracted pure.
- **Rationale:** Today the script only hears `windowActivated`, so a document/tab change within a
  focused window is invisible (documented bug). The re-inject also cures the separate freeze where
  an evicted script silently mislabels hours. The raw caption bypasses the `WindowIdentity` title
  filter because the caption provider is itself opt-in and applies its own policy.
- **Review:** Confirm captions only flow when a caption provider is enabled; re-bind on activation
  leaks no stale connection; re-inject is idempotent.
- **Test (live gate, human):** enable the caption provider; switch buffers/files in one app without
  changing focus; confirm the detail updates. Kill/evict the script; confirm it re-injects and
  focus resyncs (no stale-app mislabelling).
- **Pass:** Caption detail tracks in-window changes live; the freeze no longer strands focus.
- **Action:** Validate; commit: `In-App Detail (4/8) Complete: caption stream wired through KWin with liveness re-inject (fixes focus-freeze)`.

### Step 13.4 — MPRIS detail source (structured media metadata)
- **Locations:** new `src/kdence/detail/mpris/` — `source.py` (hardware side: `dbus-fast`,
  discover `org.mpris.MediaPlayer2.*` bus names, subscribe to `PropertiesChanged`, hold per-player
  metadata + `PlaybackStatus`), pure `policy.py` (metadata → label; `file://` URLs → `(local
  file)`, never the path), pure `tracker.py` (focus-gated latest-player-per-app + TTL, mirroring
  `browser/tracker.py`). Wire an `MprisProvider` into `collector/__main__.py` when opted in. Tests
  in `tests/detail/test_mpris_policy.py`, `test_mpris_tracker.py` (headless) + a `live` smoke test.
- **Rationale:** Same D-Bus seam, second consumer — no new dependency. Structured metadata is more
  reliable than captions for media, and event-driven (no polling). Presence-as-non-idle is **not**
  folded into active time here (recorded `[future]`).
- **Review:** Confirm the tracker is focus-gated with a TTL; the policy never stores a file path;
  a stale/closed player stops attributing.
- **Test (headless):** metadata → label; `file://` → `(local file)`; tracker TTL + focus gating.
- **Test (live gate, human):** play a track in VLC/mpv/Elisa focused; confirm the detail shows the
  track; unfocus/stop; confirm it clears.
- **Pass:** Media detail resolves for a focused player and clears when gone; policy tests green.
- **Action:** Validate; commit: `In-App Detail (5/8) Complete: MPRIS detail source (pure policy + focus-gated tracker + dbus-fast source)`.

### Step 13.5 — Config-driven browser engine map (+ non-fatal ingest bind)
- **Locations:** `browser/tracker.py` (`BROWSER_CLASSES` loaded from config with the current map
  as the bundled default), a new `browsers.json` under `$XDG_CONFIG_HOME/kdence/` via
  `storage/paths.py`, and `browser/ingest.py` / `collector/__main__.py` (a busy ingest port logs
  and continues instead of crashing the collector — fixes the crash-loop bug). Tests in
  `tests/browser/test_tracker.py` (config load + default), `tests/browser/test_ingest.py`
  (bind-failure is non-fatal).
- **Rationale:** Both extension builds already cover Zen/Waterfox/Floorp/Vivaldi/Opera/Edge by
  engine; only the class map lacks them. Config lets a user add `"zen"` with no code change. The
  ingest fix stops a browser-only feature from taking down all recording.
- **Review:** Confirm a missing/short config falls back to the bundled default (never empty); an
  unknown engine token is still ignored; ingest bind failure is logged, not fatal.
- **Test (headless):** config with an extra browser resolves it; absent config uses defaults; a
  simulated bind error leaves the collector running.
- **Pass:** Browsers are config-extensible and a busy ingest port no longer crash-loops the daemon.
- **Action:** Validate; commit: `In-App Detail (6/8) Complete: config-driven browser engine map + non-fatal tab-ingest bind`.

### Step 13.6 — Privacy controls: per-provider opt-in, denylist, generalisation
- **Locations:** `collector/__main__.py` (parse `KDENCE_DETAIL_PROVIDERS` + `--detail-providers`;
  build only the opted-in providers; site stays as today), a shared denylist honoured by every
  provider (`KDENCE_DETAIL_DENYLIST` / `--detail-denylist`), `service/units.py` (`UnitContext`
  gains the detail flags so installed units carry them), `install.sh` + `.env.example` (new
  `KDENCE_DETAIL_*` keys), and docs. Tests in `tests/service/test_units.py` (rendered flags) and a
  collector-wiring test asserting default-off.
- **Rationale:** The confirmed decision: each provider opt-in, default off; a denylist so password
  managers / banking / messaging apps are never detailed; generalisation already lives per-provider
  (13.2/13.4). One env-driven path so the installer stays the single source of truth.
- **Review:** With no config, **no** caption/MPRIS detail is captured (site unchanged); a
  denylisted class yields no detail from any provider; units render the flags only when set.
- **Test (headless):** default construction enables site only; `KDENCE_DETAIL_PROVIDERS=caption`
  enables caption; denylist suppresses a class; `units.py` emits/omits the flags correctly.
- **Pass:** Detail is off by default, per-provider on demand, and denylist-suppressed everywhere.
- **Action:** Validate; commit: `In-App Detail (7/8) Complete: per-provider opt-in + denylist + installer/unit wiring (default OFF)`.

### Step 13.7 — Surface it: generalised drill-down + honesty review + docs
- **Locations:** `api/queries.py` (per-app `details[]` — label/source/seconds — for all apps, not
  just browsers; keep browser `site` categorisation working via `grouping/categories.py`
  `resolve_site` reading `detail_source="site"`), `web/static/app.js` (+ `index.html`/`styles.css`)
  (generalise the browser drill-down to a per-app detail drill-down; reuse the `barRows` renderer;
  label rows by source), `docs/honesty-review.md` (rewrite limit #3 class-only attribution, note
  MPRIS on limit #1, add caption/MPRIS sensitivity limits), and the canonical docs
  (`documentation.md` decision + status, `structure.md` new `detail/` package + config, `workflow.md`
  new commands/env, `checklist.md` Phase 13 items, `activity-tracker-build-plan.md` Phase 13
  section). Tests in `tests/api/test_queries.py` (details reconcile with per-app totals) +
  `tests/api/test_categories.py` (site rollup still reconciles).
- **Rationale:** The whole point is the drill-down; grouping and the bar chart come along nearly
  free because they already resolve sites. The honesty review must change meaning — class-only
  attribution is no longer the only option — so the numbers are never quietly misleading.
- **Review:** Confirm `details[]` per app reconciles with that app's total; the browser site
  drill-down and site-categories are unchanged for existing data; charts still treat each app as
  one entity.
- **Test (headless):** per-app `details[]` sums to the app's active seconds; site rollup reconciles
  with the active total. **In-browser (in-session):** a seeded store shows per-app detail bars.
- **Test (live gate, human):** with providers on, real use shows documents/media/URLs in the
  drill-down.
- **Pass:** Drill-down shows what you were doing per app, everything reconciles, docs + honesty
  review are current.
- **Action:** Validate; commit: `In-App Detail (8/8) Complete: generalised per-app detail drill-down + honesty-review rewrite + docs`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Caption live probe + platform note | Prove `captionChanged` fires for a focused window | `src/kdence/focus/` probe; `docs/plans/phase-0-platform-notes.md` |
| Generic `detail` sub-dimension | `detail` + `detail_source` through model, merge, store, reader (additive migration; legacy `site` coalesced) | `model/timeline.py`, `collector/merge.py`, `storage/store.py`, `storage/reader.py` |
| Provider registry | Ordered `DetailProvider` protocol + registry | `src/kdence/collector/providers.py` |
| Caption policy | Pure `(app_class, caption) -> detail` + per-app parsers + `(local file)` generalisation + denylist | `src/kdence/detail/caption.py` |
| KWin caption wiring + re-inject | Report in-window caption changes; re-inject evicted script (fixes focus-freeze) | `focus/kwin_focus_report.js`, `focus/kwin_source.py`, `collector/__main__.py` |
| MPRIS detail source | `dbus-fast` source + pure policy + focus-gated tracker | `src/kdence/detail/mpris/{source,policy,tracker}.py` |
| Config-driven browsers + ingest hardening | `browsers.json` engine map; non-fatal ingest bind | `browser/tracker.py`, `browser/ingest.py`, `storage/paths.py` |
| Privacy controls | Per-provider opt-in (default OFF), denylist, installer/unit wiring | `collector/__main__.py`, `service/units.py`, `install.sh`, `.env.example` |
| Generalised drill-down | Per-app `details[]` + view bar-chart drill-down for all apps | `api/queries.py`, `web/static/app.js` |
| Honesty review + docs | Rewrite limits; update all canonical docs + build plan | `docs/honesty-review.md`, `docs/documentation.md`, `docs/structure.md`, `docs/workflow.md`, `docs/checklist.md`, `docs/plans/activity-tracker-build-plan.md` |
| **Tests** (headless) | Model split, store migration/round-trip, registry, caption policy, MPRIS policy/tracker, browser config, ingest hardening, units flags, queries reconciliation | `tests/detail/`, `tests/model/`, `tests/storage/`, `tests/collector/`, `tests/browser/`, `tests/service/`, `tests/api/` |
| **Tests** (live gates) | KWin caption; caption live attribution; MPRIS live attribution; in-browser drill-down | `tests/focus/test_kwin_live.py`, `tests/detail/…live…`, manual gates |

## Addendum — Step 13.8: dashboard toggle (live, no restart)

Follow-on so the providers can be flipped **from the app itself** rather than via `.env` +
reinstall. A header **⚙ Options** menu (right of the *local-only* badge) toggles Caption / MPRIS.

- **Config file as the runtime source of truth.** `detail/config.py` reads/writes
  `$XDG_CONFIG_HOME/kdence/detail.json` (`{providers, denylist}`), atomically, mirroring
  `categories.json`. When the file exists it is authoritative; when absent the collector falls
  back to its startup flags/env. The installer seeds the file from the env so the menu matches
  from first boot.
- **API.** `GET /api/detail` returns the current toggle state + the available providers/labels;
  `POST /api/detail` validates strictly (unknown provider → 400) and writes only that file.
- **Collector.** A `DetailRuntime` re-reads `detail.json` each interval and reconfigures the
  provider registry on change — connecting/closing the MPRIS D-Bus source as needed — so a toggle
  takes effect within a couple of seconds with no restart. The API and collector are separate
  processes sharing the file (no IPC), consistent with the polling design.
- **View.** The menu renders one switch per provider; a change POSTs and reconciles with the
  server echo. Off by default.

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Detail toggle config | `detail.json` parse/load/save + validation | `src/kdence/detail/config.py`, `storage/paths.py` |
| Detail API | `GET`/`POST /api/detail` (validated + atomic) | `api/server.py`, `api/__main__.py` |
| Live reconfigure | `DetailRuntime` re-reads the file each interval + MPRIS lifecycle | `collector/__main__.py` |
| Options menu | Header ⚙ menu with provider switches | `web/static/{index.html,styles.css,app.js}` |
| Installer seed | Write `detail.json` from the env at install | `service/__main__.py` |
| **Tests** | config; runtime reconfigure (fake MPRIS); `/api/detail` GET/POST | `tests/detail/test_config.py`, `tests/collector/test_detail_runtime.py`, `tests/api/test_detail_api.py` |
