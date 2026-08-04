---
name: global-project-rules
description: Universal rules every AI agent must read before working in the KDence repository. Covers required reading, the uv environment, the pure/hardware seam, privacy, testing, documentation maintenance, git, and the Definition of Done gate.
---

# Global Project Rules — KDence

The repository-wide contract. Every agent reads this before making changes.

## What KDence is

A local, privacy-preserving activity tracker for **KDE Plasma 6 on Wayland** that answers "how
long was I actually working, and in what." It detects activity (active vs. idle) and window
focus (which app), optionally resolves in-app detail (document / media / browser hostname),
turns those observations into honest durations, stores them in SQLite, and serves a read-back
API plus a live dashboard. **All data stays on the machine.**

## Required reading (before any change)

1. This file.
2. [`docs/documentation.md`](../../documentation.md) — purpose, stack, architecture, the
   decisions that still bind, current measured state.
3. [`docs/structure.md`](../../structure.md) — the canonical repository layout.
4. [`docs/workflow.md`](../../workflow.md) — commands, environment, API surface, verification, git.
5. [`docs/checklist.md`](../../checklist.md) — what is actually still open.
6. [`docs/honesty-review.md`](../../honesty-review.md) — what the numbers do and do not mean.

Then read the canonical skill for the task at hand:
[`planner/`](../planner/SKILL.md) for planning,
[`repository-structure/`](../repository-structure/SKILL.md) for layout.

The build history — how each phase was planned and closed — is in
[`docs/plans/`](../../plans/), starting with
[`activity-tracker-build-plan.md`](../../plans/activity-tracker-build-plan.md). Read a plan
when you need the *rationale* behind something; read the canonical docs above for what is
*true now*.

## The five rules that matter most

### 1. Environment: Python + `uv`, no exceptions

Python 3.13 (`.python-version`). `uv sync` to install, `uv run <cmd>` to run, `uv add <pkg>` to
add. Never introduce pip/poetry/conda workflows unless an environment constraint forces it —
and document the reason if it does.

### 2. Keep the seam clean

Pure logic (`model/`, and the pure halves of `activity/`, `focus/`, `detail/`, `browser/`,
`grouping/`, `service/`) **must** stay separable from hardware-dependent code (DBus / KWin /
Wayland idle / MPRIS). Correctness lives in the pure tests: they run with fake timestamps and
need no live session. Pushing logic across the seam is how this project loses its testability —
do not do it.

### 3. `dbus-fast` is the only runtime dependency

Everything else is standard library or a vendored static asset. Adding a second runtime
dependency is a decision to justify in `docs/documentation.md`, not a convenience. `pywayland`
and FastAPI were both rejected for good, recorded reasons.

### 4. Privacy is a design constraint, not a feature

- **No network egress. No telemetry. No cloud sync.** Ever.
- Anything that could leak defaults to the **more private** option: window titles off, in-app
  detail providers off, browser reporting is hostname-only and loopback-only, local/private
  addresses collapse to `(local app)`, filesystem paths generalise to `(local file)` and the
  path is never stored.
- Window titles and in-app detail leak document names and URLs. Any change touching them is a
  privacy decision — make it deliberately and record it.

### 5. Honesty over flattering numbers

The tracker measures *presence and interaction*, not productivity. Two rules encode this and
must not be softened: an active span ends at the **back-dated last-input** instant (trailing
idle is never counted), and a heartbeat gap larger than `max_gap` is **not** active time. If a
change would make the numbers look better without measuring more truth, it is the wrong change.
Update [`docs/honesty-review.md`](../../honesty-review.md) if a change alters what the numbers
mean.

## Testing and verification

- Runner: `uv run pytest`. Headless suite: `uv run pytest -m "not live"` — it must be green.
- Tests needing a real Wayland/KDE session carry `@pytest.mark.live` (4 of them) and are
  human-run. Prefer synthetic tests for correctness; use live tests only for hardware seams.
- Lint and format: `uv run ruff check`, `uv run ruff format`.
- Every step ends with a **Review** pass (read what you built) and a **Test** pass (prove
  behaviour against an explicit Pass condition). Do not advance until both are met.

## Documentation maintenance

Update docs in the **same change** that makes them stale — the maintenance table in
[`docs/workflow.md`](../../workflow.md) says which file covers what. In short: `structure.md`
for layout, `documentation.md` for decisions and state, `workflow.md` for commands and the API
surface, `checklist.md` for open work, `honesty-review.md` for meaning, `design-system.md` for
the view contract, and `docs/plans/` for new plans and handoff notes.

Do not restate the same fact in two files. Test counts live in exactly two places
(`documentation.md` and the root `README.md`); everything else links rather than repeats.

## Git

- Work on a branch; avoid committing straight to a shared `main` without reason.
- **Commit at the end of each validated phase. Commit only — do not push** unless the user
  explicitly asks.
- Message format: `[Plan Name] (Current/Total) Complete: <what was done>`.
- AI commits carry a co-author trailer naming the model that wrote them.

## Cleanup

- Never leave the only copy of an active instruction in a per-tool folder — `.claude/`,
  `.agents/`, and `.cursor/` hold **pointers only**.
- Delete setup-only helpers and template scaffolding once they are superseded. Stale docs cost
  more than missing ones: they get believed.
- Create a directory only when there is code to put in it.

## Definition of Done gate

Nothing is complete until the applicable items in [`docs/checklist.md`](../../checklist.md) have
been verified item by item, the headless suite is green, `ruff` is clean, and every doc the
change made stale has been updated. Do not claim completion otherwise.
