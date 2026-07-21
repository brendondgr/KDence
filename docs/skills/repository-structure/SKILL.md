---
name: repository-structure
description: Use this skill when setting up, restructuring, documenting, or enforcing repository layout standards for projects, including web apps, backend systems, CLI tools, and agentic AI systems.
---
# Repository Structure Standard

This document defines the file structure for this repository. Adhering to it keeps the
project consistent, maintainable, and easy to navigate.

## Core Directory Structure

```text
root/
├── docs/       # Project documentation, skills, plans, and architectural overviews
├── src/        # Application package(s) — the KDence collector, model, API
├── web/        # Live-view surface (Phase 6)
├── tests/      # Purpose-grouped test tree
├── utils/      # Small utility functions and helper classes
├── scripts/    # Dev/run helpers and session-lifecycle units (Phase 7)
└── libs/       # Shared internal packages (create only when shared code appears)
```

### Workflow-Specific Structures
App-specific structures are documented individually to keep the core guidelines clean.
- [Web Interfaces](structures/web-interfaces.md)
- [Lab Reports](structures/lab-reports.md)
- [LangGraph Structure](structures/langgraph.md)

> Note: `website-architecture` is referenced by the upstream standard for full web apps.
> KDence's web surface is a **minimal local live view** backed by the read-back API,
> so that heavier skill is intentionally out of scope. See
> [docs/documentation.md](../../documentation.md) for the recorded decision.

---

## 1. Documentation (`docs/`)
All documentation regarding the project, including architecture, setup guides, and
structural maps, resides here.

- **Mandatory File:** `docs/structure.md`
  - Kept up-to-date with the current file structure.
  - Details main sub-folders and primary files, explaining their purpose without source code.

---

## 2. Application code (`src/`)
The `kdence` package lives under `src/kdence/` and is split by the build plan's
four loosely-coupled sub-problems so hardware-dependent code stays isolated from pure
logic:

- `activity/` — active-vs-idle detection (Wayland idle signal).
- `focus/` — focused-window reporter (compositor / DBus).
- `model/` — pure time model: instantaneous observations → durations (no hardware).
- `storage/` — single-writer datastore (SQLite).
- `collector/` — merges the live signals and owns the daemon loop.
- `api/` — read-back query layer (current state, per-app totals, timeline).

---

## 3. Utilities (`utils/`)
- **Small Utilities:** Basic utilities (e.g., a simple logger) live as individual files directly within `utils/`.
- **Large Utilities:** A utility with complex logic gets its own sub-folder.
- **Initialization:** Python sub-folders must include an `__init__.py`.

---

## 4. Libraries (`libs/`)
Internal libraries and external-facing components are modularized within `libs/`. Create
this directory only when genuinely shared code appears.

## 5. Tests (`tests/`)
Lightweight tests live in a top-level `tests/` directory, grouped by the area they cover.

- Keep tests small and focused as features are added.
- Prefer `tests/<area>/test_<behavior>.py` over one oversized flat folder.
- The pure-logic tests under `tests/model/` are where correctness actually lives — lean
  on them hardest; they need no live Wayland session.

### Test Layout

```text
tests/
├── activity/   # synthetic + live idle-detection tests
├── focus/      # focus-reporter tests
├── model/      # pure time-model tests (no hardware) — the critical suite
├── storage/    # datastore + crash-recovery tests
└── api/        # read-back reconciliation + concurrency tests
```

---

## Global Code Guidelines

### File Length Limits
- **Maximum Length:** 800 lines.
- **Ideal Length:** Under 500 lines.
- **Rule:** Favor modularity. If a file exceeds 800 lines, outsource logic to secondary modules.

### Package Management
We use `uv` as the primary package manager.
- **Primary Commands:** `uv add`, `uv run`, `uv sync`.
- Add runtime dependencies per build-plan phase rather than all up front.
- Avoid other package managers unless an environment constraint requires it.

---

*Last Updated: 2026-07-20*
