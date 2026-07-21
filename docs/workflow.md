# Workflow — TimeKeeper-v2

Operational rules: environment, commands, documentation maintenance, verification, and
git/handoff. Every agent reads this before working (see
`docs/skills/global-project-rules/SKILL.md`).

## Environment

- **Runtime:** Python 3.13 (pinned in `.python-version`).
- **Manager:** `uv` is mandatory. Do not use pip/poetry/conda unless an environment
  constraint forces it, and document the reason.
- **Platform:** KDE Plasma 6 on Wayland. Some tests (idle/focus) require a live graphical
  session and cannot run in headless CI; they are marked and run locally.

## Commands

| Task | Command |
|---|---|
| Install / sync deps | `uv sync` |
| Add a runtime dep | `uv add <pkg>` |
| Add a dev dep | `uv add --dev <pkg>` |
| Run a module | `uv run python -m timekeeper.<component>` |
| Run tests | `uv run pytest` |
| Run one area | `uv run pytest tests/model` |
| Run hardware-free tests only | `uv run pytest -m "not live"` |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |

> Dependencies are added **per build-plan phase**, not all at once. `pyproject.toml` starts
> with only the dev toolchain (`pytest`, `ruff`); runtime deps (DBus lib, FastAPI, etc.)
> arrive as their phase begins.

### Test markers

- Tests that need a live Wayland/KDE session are marked `@pytest.mark.live`.
- Pure-logic tests (the `tests/model/` suite especially) carry no marker and must always
  pass anywhere. Lean on them for correctness.

## Documentation Maintenance

Update docs in the same change that makes them stale:

- `docs/structure.md` — directories/key files added, moved, or removed.
- `docs/documentation.md` — new decisions, stack/dependency changes, status shifts.
- `docs/workflow.md` — command, environment, or verification changes.
- `docs/checklist.md` — check items off; add newly discovered work.
- `docs/plans/` — new plans and handoff plans; keep the active build plan current.

## Verification Workflow

The build plan is test-driven. **Every step ends with two passes:**

1. **Review** — read what you built and confirm it does what the step intends.
2. **Test** — prove behavior with an explicit **Pass condition**.

Do not advance a step until both pass. Regression checkpoints (Steps 1.3, 2.4, 4.4, 8.2)
re-run prior suites; nothing earlier may break.

Special critical gates:
- **Step 1.1** — the five-minute idle experiment (learn the real idle signal before designing).
- **Step 2.1** — prove the compositor emits focus at all.
- **Step 3.1** — the merged live line you'd "bet money on."
- **Step 4.2** — the pure-logic time-model suite; the back-dating (active→idle) case is the one people get wrong.

## Git & Handoff

- Work on a branch; avoid committing straight to a shared `main` without reason.
- **Commit at the end of each validated phase. Commit only — do not push** unless the user
  explicitly asks.
- Phase commit message format:
  `[Plan Name] (Current/Total) Complete: <what was done>`.
- Co-author trailer for AI commits:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Handoff: write a handoff note under `docs/plans/` capturing what's done, what's next, and
  any open decisions, so another agent can continue without re-asking.

## Supported Agent Tools

- **Claude Code** — configured. Pointers in `.claude/skills/` route to `docs/skills/`.
- To add another tool (Codex, Cursor, Gemini CLI, Antigravity), mirror the same pointer
  pattern into that tool's folder — never duplicate full instructions; point to `docs/`.
