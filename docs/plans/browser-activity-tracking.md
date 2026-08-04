# Browser Activity Tracking — Plan (added scope, "Phase 10")

## 1. Introduction

KDence already answers *which application* held focus (its `resourceClass`, e.g.
`librewolf`, `firefox`, `brave-browser`, `chromium`) and for how long. This plan adds a
**sub-dimension under browsers only**: *which website* was in the active tab while that
browser was focused and the user was active. The goal is end-of-day summaries that can tell
work from non-work browsing without changing what the charts show.

The design decision that shapes everything (confirmed with the user): a browser stays a
**single entity** in the Activity-distribution bars and the Application-share donut. The
site breakdown appears **only** as an expandable drill-down inside the *Per-application
totals* table — expand the `librewolf` row and you see the hosts you visited under it, with
active time and share, over the selected window.

Getting the active tab's URL is impossible from the compositor on Wayland, so the source is
a small **WebExtension** (one Gecko packaging for LibreWolf/Firefox, one Chromium packaging
for Brave/Chromium) that reads the active tab and POSTs **only its hostname** to a
**loopback-only** ingest endpoint the collector owns. No path, query, or fragment ever
leaves the browser; nothing leaves the machine (127.0.0.1 only) — the local-only privacy
rule is preserved. Hostnames that resolve to the local machine (loopback, RFC1918 private
ranges, link-local, `.local`) collapse to one generic `"(local app)"` bucket, per the
user's requirement that private/local work is never logged by name.

## 2. Gaps & Unanswered Questions

- **URL source.** *Decided:* WebExtension → loopback POST. Window-title scraping cannot see
  the URL and titles are privacy-off by default, so it can't satisfy the localhost rule.
- **Granularity.** *Decided:* **hostname only** (e.g. `github.com`), `www.` stripped,
  lowercased. Paths/queries stay out of the store.
- **Where the privacy classification runs.** *Assumption:* the extension sends the raw
  hostname + scheme to loopback; the **pure Python** `site` policy classifies (local →
  generic, else normalized host). This keeps the localhost/private-IP logic unit-testable in
  the repo's Python idiom rather than hidden in JS, and the hostname only ever transits
  127.0.0.1.
- **Which browser a tab report belongs to.** *Assumption:* the extension tags each POST with
  a browser token; the tracker keys the latest active tab by token with a short TTL, and the
  collector attributes a site **only** when the currently focused `app_class` is a known
  browser class and its report is fresh. Two browsers open at once each keep their own entry.
- **Storing the site.** *Assumption:* a new nullable `site` column on `spans` (a dedicated
  sub-identity), **not** overloading the sensitive, opt-in `title` field — `site` has its own
  privacy policy and is on by default for browsers only.
- **Extension distribution / signing.** *Human intervention needed at the live gate:* the
  user loads the unpacked extension (LibreWolf/Firefox: temporary or unsigned via
  `xpinstall.signatures.required=false`; Chromium/Brave: Load unpacked in dev mode). This
  plan ships the extension source + a README; it does not publish to any store (that would be
  egress and out of scope).
- **New loopback port.** *Assumption:* the ingest listener binds `127.0.0.1:8766` (the API
  view stays on 5785). Configurable via `--ingest-port` / `--no-ingest`.

## 3. Hierarchical Step-by-Step Instructions

### Step 1 — Pure site-identity policy + browser-tab tracker (no hardware)
- **Locations:** new `src/kdence/browser/__init__.py`, `browser/site.py`
  (`normalize_site(hostname, scheme) -> str | None`, `LOCAL_APP` sentinel, `is_local_host`),
  `browser/tracker.py` (`BrowserTabTracker` with `report(browser, site, at)` /
  `site_for(app_class, now)`, `BROWSER_CLASSES` map of family-token → `resourceClass` set,
  `ttl_seconds`). Tests: `tests/browser/__init__.py`, `test_site.py`, `test_tracker.py`.
- **Rationale:** this is where the correctness of "what counts as a site" and "when is a
  report still valid" lives; it must be provable with zero hardware, like every other pure
  seam in the repo. Building it first means Steps 2–3 wire a *tested* policy.
