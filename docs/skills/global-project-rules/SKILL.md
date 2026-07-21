---
name: global-project-rules
description: Universal rules every AI agent must read before working in the KDence repository. Covers required reading, environment manager, documentation maintenance, testing expectations, cleanup, and the Definition of Done gate.
---

# Global Project Rules — KDence

Every agent (Claude Code, and any other configured tool) must read this file before making
changes. It is the repository-wide contract.

## What KDence Is

A local, privacy-preserving activity tracker for **KDE Plasma 6 on Wayland** that answers
"how long was I actually working." It detects activity (active vs. idle), detects window
focus (which app), turns those observations into durations, stores them, and serves a
read-back API plus a minimal live view. All data stays on the user's machine.

## Required Reading (before any change)

1. `docs/skills/global-project-rules/SKILL.md` — this file.
2. `docs/documentation.md` — purpose, stack, architecture, decisions, status.
3. `docs/structure.md` — canonical repository layout.
4. `docs/workflow.md` — commands, environment, docs-maintenance, verification.
5. `docs/checklist.md` — active checklist and remaining work.
6. `docs/plans/activity-tracker-build-plan.md` — the authoritative test-driven build order.

Read the relevant canonical skill under `docs/skills/` for the task at hand
(`planner/` for planning, `repository-structure/` for layout).

## Environment Manager

- **Python + `uv` is mandatory.** Python 3.13 (see `.python-version`).
- Install/sync: `uv sync`. Run: `uv run <cmd>`. Add deps: `uv add <pkg>`.
- Add runtime dependencies **per build-plan phase**, not all up front — the build is
  test-driven and each phase pulls in only what it needs.
- Never introduce pip/poetry/conda workflows unless an environment constraint forces it,
  and document the reason if so.

## Architecture Rule (keep the seam clean)

- Pure logic (the time model in `src/timekeeper/model/`) MUST stay separable from
  hardware-dependent code (DBus / KWin / Wayland idle in `activity/` and `focus/`).
- Correctness lives in the pure-logic tests. They run with fake timestamps and need no
  live session — lean on them hardest.

## Documentation Maintenance

Update docs in the same change that makes them stale:

- `docs/structure.md` — whenever directories or key files are added/moved/removed.
- `docs/documentation.md` — on new decisions, stack/dependency changes, or status shifts.
- `docs/workflow.md` — when commands, environment, or verification steps change.
- `docs/checklist.md` — check items off as they complete; add newly discovered work.
- `docs/plans/` — new plans and handoff plans go here; keep the active build plan current.

## Testing & Verification

- Test runner: `pytest` (via `uv run pytest`).
- Every build-plan step ends with a **Review** (read what you built) and a **Test**
  (prove behavior) pass, each with an explicit Pass condition. Do not advance until both
  are met.
- Prefer synthetic/pure-logic tests for correctness; use live tests only for the
  hardware-dependent seams. The keyboard-only idle case (Step 1.1) is the critical live check.
- Lint/format: `ruff check` and `ruff format` (via `uv run`).

## Git Workflow

- Work on a branch; do not commit directly to a shared `main` without reason.
- Commit at the end of each validated phase. **Commit only — do not push** unless the
  user explicitly asks.
- Phase commit wording: `[Plan Name] (Current/Total) Complete: <what was done>`.

## Privacy

- Data is local-only. Do not add network egress, telemetry, or cloud sync.
- Window **titles** can leak document names and URLs; treat the title-capture stance as a
  deliberate, documented decision (see build plan Step 2.2), defaulting to the more
  private option unless the user opts in.

## Cleanup

- Do not leave the only copy of an active skill in a starter directory.
- Remove setup-only helpers and empty generated folders once superseded.
- Record deletions and intentional retentions in `docs/checklist.md`.

## Definition of Done Gate

Setup and any phase are **not** complete until the applicable checklist in
`docs/checklist.md` (and, for initialization, the Definition of Done carried from
`initialize.md`) has been verified item by item. Do not claim completion otherwise.
