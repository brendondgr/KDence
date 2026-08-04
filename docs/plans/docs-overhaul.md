# Documentation Overhaul — audit, purge, rewrite

**Mode:** B (no worktree — work directly on `main`). **Commit only, do not push.**

The docs were written incrementally across Phases 0–13 and accumulated three kinds of rot:
claims that were true when written and are not now, setup-era scaffolding that outlived its
purpose, and upstream skill templates that were never about this project. This plan audits
everything, deletes what should not exist, and rewrites the rest against verified ground truth.

## Verified ground truth (measured 2026-08-04, not assumed)

| Fact | Verified value | How |
|---|---|---|
| Headless tests | **315 pass**, 4 deselected | `uv run pytest -m "not live" -q` |
| Total collected | **319** (315 headless + 4 `live`) | `uv run pytest -q --collect-only` |
| Lint | clean | `uv run ruff check` |
| API routes | `GET` `/api/current` `/api/summary` `/api/timeline` `/api/extent` `/api/buckets` `/api/categories` `/api/detail` `/api/health`; `POST` `/api/categories` `/api/detail` | `src/kdence/api/server.py:88-123` |
| Ports | API 5785, ingest 5786 | `.env.example` |
| Screenshot | `docs/images/dashboard.png` exists (122 KB) | `ls` |
| `initialize.md` | **does not exist** | `ls` |
| Runtime dep | `dbus-fast` only | `pyproject.toml` |

## Audit findings

### A. Wrong claims

1. `README.md` — badge and prose say **206 headless tests**; the real number is 315.
2. `README.md` — a "Screenshot placeholder / drop a capture at `docs/images/dashboard.png`"
   note sits directly above the image that already exists.
3. `README.md` Status — stops at "browser activity, application grouping, site categories";
   omits Phase 13 in-app detail, the ⚙ Options menu, hide/restore, and the mobile overhaul.
4. `docs/documentation.md` Current Status — a single ~60-line paragraph that quotes **114**,
   **87**, and **315** test counts in turn, narrating history rather than stating state.
5. `docs/structure.md` — lists `initialize.md` in the tree; the file is gone. Its `docs/plans/`
   listing is missing 7 of the 17 plans that exist.
6. `docs/checklist.md` — the "Deleted / Retained Setup Files" record and two open items still
   treat `initialize.md` as retained.
