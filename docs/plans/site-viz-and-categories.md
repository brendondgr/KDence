# Site visualization + site-level categories — Plan (added scope, "Phase 12")

## 1. Introduction

Two enhancements to the browser drill-down, both requested by the user:

1. **Mini bar chart in the drill-down.** Replace the browser per-site text rows with a compact
   horizontal **bar chart** (each site a proportional, coloured bar with its host + time), so
   the breakdown reads at a glance. Client-only — the data (`sites[]`) is already served.
2. **Roll browser sites into categories.** Let categories assign **hostnames** (e.g.
   `youtube.com → Entertainment`), not just applications. In *By group* mode a browser's time
   then **splits across categories by site**; unassigned sites fall back to the browser's own
   category, so totals still reconcile exactly.

Categories remain configuration in `categories.json` (off the span store); this adds a parallel
`site_assignments` map beside `assignments`.

## 2. Gaps & Unanswered Questions

- **Bar chart vs. sparkline.** *Decided:* a mini **bar chart** — a per-site sparkline would need
  per-site *time-series* buckets the API doesn't serve; a share-proportional bar chart uses the
  existing `sites[]` totals and answers "how much on each" directly.
- **Unassigned site fallback.** *Assumption:* a browser site with no explicit category rolls up
  under the **browser app's** category (so today's behaviour — whole browser under one
  category — is preserved when no sites are assigned). Un-sited browser time (`site=None`) does
  the same.
- **Reconciliation.** `per_app_site_totals` already sums each browser's sites (incl. the
  `None` bucket) to the browser's own total, so splitting by site accounts for every second
  exactly once — group totals still equal the active total.
- **Opinionated site seed.** *Assumption:* a modest `DEFAULT_SITE_ASSIGNMENTS` (youtube →
  Entertainment, github/stackoverflow → Work, reddit/x → Social, …) powers "Auto-categorize"
  for sites, mirroring the app seed. Browsers themselves stay unseeded.
- **Charts.** Still per-app in v1 (unchanged).

## 3. Hierarchical Step-by-Step Instructions

### Step 1 — Mini bar-chart drill-down (client-only)
- **Locations:** `web/static/app.js` (a shared `barRows(items)` renderer; use it for the
  browser per-site drill-down in *by-app* mode), `web/static/styles.css` (bar-chart row styling).
- **Rationale:** the site breakdown is already served; this is a presentation change that also
  gives a reusable renderer for the group-mode members in Step 3.
- **Test:** in-browser — a browser row expands to a compact bar chart (bars ∝ share, host +
  time labels); totals still match `/api/summary`; non-browser rows unchanged.
- **Action:** verify in-browser; commit: `Site Viz + Categories (1/4) Complete: mini bar-chart browser drill-down`.

### Step 2 — Site-category config + site-aware rollup (pure)
- **Locations:** `grouping/categories.py` (`CategoryConfig.site_assignments`, `resolve_site`,
  `DEFAULT_SITE_ASSIGNMENTS`, and `default_config`/`parse`/`to_dict` updated), `api/queries.py`
  (`group_totals(app_totals, config, site_totals=None)` — split a browser's time across
  categories by site; `GroupMember` gains `site`/`browser`). Tests: `tests/grouping`,
  `tests/api/test_queries.py`.
- **Rationale:** correctness of the split + reconciliation is pure and must be proven headless.
  Default `site_totals=None` keeps the old 2-arg behaviour (backward compatible).
- **Test:** `resolve_site`; site-assignment validation/round-trip; `group_totals` splits a
  browser across categories, unassigned sites fall back to the browser's category, and per-group
  sums still reconcile with the active total.
- **Action:** verify/validate; commit: `Site Viz + Categories (2/4) Complete: site_assignments + site-aware group rollup`.

### Step 3 — API + editor + group display
- **Locations:** `api/server.py` (`_summary` passes the site breakdown into `group_totals`;
  `_categories_payload` adds `site_assignments` + `site_defaults`), `web/static/app.js` (editor
  gains a **Browser sites** assignment section; Auto-categorize fills sites; group-mode members
  render via `barRows`, showing site members with a small browser tag), `web/static/styles.css`.
  Tests: `tests/api/test_categories.py`.
- **Rationale:** wire the pure rollup to the live config + UI; reuse the Step 1 renderer.
- **Test:** in-browser — assign `youtube.com → Entertainment`, Save; the browser's YouTube time
  moves under Entertainment while its other sites stay put; totals reconcile. Headless: payload
  round-trips `site_assignments`; grouped summary reflects a site assignment.
- **Action:** verify/validate; commit: `Site Viz + Categories (3/4) Complete: site-category API + editor + group display`.

### Step 4 — Docs + regression
- **Locations:** `documentation.md`, `structure.md`, `workflow.md`, `checklist.md`,
  `design-system.md`, build plan (Phase 12).
- **Test:** full headless sweep (`pytest -m "not live"`) green; `ruff` clean.
- **Action:** commit: `Site Viz + Categories (4/4) Complete: docs + regression`.

## 4. Invariants
- Group totals always reconcile with the active total (every browser-second lands in exactly
  one category via its site, its browser's category, or Uncategorized).
- Config writes touch only `categories.json`; the span store stays read-only.
- Charts unchanged; by-app mode unchanged except the drill-down's visual.
