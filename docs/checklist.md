# Checklist — KDence

## Initialization — Definition of Done

Carried from `initialize.md`. Verified during setup on 2026-07-20.

### Intake
- [x] Project goal, runtime, deliverables, target user, supported tool, and validation
  workflow are known (from `docs/plans/activity-tracker-build-plan.md`).
- [x] Ambiguous defaults recorded as explicit decisions in `docs/documentation.md`
  (storage, API, DBus lib, live-view = proposed, confirmed per phase).
- [x] Web-architecture questions: N/A by decision — the live view is a minimal local
  surface; the heavier web skills are not present in this repo and are out of scope.

### Canonical Docs
- [x] `docs/` exists.
- [x] `docs/documentation.md`
- [x] `docs/structure.md`
- [x] `docs/workflow.md`
- [x] `docs/checklist.md`
- [x] `docs/plans/` exists (holds the build plan).
- [x] `docs/skills/` exists.
- [x] `docs/skills/global-project-rules/SKILL.md` names required reading.
- [x] Every selected skill has a canonical folder: `planner/`, `repository-structure/`.
- [x] Supporting files preserved: `planner.md`, both `SETUP.md`, `structures/`.

### Agent Pointers
- [x] Claude Code pointers under `.claude/skills/`.
- [x] OpenAI Codex pointers under `.agents/skills/`.
- [x] Cursor rules under `.cursor/rules/` (`*.mdc`; global rule `alwaysApply: true`).
- [x] Each pointer/rule has valid frontmatter for its tool.
- [x] Each references `docs/skills/global-project-rules/SKILL.md` and its canonical skill.
- [x] No agent folder holds the only copy of important instructions.

### Project Structure
- [x] Lean root: only `docs/`, `src/`, `tests/` as visible top-level folders.
- [x] `src/kdence/` package exists; component subpackages deferred to their phase
  (documented in `docs/structure.md`).
- [x] Phase-specific dirs (`web/`, `scripts/`, `utils/`) intentionally deferred, not
  pre-scaffolded empty.
- [x] Frontend design comp stored under `docs/references/frontend/` (reference only).
- [x] Runtime/config files exist: `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`.
- [x] `README.md` points to the canonical docs.

### Cleanup
- [x] Starter skill dirs `plan/` and `repo-structure/` deleted after migration to `docs/skills/`.
- [x] `read-yaml.py` deleted (discovery helper, no longer needed; skills are migrated).
- [x] `activity-tracker-build-plan.md` moved from root into `docs/plans/`.
- [ ] `initialize.md` — **intentionally retained** pending user confirmation to delete.
  It is a reusable playbook; remove once the user agrees setup is final.
- [x] No duplicate competing sources of truth remain.

### Verification
- [x] Final tree inspected after cleanup.
- [x] Generated canonical docs opened and checked.
- [x] Representative pointer files checked; all pointer targets exist.
- [x] `uv sync` succeeds and `uv run pytest` runs green (scaffold sanity test).
- [x] Remaining gaps listed below.

## Remaining Follow-up Work

- [ ] **Confirm deletion of `initialize.md`** (currently retained).
- [x] Confirm proposed stack choices at their phases: ~~SQLite (4.3)~~ **adopted**,
  ~~FastAPI+Uvicorn (5.1)~~ **stdlib `http.server` adopted instead**, ~~live-view approach
  (6.1)~~ **vendored ECharts + static view served by the API, adopted**.
  *(Idle source decided in Phase 1: stdlib Wayland wire client, no dep. Focus access decided
  in Phase 2: KWin script + **`dbus-fast`** receiver — adopted, the first runtime dependency.
  Storage decided in Phase 4: stdlib `sqlite3`, single-writer, WAL — **adopted, no new
  dependency**. Read-back API decided in Phase 5: stdlib `http.server` `ThreadingHTTPServer`
  over FastAPI — **adopted, no new dependency**. Live view decided in Phase 6: ECharts 5.5.0
  + JetBrains Mono **vendored locally** (no CDN/egress), static assets served by the API —
  **adopted, no new Python dependency**.)*