- **Test:** loopback/`127.0.0.1`/`::1`, RFC1918 (`10.`, `172.16–31.`, `192.168.`),
  link-local `169.254.`, `.local`, and `file:`/`about:` → `LOCAL_APP` or `None`; normal hosts
  normalize (`www.` stripped, lowercased); tracker returns a site only for a known browser
  class within TTL, `None` when stale, for non-browsers, or when unset.
- **Action:** verify/validate this phase. Once green, commit (no push):
  `Browser Activity Tracking (1/6) Complete: pure site-identity policy + browser-tab tracker`.

### Step 2 — Thread a `site` sub-identity through the time model + span store
- **Locations:** `model/timeline.py` (`Span`/`OpenSpan` gain `site`; `active(...)` takes
  `site`; same-window test includes `site`; callbacks carry it), `storage/store.py`
  (`_SCHEMA` + additive migration `ALTER TABLE spans ADD COLUMN site`, guarded by a
  `PRAGMA table_info` check; `SpanRow.site`; insert/read include it), `storage/reader.py`
  (`_COLUMNS` + `_row` include `site`). Tests: extend `tests/model/test_timeline.py`,
  `tests/storage/test_store.py`.
- **Rationale:** the site must ride with the span so read-back can group by `(app_class,
  site)`. A site change within the same browser must open a new, contiguous span — exactly
  the existing window-switch rule, now keyed on one more field. The migration keeps existing
  databases (months of history) intact.
- **Test:** a span carrying a site round-trips; changing only the site closes and reopens a
  contiguous span; `site=None` spans behave exactly as before; opening an old DB with no
  `site` column adds it and reads back `NULL`.
- **Action:** verify/validate; re-run `tests/model` + `tests/storage`. Commit:
  `Browser Activity Tracking (2/6) Complete: site sub-identity in the time model + migrated span store`.

### Step 3 — Merge rule + loopback tab-ingest + collector wiring
- **Locations:** `collector/merge.py` (`MergedSample.site`; `merge(state, identity,
  site=None)` attaches the site only while active), new `browser/ingest.py` (a
  `ThreadingHTTPServer` bound to `127.0.0.1`, `POST /tab` → `tracker.report(...)` after
  `normalize_site`, `GET /health`; loopback-only, tiny), `collector/__main__.py` (start the
  ingest server on a daemon thread, resolve `site` from the tracker each interval keyed on
  `reporter.current.app_class`, pass it into `merge` and `timeline.active`; add
  `--ingest-port` / `--no-ingest`). Tests: extend `tests/collector/test_merge.py`; new
  `tests/browser/test_ingest.py`.
- **Rationale:** the browser reporter is a writer-side concern (it changes what gets stored),
  so it belongs with the collector, mirroring the activity/focus IO-vs-logic seam. A site is
  only ever attached to a browser that is *both* focused and active.
- **Test:** merge attaches a site only when active and only when passed one; a POST to the
  ingest server lands in the tracker (headless localhost); a non-browser focus yields no
  site; malformed POSTs are rejected without crashing.
- **Action:** verify/validate. Commit:
  `Browser Activity Tracking (3/6) Complete: loopback tab-ingest + collector attaches site to browser spans`.

### Step 4 — Read-back: per-browser site breakdown in `/api/summary`
- **Locations:** `api/queries.py` (`per_app_totals` unchanged for the charts; add
  `site_totals(spans, window)` or nest a `sites: list[{site, seconds, sessions}]` on the
  browser entries of the summary payload — populated only for browser `app_class`es with
  stored sites), `api/server.py` (serialize the nested breakdown; charts’ per-app totals byte-
  identical to before). Tests: extend `tests/api/test_queries.py`, `tests/api/test_server*.py`.
- **Rationale:** the drill-down data must reconcile with the raw spans exactly like every
  other endpoint (Step 5.1 discipline). Keeping `per_app_totals` untouched guarantees the
  charts don't shift.
- **Test:** a browser entry lists its hosts with seconds/sessions that sum to the browser's
  own total and reconcile with the raw store; non-browser apps carry no sites; the
  distribution/donut totals are unchanged from before this step.
- **Action:** verify/validate. Commit:
  `Browser Activity Tracking (4/6) Complete: /api/summary nests per-browser site totals`.

