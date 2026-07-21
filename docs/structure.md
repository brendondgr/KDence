# Repository Structure — TimeKeeper-v2

This file is the canonical map of the repository. Keep it current whenever directories or
key files are added, moved, or removed.

## Guiding principle: lean root, grow per phase

The root is kept deliberately uncluttered. Only `docs/`, `src/`, and `tests/` exist as
visible top-level folders today. Directories that a build-plan phase will need
(`web/`, `scripts/`, `utils/`, `libs/`, and the `src/timekeeper/` component subpackages)
are **created when that phase begins**, not pre-scaffolded empty. Their intended homes are
documented below so there is no ambiguity when the time comes.

## Current Tree

```text
TimeKeeper-v2/
├── docs/                          # Source of truth: docs, skills, plans, references
│   ├── documentation.md           # Purpose, stack, architecture, decisions, status
│   ├── structure.md               # This file
│   ├── workflow.md                # Commands, environment, verification, git, handoff
│   ├── checklist.md               # Init Definition of Done + remaining work
│   ├── plans/
│   │   ├── activity-tracker-build-plan.md   # Authoritative test-driven build order
│   │   ├── phase-0-platform-notes.md        # Recorded Wayland/Plasma + idle-source facts
│   │   └── phase-1-activity-detection.md    # Phase 1 implementation plan
│   ├── references/
│   │   ├── frontend/              # Live-view design comp (reference only, not app code)
│   │   │   ├── README.md          # What the comp is + observed design tokens
│   │   │   ├── Activity Tracker.dc.html
│   │   │   └── support.js
│   │   └── protocols/
│   │       └── ext-idle-notify-v1.xml       # Vendored spec the idle wire client targets
│   └── skills/                    # Canonical skill definitions (read by all agents)
│       ├── global-project-rules/SKILL.md
│       ├── planner/{SKILL.md, planner.md, SETUP.md}
│       └── repository-structure/{SKILL.md, SETUP.md, structures/*}
├── src/
│   └── timekeeper/
│       ├── __init__.py            # Package root; subpackages added per phase (see below)
│       └── activity/             # Phase 1: active-vs-idle detection
│           ├── __init__.py        # Public surface (ActivityMonitor, WaylandIdleSource)
│           ├── monitor.py         # Pure threshold logic (no hardware) — where correctness lives
│           ├── wayland_idle.py    # Stdlib ext_idle_notifier_v1 wire client (hardware side)
│           ├── experiment.py      # Step 1.1 idle experiment (python -m timekeeper.activity.experiment)
│           └── __main__.py        # Step 1.2 live state printer (python -m timekeeper.activity)
├── tests/
│   ├── __init__.py
│   ├── test_scaffold.py           # Runner sanity check; real suites added per phase
│   └── activity/                 # Phase 1 suites
│       ├── __init__.py
│       ├── test_monitor.py        # Synthetic pure-logic tests (headless)
│       └── test_wayland_live.py   # @pytest.mark.live idle-source smoke test
├── .claude/skills/                # Claude Code pointers → docs/skills/*
├── .agents/skills/                # OpenAI Codex pointers → docs/skills/*
├── .cursor/rules/                 # Cursor rules (*.mdc) → docs/skills/*
├── .env.example
├── .python-version                # 3.13
├── pyproject.toml                 # uv project + tooling config
├── uv.lock
├── initialize.md                  # Initialization playbook (retained; see checklist)
└── README.md                      # Orientation → points to docs/
```

## Planned homes (created per build-plan phase)

| Path | Created in | Purpose |
|---|---|---|
| `src/timekeeper/activity/` | Phase 1 — **done** (see Current Tree) | Active-vs-idle detection (Wayland idle). |
| `src/timekeeper/focus/` | Phase 2 | Focused-window reporter (KWin / DBus). |
| `src/timekeeper/model/` | Phase 4 | Pure time model (no hardware) — the critical logic. |
| `src/timekeeper/storage/` | Phase 4 | Single-writer SQLite datastore. |
| `src/timekeeper/collector/` | Phase 3 | Merge live signals; the daemon loop. |
| `src/timekeeper/api/` | Phase 5 | Read-back query layer. |
| `tests/<area>/` | with each area | Purpose-grouped suites mirroring `src`; `tests/model/` is hardware-free and where correctness lives. |
| `web/` | Phase 6 | Minimal live view (see `docs/references/frontend/` for the design comp). |
| `scripts/` | Phase 7 | Dev/run helpers; session-lifecycle (systemd user) units. |
| `utils/` | as needed | Small cross-cutting helpers. |
| `libs/` | as needed | Shared internal packages (only when genuinely shared). |

## Why Each Existing Top-Level Path Exists

| Path | Purpose |
|---|---|
| `docs/` | Single source of truth: project docs, canonical skills, plans, and references. |
| `src/timekeeper/` | The application package; grows into the split above as phases land. |
| `tests/` | Test tree; grows purpose-grouped subfolders alongside the code they cover. |
| `.claude/`, `.agents/`, `.cursor/` | Thin per-tool pointers routing to `docs/skills/`. |
| root config | `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example` define the runtime. |
