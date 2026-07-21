# TimeKeeper-v2

A **local, privacy-preserving activity tracker** for **KDE Plasma 6 on Wayland**. It answers
one honest question — *"how long was I actually working?"* — by watching activity (active
vs. idle) and window focus (which app), turning that into durations, storing them locally,
and serving a read-back API plus a minimal live view.

All data stays on your machine. No cloud, no telemetry, no network egress.

## Documentation lives in `docs/`

`docs/` is the source of truth. Start here:

- [docs/documentation.md](docs/documentation.md) — purpose, stack, architecture, decisions, status.
- [docs/structure.md](docs/structure.md) — the repository layout and why each path exists.
- [docs/workflow.md](docs/workflow.md) — commands, environment, verification, git rules.
- [docs/checklist.md](docs/checklist.md) — setup Definition of Done + remaining work.
- [docs/plans/activity-tracker-build-plan.md](docs/plans/activity-tracker-build-plan.md) — the authoritative, test-driven build order.
- [docs/skills/global-project-rules/SKILL.md](docs/skills/global-project-rules/SKILL.md) — rules every agent reads first.

## Quick start

```bash
uv sync            # create the environment and install dev tooling
uv run pytest      # run the test suite (scaffold sanity test today)
uv run ruff check  # lint
```

Python 3.13, managed with [`uv`](https://docs.astral.sh/uv/). Runtime dependencies are
added per build-plan phase, so the project starts with only the dev toolchain.

## Status

Initialized (docs, skills, and an empty package/test tree). Tracker functionality is built
by following the build plan, starting at Phase 0. See the checklist for what's next.