### Step 5 — View: expandable browser rows in the totals table
- **Locations:** `web/static/index.html` (row markup supports a nested site sub-list),
  `web/static/app.js` (`renderTable` marks browser rows expandable, toggles a per-site
  sub-list on click; charts untouched), `web/static/styles.css` (disclosure caret + indented
  `.site-row` styling on the existing tokens).
- **Rationale:** this is the only place the site dimension surfaces in the UI, exactly as the
  user specified — the charts stay per-application.
- **Test:** in-session browser check against a seeded store: a browser row expands to show
  its hosts with active time/share; a non-browser row has no caret; the distribution and
  donut are unchanged; the site times reconcile with `/api/summary`.
- **Action:** verify/validate in the in-app browser. Commit:
  `Browser Activity Tracking (5/6) Complete: expandable per-browser site drill-down in the table`.

### Step 6 — The cross-browser WebExtension + docs + install steps
- **Locations:** new top-level `browser-extension/` (`shared/tab-reporter.js` the common
  logic; `gecko/manifest.json` MV2/MV3 for LibreWolf/Firefox; `chromium/manifest.json` MV3
  for Brave/Chromium; `README.md` with per-browser load steps). Host permission restricted to
  `http://127.0.0.1:8766/*`. Reads the active tab via `tabs.onActivated`/`onUpdated` +
  `windows.onFocusChanged`, POSTs `{browser, hostname, scheme}` (hostname only). Docs:
  `documentation.md` (new decision + component), `structure.md` (new dirs/files),
  `workflow.md` (ports, `--ingest-port`, extension load steps, migration note), `checklist.md`
  (new live gate), `honesty-review.md` (browser-presence ≠ reading; localhost generalization),
  `design-system.md` (table drill-down note), and the build plan's Phase 10 entry.
- **Rationale:** the extension is the hardware-equivalent live seam here; like the KWin/idle
  gates it can only be *proven* in a real browser session. Everything downstream was built and
  tested against the ingest contract without it.
- **Test:** headless — the manifests parse as JSON and declare only the loopback host
  permission. Live gate (human) — load the extension in one Gecko + one Chromium browser,
  browse two sites + a `localhost` app, confirm the collector stores the two hosts and the
  generic `(local app)` bucket and the drill-down shows them.
- **Action:** verify/validate; run the full headless sweep (`pytest -m "not live"`). Commit:
  `Browser Activity Tracking (6/6) Complete: cross-browser WebExtension tab-reporter + docs`.

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Site-identity policy | Hostname → normalized site / generic local bucket | `src/kdence/browser/site.py` |
| Browser-tab tracker | Latest active tab per browser, TTL, focus-gated | `src/kdence/browser/tracker.py` |
| Loopback tab-ingest | 127.0.0.1 `POST /tab` receiver feeding the tracker | `src/kdence/browser/ingest.py` |
| Site column | `spans.site` + model/store/reader threading + migration | `model/timeline.py`, `storage/store.py`, `storage/reader.py` |
| Merge + collector wiring | Attach site to focused-browser active spans | `collector/merge.py`, `collector/__main__.py` |
| Site read-back | Nested per-browser host totals in `/api/summary` | `api/queries.py`, `api/server.py` |
| Table drill-down | Expandable browser rows (charts unchanged) | `web/static/{index.html,app.js,styles.css}` |
| WebExtension | Gecko + Chromium tab-reporter (hostname → loopback) | `browser-extension/` |
| Site policy tests | Local/private/public host classification | `tests/browser/test_site.py` |
| Tracker tests | Freshness/TTL + browser-class gating | `tests/browser/test_tracker.py` |
| Ingest tests | Loopback POST → tracker, malformed input | `tests/browser/test_ingest.py` |
| Model/store/API test deltas | Site round-trip, migration, reconciliation | `tests/model`, `tests/storage`, `tests/api` |

## 5. Privacy invariants (must hold at every step)

- **Loopback only.** The ingest listener binds `127.0.0.1`; the extension's host permission is
  `http://127.0.0.1:8766/*`. No external egress anywhere.
- **Hostname only.** Paths, queries, and fragments never leave the browser and are never
  stored.
- **Local stays private.** Loopback / RFC1918 / link-local / `.local` → one generic
  `(local app)` bucket; the specific local hostname is never stored.
- **Titles untouched.** The `title` opt-in and its default-off stance are unchanged; `site`
  is a separate dimension with its own (browser-only) policy.
