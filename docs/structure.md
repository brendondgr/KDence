# Repository Structure — TimeKeeper-v2

This file is the canonical map of the repository. Keep it current whenever directories or
key files are added, moved, or removed.

## Tree

```text
TimeKeeper-v2/
├── docs/                          # Source of truth: docs, skills, plans
│   ├── documentation.md           # Purpose, stack, architecture, decisions, status
│   ├── structure.md               # This file
│   ├── workflow.md                # Commands, environment, verification, git, handoff
│   ├── checklist.md               # Init Definition of Done + remaining work
│   ├── plans/                     # Implementation & handoff plans
│   │   └── activity-tracker-build-plan.md   # Authoritative test-driven build order
│   └── skills/                    # Canonical skill definitions (read by all agents)
│       ├── global-project-rules/  # Mandatory rules every agent reads first
│       │   └── SKILL.md
│       ├── planner/               # Planning skill
│       │   ├── SKILL.md
│       │   ├── planner.md         # Plan format & quality rules
│       │   └── SETUP.md           # Planning questionnaire
│       └── repository-structure/  # Layout standard
│           ├── SKILL.md
│           ├── SETUP.md           # Structure questionnaire
│           └── structures/        # Workflow-specific layout references
│               ├── web-interfaces.md
│               ├── lab-reports.md
│               └── langgraph.md
├── src/
│   └── timekeeper/                # Application package
│       ├── __init__.py
│       ├── activity/              # Phase 1: active-vs-idle detection (Wayland idle)
│       ├── focus/                 # Phase 2: focused-window reporter (KWin / DBus)
│       ├── model/                 # Phase 4: pure time model (no hardware) — critical logic
│       ├── storage/              # Phase 4: single-writer SQLite datastore
│       ├── collector/            # Phase 3 + daemon: merge live signals, write spans
│       └── api/                  # Phase 5: read-back query layer
├── web/                           # Phase 6: minimal live view surface
├── tests/                         # Purpose-grouped tests (mirror of src areas)
│   ├── activity/
│   ├── focus/
│   ├── model/                     # The pure-logic suite where correctness lives
│   ├── storage/
│   └── api/
├── utils/                         # Small shared helpers (e.g. logging)
├── scripts/                       # Dev/run helpers; session-lifecycle units (Phase 7)
├── .claude/skills/                # Claude Code pointer files → docs/skills/*
│   ├── global-project-rules/SKILL.md
│   ├── planner/SKILL.md
│   └── repository-structure/SKILL.md
├── .env.example                   # Documented environment variables
├── .python-version                # 3.13
├── pyproject.toml                 # uv project + tooling config
├── uv.lock                        # Locked dependency set
├── initialize.md                  # Initialization playbook (retained; see checklist)
└── README.md                      # Orientation → points to docs/
```

## Why Each Top-Level Path Exists

| Path | Purpose |
|---|---|
| `docs/` | The single source of truth: project docs, canonical skills, and plans. |
| `src/timekeeper/` | The application package, split by the build plan's four sub-problems so hardware-dependent code stays isolated from pure logic. |
| `web/` | The minimal local live view backed by the read-back API (Phase 6). |
| `tests/` | Purpose-grouped test tree; `tests/model/` is the hardware-free correctness suite. |
| `utils/` | Small cross-cutting helpers that don't belong to one component. |
| `scripts/` | Developer run/dev scripts and Phase-7 session-lifecycle (systemd user) units. |
| `.claude/` | Claude Code pointer files — thin frontmatter routing to `docs/skills/`. |
| root config | `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example` define the runtime. |

`libs/` is **not** created yet; add it only when genuinely shared internal packages appear
(per the repository-structure skill).