7. `docs/design-system.md` — written in the imperative future ("the app must **not** load from a
   CDN", "Phase 6 — implement `web/`"); all of it shipped. Also predates the ⚙ Options menu,
   the per-app detail bars, and the mobile breakpoints.
8. `docs/workflow.md` — the commit co-author trailer names `Claude Opus 4.8`.

### B. Setup-era scaffolding that outlived its purpose

9. `docs/skills/planner/SETUP.md` and `docs/skills/repository-structure/SETUP.md` are
   *questionnaires for configuring the skills*. The skills were configured in July 2026; the
   answers are already baked into the SKILL.md files. `planner/SETUP.md` even instructs the
   reader to edit `plan/planner.md` — a directory deleted during initialization. Both are
   exactly what the global rules call "setup-only helpers … once superseded".

### C. Upstream templates that were never about this project

10. `docs/skills/repository-structure/structures/langgraph.md` (110 lines),
    `lab-reports.md` (56 lines), and `web-interfaces.md` (322 lines) — 488 lines of generic
    layout templates for LangGraph agents, lab reports, and full web apps. KDence is none of
    these, and `documentation.md` decision #6 already records the heavier web surface as
    deliberately out of scope. They are dead weight an agent must read past.

### D. Stale skill content

11. `docs/skills/repository-structure/SKILL.md` presents a "Core Directory Structure" with
    `web/`, `utils/`, `scripts/`, and `libs/` at the root — **none of which exist**, and
    `structure.md` explicitly records `scripts/` as superseded and `web/` as in-package. Its
    `src/` listing omits `browser/`, `detail/`, `grouping/`, `service/`, and `web/`; its test
    layout omits 5 of the 10 suites. An agent following it would create the wrong directories.

### D2. Found during execution

12. Five plans under `docs/plans/` carried copy-pasteable commands against the **old** API port
    **8765**, from before the canonical 5785/5786 decision. Harmless as prose, except that
    `phase-8-integration-review.md` holds the cold-start E2E procedure a human is meant to
    *follow* — and `checklist.md` points at it. The port is incidental to every one of those
    plans, so it was corrected in place rather than annotated.

### E. Correct, keep as-is

- `docs/honesty-review.md` — 11 limits, each accurate against current behaviour. Keep.
- `docs/plans/*` (the 17 phase/feature plans) — the historical record of *how* it was built.
  They are dated artefacts, not live claims, and the build plan is still the authoritative
  order. Keep; only ensure `structure.md` lists them all.
- `docs/references/` — the design comp and the vendored Wayland protocol spec. Keep.
- `browser-extension/README.md` — accurate. Keep.

## Steps

Each step ends with a **Validate** gate; do not advance until it passes.

### Step 1 — Purge

`git rm` the 6 files identified in findings B, C, and the stale `docs/images/README.md`
(instructions for producing a screenshot that already exists).

**Validate:** `git status` shows exactly 6 deletions; `grep -rn` across `docs/`, `README.md`,
`.claude/`, `.agents/`, `.cursor/` returns **no** surviving reference to any deleted path.

### Step 2 — Rewrite the canonical docs

- `docs/documentation.md` — purpose, stack, architecture, decisions, status. Collapse the 23
  chronological "Major Decisions" entries into the decisions that still bind, and replace the
  status narrative with a table of measured state.
- `docs/structure.md` — regenerate the tree from the filesystem; drop the "planned homes"
  table for directories that were built or superseded years of phases ago.
- `docs/workflow.md` — keep the command table (it is the most-used doc), correct the
  co-author trailer, and compress the per-phase dependency narrative to the one fact that
  matters: `dbus-fast` is the only runtime dependency.
- `docs/checklist.md` — replace the initialization Definition of Done (met on 2026-07-20) and
  the 60-item per-step ledger with what is actually *open*: the live-hardware gates.
- `docs/design-system.md` — restate in the present tense as the shipped token/panel contract.

**Validate:** every factual claim traceable to the ground-truth table above or to a file that
exists; `uv run pytest -m "not live"` still green (docs-only change, so this is a no-regression
check).

### Step 3 — Rewrite the skill docs and pointers

- `docs/skills/global-project-rules/SKILL.md` — required reading list must name only files
  that exist after Step 1.
- `docs/skills/repository-structure/SKILL.md` — replace the fictional core tree with the real
  one; drop the `structures/` links deleted in Step 1.
- `docs/skills/planner/SKILL.md` + `planner.md` — drop the `SETUP.md` link; keep the format
  reference.
- `.claude/skills/`, `.agents/skills/`, `.cursor/rules/` — pointer files only. Fix the
  KDence / TimeKeeper-v2 naming split in the Cursor rule descriptions.

**Validate:** a script resolves every path referenced by every skill file; zero misses.

### Step 4 — Rewrite the root README

Correct the test badge and count, remove the screenshot placeholder, add the Phase 13 /
mobile work to the feature list and status, and list the real API surface.

**Validate:** every relative link in `README.md` resolves.

### Step 5 — Repo-wide link check, then commit

**Validate:** one script walks every `*.md` in the repo, extracts every relative link and
every backtick-quoted repo path, and asserts each resolves. Then `uv run pytest -m "not live"`
and `uv run ruff check`. Commit on `main`; **do not push**.

## Deliverables

| Path | Action |
|---|---|
| `docs/skills/repository-structure/structures/` (3 files) | **Deleted** — upstream templates, not this project |
| `docs/skills/planner/SETUP.md` | **Deleted** — superseded setup questionnaire |
| `docs/skills/repository-structure/SETUP.md` | **Deleted** — superseded setup questionnaire |
| `docs/images/README.md` | **Deleted** — instructions for an asset that exists |
| `README.md` | Rewritten |
| `docs/documentation.md` | Rewritten |
| `docs/structure.md` | Rewritten |
| `docs/workflow.md` | Rewritten |
| `docs/checklist.md` | Rewritten |
| `docs/design-system.md` | Rewritten |
| `docs/skills/*/SKILL.md`, `planner.md` | Rewritten |
| `.claude/skills/`, `.agents/skills/`, `.cursor/rules/` | Refreshed pointers |
| `docs/plans/*` (5 files) | Stale port 8765 → 5785 in runnable commands (finding 12) |
| `pyproject.toml` | Dependency comment corrected (it still listed FastAPI/Uvicorn as pending) |
| `docs/honesty-review.md`, `docs/references/*` | Unchanged — verified accurate |

Commit: `[Documentation Overhaul] (1/1) Complete: purge stale docs, rewrite canonical + skill docs`
