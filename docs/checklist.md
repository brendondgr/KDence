# Checklist — TimeKeeper-v2

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
- [x] `src/timekeeper/` package exists; component subpackages deferred to their phase
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
    `collector --store PATH` + `python -m timekeeper.storage PATH` dump added. **Manual:**
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
  - [x] 6.1 Live view — dark-terminal dashboard under `src/timekeeper/web/`, served by the
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
  - [ ] 7.1–7.2 Session lifecycle + soak.
  - [ ] 8.1–8.3 E2E, full regression, honesty review.

## Deleted / Retained Setup Files (record)

| File/Dir | Action | Reason |
|---|---|---|
| `plan/` | Deleted | Migrated to `docs/skills/planner/`. |
| `repo-structure/` | Deleted | Migrated to `docs/skills/repository-structure/`. |
| `read-yaml.py` | Deleted | Skill-discovery helper; no longer needed post-migration. |
| `activity-tracker-build-plan.md` (root) | Moved | Now `docs/plans/activity-tracker-build-plan.md`. |
| `web/`, `scripts/`, `utils/` (empty) | Deleted | Deferred to their build-plan phase to keep the root lean. |
| `src/timekeeper/*` empty subpackages, `tests/*` empty areas | Deleted | Created per phase alongside real code/tests. |
| `Activity Tracker.dc.html`, `support.js` (root) | Moved | Frontend design comp → `docs/references/frontend/`. |
| `initialize.md` | Retained | Reusable playbook; delete on user confirmation. |
