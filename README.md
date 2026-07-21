# KDence

A **local, privacy-preserving activity tracker** built natively for **KDE Plasma 6 on
Wayland**. It answers one honest question — *"how long was I actually working?"* — by
watching activity (active vs. idle) and window focus (which app), turning that into
durations, storing them locally, and serving a read-back API plus a minimal live view.

All data stays on your machine. No cloud, no telemetry, no network egress.

## Requirements

KDence is purpose-built for one desktop and **only runs there**:

- **KDE Plasma 6 on Wayland** — required. KDence uses Wayland idle detection and a KWin
  DBus focus script, so it will **not** run on X11, GNOME, other desktops, macOS, or Windows.
- **Python 3.13**, managed with [`uv`](https://docs.astral.sh/uv/).

The pure time model is desktop-agnostic; only the sensing layer is Plasma-specific, so
porting to another desktop later means replacing the sensors, not the core.

## Documentation lives in `docs/`

`docs/` is the source of truth. Start here:

- [docs/documentation.md](docs/documentation.md) — purpose, stack, architecture, decisions, status.
- [docs/structure.md](docs/structure.md) — the repository layout and why each path exists.
- [docs/workflow.md](docs/workflow.md) — commands, environment, verification, git rules.
- [docs/checklist.md](docs/checklist.md) — setup Definition of Done + remaining work.
- [docs/plans/activity-tracker-build-plan.md](docs/plans/activity-tracker-build-plan.md) — the authoritative, test-driven build order.
- [docs/skills/global-project-rules/SKILL.md](docs/skills/global-project-rules/SKILL.md) — rules every agent reads first.

## Install & run

```bash
cp .env.example .env     # optionally edit ports (defaults: API 5785, tab-ingest 5786)
./install.sh             # sets up the env, installs systemd user units, starts everything
```

`install.sh` reads `.env`, generates the systemd **user** units, aligns the browser extension
to the ingest port, and enables + starts the collector + dashboard (auto-start on graphical
login). **Re-run `./install.sh` any time to restart.** The dashboard is then at
`http://127.0.0.1:5785`. For per-website breakdowns, also load the browser extension
(`browser-extension/`, see its README) — no installer can do that for you.

## Developing

```bash
uv sync            # create the environment and install dev tooling
uv run pytest      # run the test suite
uv run ruff check  # lint
```

Runtime dependencies are added per build-plan phase, so the project starts with only the
dev toolchain.

## Status

Initialized (docs, skills, and the package/test tree). Tracker functionality is built by
following the build plan. See the checklist for what's next.
</content>
</invoke>
