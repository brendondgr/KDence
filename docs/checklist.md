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
- [ ] Confirm proposed stack choices at their phases: SQLite (4.3), FastAPI+Uvicorn (5.1),
  `dbus-fast`/`jeepney` (1/2), live-view approach (6.1).
- [ ] Add the optional `.claude/settings` allowlist / other agent-tool pointers if desired.
- [ ] Execute the build plan starting at **Phase 0** (`docs/plans/activity-tracker-build-plan.md`):
  - [ ] 0.1 Confirm Wayland + Plasma 6.x; record in a notes file.
  - [ ] 0.2 Test scaffold: one passing, one deliberately failing test.
  - [ ] 1.1 Five-minute idle experiment (gate).
  - [ ] 1.2–1.3 Activity monitor + regression.
  - [ ] 2.1 Prove compositor emits focus (gate).
  - [ ] 2.2–2.4 Focus reporter + regression.
  - [ ] 3.1 Merged live line (gate).
  - [ ] 4.1–4.4 Time model → pure-logic tests → storage.
  - [ ] 5.1–5.2 Read-back API.
  - [ ] 6.1–6.2 Live view.
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
