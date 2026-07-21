# Application Grouping / Categories — Plan (added scope, "Phase 11")

## 1. Introduction

The dashboard reports **per-application** totals but has no notion of *what kind* of activity
an app represents. This plan adds user-defined **categories** (Work, Entertainment, Social,
Games, …) that apps roll up into, so totals can be seen **by group**, not just by app. It
covers custom categories with colors, an opinionated **auto-categorization** default, and a
grouped table view where category rows expand to their member apps rendered in lighter/darker
variants of the category's color.

Categories are **configuration, not span-derived data**, so they live in their own
`categories.json` (an `app_class → category` map plus category definitions), kept entirely off
the single-writer span store — preserving the reader/writer isolation the store depends on.
The three design forks were confirmed with the user: **live in-dashboard editing** (a small
config write endpoint), **opinionated auto-categorization defaults**, and the **grouped-table +
inline-edit** UI (reusing the browser→site expandable-row pattern).

## 2. Gaps & Unanswered Questions

- **Where config lives / how it's edited.** *Decided:* `$XDG_CONFIG_HOME/timekeeper/
  categories.json` (fallback `~/.config/timekeeper/`), edited live via a new `POST
  /api/categories`. The write path touches only this config file — **never** the span store,
  so span reader/writer isolation is intact. The API stays read-only w.r.t. spans.
- **Initial assignment.** *Decided:* ship a built-in `app_class → category` default map;
  unknown apps fall to a reserved, non-deletable **Uncategorized** (neutral gray). An
  "Auto-categorize" action (re)fills unassigned apps from this map.
- **UI pattern.** *Decided:* a "By app / By group" toggle on the totals table; category rows
  expand to member apps in tint/shade variants; an "Edit groups" mode adds a per-app category
  selector, category creation (name + a 12-swatch palette), and save.
- **Colors / variants.** *Assumption:* a fixed **12-color** starting palette; member-app
  swatches are computed as lightness-stepped **variants** of the category base (pure function,
  deterministic by member index). Categories may also hold a custom hex outside the 12.
- **Charts.** *Assumption for v1:* the distribution/donut charts stay **per-app**; grouping is a
  table feature (matching the request's "extend the per-application totals view"). A future
  "color charts by category" toggle is noted, not built.
- **Grouping granularity.** *Assumption:* **apps only** for v1 (`app_class → category`). Browser
  *sites* keep their existing drill-down; site-level categories are a future extension.
- **Cross-origin write safety.** *Assumption:* the API sends no CORS headers on `/api/categories`,
  so a browser page on another origin cannot preflight a JSON `POST`; the endpoint is loopback
  and validates strictly (hex colors, length/count caps, known shape).

## 3. Hierarchical Step-by-Step Instructions

### Step 1 — Pure grouping core: config + palette + rollup (no hardware, no I/O beyond the config file)
- **Locations:** new `src/timekeeper/grouping/__init__.py`, `grouping/palette.py`
  (12 base colors; `variant(base_hex, index, count) -> hex` lightness stepping; `PALETTE`),
  `grouping/categories.py` (`Category` dataclass, `CategoryConfig`, `UNCATEGORIZED` reserved id,
  `DEFAULT_CATEGORIES`, `DEFAULT_ASSIGNMENTS` app→cat map, `default_config()`,
  `auto_assign(app_classes, config)`, `resolve(app_class, config)`, `validate/normalise`,
  `load(path)`, `save(path, config)` atomic, `default_categories_path()` via a new
  `config_home()` in `storage/paths.py`). Rollup: `GroupTotal` + `group_totals(app_totals,
  categories, assignments)` added to `api/queries.py` (plain inputs, so `queries` stays
  independent of `grouping`). Tests: `tests/grouping/test_palette.py`,
  `tests/grouping/test_categories.py`, and a `group_totals` block in `tests/api/test_queries.py`.
- **Rationale:** correctness (rollup math, auto-assignment, color variants, config validation)
  must be provable headless, like every other pure seam. Keeping `group_totals` in `queries`
  on plain data avoids a `queries ↔ grouping` cycle.
- **Test:** 12 distinct palette colors; `variant` is deterministic and brackets lighter→darker;
  `auto_assign` maps known apps and drops unknowns to Uncategorized; `default_config` has the
  reserved Uncategorized; save/load round-trips atomically; bad colors/shapes are rejected;
  `group_totals` shares sum to 1 and per-group sums reconcile with `per_app_totals`.
- **Action:** verify/validate; commit (no push):
  `Application Grouping (1/4) Complete: pure category config + palette + rollup`.

### Step 2 — API: read + write categories, groups in the summary
- **Locations:** `api/server.py` — add `categories_path` to `_Config`; `GET /api/categories`
  → `{palette, categories, assignments, defaults}`; `POST /api/categories` (new `do_POST`)
  validates via `grouping` and atomically saves; `/api/summary` gains a `groups: [...]`
  roll-up (member apps carry their variant index) beside `apps`. Tests:
  `tests/api/test_categories.py`.
- **Rationale:** the dashboard needs to read the config, roll totals up by it, and persist
  edits. The write endpoint is the first mutation on the API, but it targets the **config
  file only** — the span store stays read-only, so the isolation guarantee holds.
- **Test:** GET returns defaults when no file exists; POST persists and round-trips; malformed
  bodies → 400 without writing; `/api/summary` groups reconcile with `apps` and with the raw
  store; Uncategorized appears only when something is unassigned.
- **Action:** verify/validate; commit:
  `Application Grouping (2/4) Complete: /api/categories read+write + grouped summary rollup`.

### Step 3 — View: grouped table toggle, color variants, inline edit
- **Locations:** `web/static/index.html` (a "By app / By group" toggle on the totals panel +
  an "Edit groups" affordance + a lightweight editor region), `web/static/app.js` (fetch
  `/api/categories`; group-mode render with expandable category rows whose member apps use
  `variant()` colors; edit mode: per-app category `<select>`, create-category with the
  12-swatch picker, "Auto-categorize", and Save → `POST`), `web/static/styles.css` (swatch
  grid, select, category/member row styling on the existing tokens).
- **Rationale:** this is the whole point for the user, and it reuses the exact expandable-row
  mechanics from the browser→site drill-down, so it stays consistent and small.
- **Test:** in-session browser against a seeded store — toggle to group mode shows category
  rows (base color) expanding to member apps in variants; totals reconcile with `/api/summary`
  `groups`; edit mode assigns an app and Save persists (reload shows it); Auto-categorize fills
  from defaults; charts remain per-app and unchanged.
- **Action:** verify/validate in-browser; commit:
  `Application Grouping (3/4) Complete: grouped table view + inline category editor`.

### Step 4 — Docs + regression
- **Locations:** `docs/documentation.md` (component + decision + status), `docs/structure.md`
  (`grouping/` package, `categories.json`, `tests/grouping/`), `docs/workflow.md` (config path,
  `/api/categories`, edit flow), `docs/checklist.md` (Phase 11 steps + any manual note),
  `docs/design-system.md` (grouped-table + color-variant note), and the build plan (Phase 11).
- **Test:** full headless sweep (`pytest -m "not live"`) green; `ruff` clean.
- **Action:** verify/validate; commit:
  `Application Grouping (4/4) Complete: category grouping docs + regression`.

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Palette + variants | 12 base colors + deterministic tint/shade `variant()` | `src/timekeeper/grouping/palette.py` |
| Category config | Definitions + `app→category` map, defaults, auto-assign, validate, atomic load/save | `src/timekeeper/grouping/categories.py` |
| Config path | `config_home()` + `default_categories_path()` | `src/timekeeper/storage/paths.py` |
| Group rollup | `GroupTotal` + `group_totals(...)` (pure) | `src/timekeeper/api/queries.py` |
| Categories API | `GET`/`POST /api/categories` + `groups` in `/api/summary` | `src/timekeeper/api/server.py` |
| Grouped table + editor | Toggle, expandable category rows in variants, inline edit | `web/static/{index.html,app.js,styles.css}` |
| Palette tests | 12 colors distinct; variant brackets lighter→darker | `tests/grouping/test_palette.py` |
| Config tests | Defaults, auto-assign, validation, round-trip | `tests/grouping/test_categories.py` |
| Rollup tests | Group totals reconcile + shares sum to 1 | `tests/api/test_queries.py` |
| API tests | GET defaults, POST persist/validate, summary groups | `tests/api/test_categories.py` |

## 5. Invariants (must hold at every step)

- **Span store stays read-only from the API.** Category edits write `categories.json` only;
  the SQLite span store is never opened for writing by the API.
- **Local-only.** No network egress; config is a local file; the write endpoint is loopback and
  sends no cross-origin CORS headers.
- **Charts unchanged in v1.** Grouping is a table + summary feature; the distribution/donut stay
  per-app so nothing visual regresses.
- **Uncategorized is reserved.** It always exists, cannot be deleted, and catches every
  unassigned app so group totals always reconcile with per-app totals.