- [ ] Add the optional `.claude/settings` allowlist / other agent-tool pointers if desired.
- [ ] Execute the build plan (`docs/plans/activity-tracker-build-plan.md`):
  - [x] 0.1 Confirm Wayland + Plasma 6.x; recorded in `docs/plans/phase-0-platform-notes.md`.
  - [x] 0.2 Test scaffold: red/green both proven; headless suite green.
  - [x] 1.1 Five-minute idle experiment (gate) — harness built; automated `idled` verified.
    **Manual:** keyboard-only vs mouse-only `resumed` reset (needs a human).
  - [x] 1.2 Activity monitor: synthetic tests pass; live smoke test passes.
  - [x] 1.3 Regression checkpoint — full headless suite green, lint/format clean.
  - [x] 2.1 Prove compositor emits focus (gate) — KWin script + `callDBus` proven live;
    real focused window and a focus *change* reported outside the compositor. Facts in
    `docs/plans/phase-0-platform-notes.md`.
  - [x] 2.2 Window identity + title-privacy: app class always, **titles opt-in (default off)**;
    synthetic tests green.
  - [x] 2.3 Focus reporter: pure tracker (change-deduped) + live KWin source; synthetic + live
    tests green. Edge cases (desktop, empty title) covered.
  - [x] 2.4 Regression checkpoint — Phase 1 tests still green with focus present (30 headless).
    **Manual:** two-app focus switching changes the identity (needs a human).
  - [x] 3.1 Merged live line (gate) — one process prints `app — active` / `— idle`; verified
    the line tracked the app then flipped to idle after the threshold. **Manual:** app-switch
    tracking and keyboard return-to-active.
  - [x] 4.1 Model on paper — stitched heartbeats; the four rules (end-boundary/back-dating,
    local-day + midnight split in the read layer, suspend-gap, open-span-on-crash) written up
    in `docs/plans/phase-4-time-model-and-storage.md`.
  - [x] 4.2 Pure time-model suite (**the critical one**) — `model/Timeline`; the four named
    cases (a continuous, b back-dated walk-away, c contiguous app-switching, d suspend gap)
    plus edges all assert; headless.
  - [x] 4.3 Datastore under the model — single-writer SQLite (`storage/Store`, WAL, stdlib
    `sqlite3`). Persistence + crash-recovery (no invented hours) proven headless;
    `collector --store PATH` + `python -m kdence.storage PATH` dump added. **Manual:**
    live "run a few minutes, dump, spans match" + a hard-kill crash-recovery eyeball.
  - [x] 4.4 Regression checkpoint — Phases 1–3 + 4.2 all green (48 headless + 3 live), lint/
    format clean.
  - [x] 5.1 Query layer — pure `api/queries.py` (active total, per-app totals/share/sessions,
    timeline, current-state, local TODAY/WEEK/MONTH windowing) served by a thin stdlib
    `http.server` (`ThreadingHTTPServer`, 127.0.0.1). Reads isolated via read-only
    (`mode=ro`) connections (`storage/reader.py`). Endpoint numbers reconcile with the raw
    store; concurrent read/write stays clean — proven headless in `tests/api`.
  - [x] 5.2 Boundary tests — empty day → zeros (no crash); single open span → active,
    counted to `now`; span across local midnight splits per the Phase 4.1 day rule. Headless.
  - [x] 6.1 Live view — dark-terminal dashboard under `src/kdence/web/`, served by the
    API at `/` (new traversal-safe static route). Polls `/api/current` + `/api/summary` +
    `/api/timeline` every ~2s; charts are **vendored ECharts 5.5.0** (no CDN), font
    JetBrains Mono vendored; timeline spans bucketed client-side (no API change). Counters
    tick locally and **freeze when idle**. Verified in-session against a seeded store and the
    live collector (real active `brave-browser` session; per-app table reconciled with the
    store). Static-route/traversal tests headless-green. **Manual:** watch it track reality
    while you work/switch/walk-away.
  - [x] 6.2 Resilience — failed fetches flip to an "offline · retrying" badge, freeze the
    counters, and keep polling; recovers when the API/collector returns. **Manual:** restart
    the collector with the view open and confirm it recovers rather than wedging.
  - [x] 7.1 Session lifecycle — pure systemd **user**-unit renderers (`service/units.py`) +
    `install`/`uninstall`/`print` CLI (`python -m kdence.service`). Units bind
    `graphical-session.target` (after DBus/compositor), `Restart=on-failure` with a start-rate
    backoff, `ExecStart` uses the venv interpreter, and pass an **explicit** durable
    `--store %h/.local/share/kdence/kdence.db` (not `/tmp`; the collector default is unchanged —
    Phase 9 still owns the persistent-*default* work). API unit binds `127.0.0.1` only. Unit
    *content* asserted headless in `tests/service/test_units.py`. **Manual gate (needs a human):**
    `install`, enable both units, **log out and back in** → both start and data resumes with no
    manual steps; `systemctl --user kill kdence-collector.service` → it restarts.
  - [x] 7.2 Long-run soak — pure resource summary (`service/soak.py`: RSS least-squares slope +
    `flat` verdict) with a stdlib sampler (`… service soak`). Flat-vs-climbing verdicts asserted
    headless in `tests/service/test_soak.py`. **Manual gate:** leave both units running a full
    working day; at day's end the RSS slope is flat and the API totals pass your smell test of
    the day; a suspend/resume mid-day leaves spans intact (the Phase 4.1 suspend-gap rule).
  - [x] 8.2 Full regression sweep — **87 hardware-free tests green in one pass**
    (`uv run pytest -m "not live"`): activity 13, focus 12, collector 4, model 11, storage 7,
    api 24, service 15, + scaffold. `ruff check` / `ruff format --check` clean. Live-marked
    tests (3) are human-run: the focus live test needs the systemd collector **stopped**
    (`systemctl --user stop kdence-collector` — it owns the `org.kdence.Focus` name by
    design), and the idle live test needs genuine no-input.
  - [x] 8.3 Honesty review — `docs/honesty-review.md`: what the tracker measures (focused-window
    active time / presence) vs. does not (engagement/productivity), with 7 known limits each
    tagged *accepted* or *future*. Linked from `docs/documentation.md`.
  - [ ] 8.1 Cold-start E2E — **manual gate (human + stopwatch):** clean store, work ~2 min each
    in three apps, walk away > 5 min, return; `curl -s '127.0.0.1:8765/api/summary?range=today'`
    totals must match the stopwatch within one poll interval per app and exclude the away time.
    Procedure in `docs/plans/phase-8-integration-review.md`.
  - [ ] **Phase 7 live gates (carried):** install/enable done ✓ and the live stack verified up
    (collector + API active, real session tracked, durable store on disk) — but **logout/login
    survival**, **kill→restart**, and the **full-day soak** still need a human.
  - [x] 9.1 Persistent XDG store path — `storage/paths.py` `default_store_path()` →
    `$XDG_DATA_HOME/kdence/kdence.db` (creates the parent dir). Collector/API default there;
    collector gains `--no-store` for the Phase 3 print-only mode. `tests/storage/test_paths.py`.
    **Resolves the urgent `/tmp` (tmpfs/RAM) data-loss trap** — the Phase 7 units already pass
    this same durable path, and the archive now survives reboots by default.
  - [x] 9.2 Arbitrary date ranges (pure) — `range_window(anchor=…)` + `day`/`year`,
    `custom_window`, `local_date_to_timestamp`, `bucket_series` (calendar-aligned) +
    `auto_granularity`. Bucket totals reconcile with `active_seconds`/`per_app_totals`.
    `tests/api/test_queries_navigation.py`.
  - [x] 9.3 Date-aware API + view — `/api/summary`&`/api/timeline` take `range`/`date`/`start`/
    `end`; new `/api/extent` (via `SpanReader.extent()`) and `/api/buckets`. View gains a
    Day/Week/Month/Year/Custom selector, prev/next steppers, a date picker bounded by the extent,
    and a NOW button; charts read server buckets so a year view never ships every span.
    Headless: `tests/api/test_server_navigation.py`. **In-session browser check (done):** live
    today, month prev/next, year (weekly buckets), a jumped historical day (hourly + focus band),
    and a custom Feb→Apr range whose 157h30m total reconciled with the API. **Manual gate:** the
    interactive multi-month scrub against your own real archive over time.
  - [x] 10.1 Site policy + tracker — pure `browser/site.py` (`normalize_site`: local/private →
    `(local app)`, public host normalised) + `browser/tracker.py` (focus-gated latest-tab-per-
    engine, TTL). Headless: `tests/browser/test_site.py`, `test_tracker.py`.
  - [x] 10.2 Site sub-identity in model + store — `Span/OpenSpan.site`, same-window split on a
    site change; `spans.site` column with an **additive, idempotent migration** (a legacy DB is
    upgraded in place, history preserved). Reader adapts to a not-yet-migrated store. Headless:
    `tests/model` + `tests/storage` deltas.
  - [x] 10.3 Merge + loopback ingest + read-back — `merge(state, identity, site)`; `browser/
    ingest.py` (127.0.0.1-only `POST /tab`, refuses non-loopback binds); collector runs it
    (`--ingest-port`/`--no-ingest`) and attributes the focused browser's site. `/api/summary`
    nests per-browser `sites[]` that reconcile with the raw spans; charts unchanged. Headless:
    `tests/browser/test_ingest.py`, `tests/collector/test_merge.py`, `tests/api/test_queries.py`.
  - [x] 10.4 Table drill-down + WebExtension — browser rows expand to a per-host breakdown
    (charts untouched); verified in-browser against a seeded store (LibreWolf/Brave expand and
    reconcile with `/api/summary`; expansion survives the 2s poll; non-browsers inert).
    `browser-extension/` ships MV2 (gecko) + MV3 (chromium) builds sending **hostname only** to
    loopback; manifest privacy invariants asserted headless (`tests/browser/test_extension_manifests.py`).
    **Manual gate (needs a human):** load the extension in one Gecko + one Chromium browser,
    browse two sites + a `localhost` app, and confirm the drill-down shows the two hosts + one
    `(local app)` bucket.
  - [x] 11.1 Pure grouping core — `grouping/palette.py` (12-colour palette + `variant()`
    member shades) + `grouping/categories.py` (Category config, reserved Uncategorized,
    opinionated `DEFAULT_ASSIGNMENTS`, `auto_assign`/`resolve`, strict `parse` + resilient
    `load` + atomic `save`) + `storage/paths.py` config path. Rollup `group_totals` in
    `api/queries.py` reconciles with per-app totals. Headless: `tests/grouping/*`,
    `tests/api/test_queries.py`.
  - [x] 11.2 Categories API + grouped summary — `GET`/`POST /api/categories` (validate +
    atomic save; the span store stays read-only), `groups[]` on `/api/summary`. `--categories`
    flag on the API. Headless: `tests/api/test_categories.py`.
  - [x] 11.3 Grouped table view + editor — By app / By group toggle; category rows expand to
    member apps in colour variants; inline editor (create/assign/delete/auto-categorize/save).
    **In-session browser check (done):** group rollup + member variants, reassignment persisted
    to `categories.json` and re-rolled, by-app mode + charts unchanged. Charts stay per-app in
    v1 (no manual gate).

## Deleted / Retained Setup Files (record)

| File/Dir | Action | Reason |
|---|---|---|
| `plan/` | Deleted | Migrated to `docs/skills/planner/`. |
| `repo-structure/` | Deleted | Migrated to `docs/skills/repository-structure/`. |
| `read-yaml.py` | Deleted | Skill-discovery helper; no longer needed post-migration. |
| `activity-tracker-build-plan.md` (root) | Moved | Now `docs/plans/activity-tracker-build-plan.md`. |
| `web/`, `scripts/`, `utils/` (empty) | Deleted | Deferred to their build-plan phase to keep the root lean. |
| `src/kdence/*` empty subpackages, `tests/*` empty areas | Deleted | Created per phase alongside real code/tests. |
| `Activity Tracker.dc.html`, `support.js` (root) | Moved | Frontend design comp → `docs/references/frontend/`. |
| `initialize.md` | Retained | Reusable playbook; delete on user confirmation. |
