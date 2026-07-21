# TimeKeeper-v2 — Project Documentation

## Purpose

TimeKeeper-v2 is a **local, privacy-preserving activity tracker** for **KDE Plasma 6 on
Wayland**. It answers a single honest question — *"how long was I actually working?"* — by
observing activity (active vs. idle) and window focus (which app), converting those
observations into durations, storing them locally, and serving a read-back API plus a
minimal live view.

All data stays on the user's machine. There is no cloud sync, no telemetry, and no network
egress.

## Intended User

A single desktop user on their own machine (solo use, single writer). Not multi-tenant.

## Tech Stack

| Concern | Choice | Status |
|---|---|---|
| Language / runtime | Python 3.13 | Fixed (`.python-version`) |
| Package / env manager | `uv` | Fixed |
| Test runner | `pytest` | Fixed |
| Lint / format | `ruff` | Fixed |
| Time-span storage | SQLite (stdlib `sqlite3`) | Proposed — confirm at Phase 4.3 |
| Read-back API | FastAPI + Uvicorn | Proposed — confirm at Phase 5.1 |
| DBus / compositor access | `dbus-fast` (or `jeepney`) | Proposed — confirm at Phase 1/2 |
| Live view | Minimal HTML/JS served by the API | Proposed — confirm at Phase 6.1 |

Runtime dependencies are added **per build-plan phase** (`uv add`) rather than all up
front, because the build is test-driven and each phase pulls in only what it needs. The
"Proposed" rows above are recommended defaults, not commitments — each is a decision point
in the build plan.

## Architecture

The system decomposes into four loosely-coupled parts (see the build plan for the full
rationale). The key design rule is a **clean seam between pure logic and
hardware-dependent code**:

```
 hardware-dependent (needs a live Wayland session, little logic)
   ┌─────────────┐        ┌─────────────┐
   │  activity/  │        │   focus/    │
   │ active/idle │        │ which app   │
   └──────┬──────┘        └──────┬──────┘
          └──────────┬───────────┘
                     ▼
              ┌─────────────┐   pure logic (fake timestamps, no hardware)
              │ collector/  │──▶│  model/  │  observations → durations
              └──────┬──────┘   └────┬─────┘
                     ▼                ▼
              ┌─────────────┐   ┌─────────────┐
              │  storage/   │◀──│ single-writer│  SQLite spans
              └──────┬──────┘   └─────────────┘
                     ▼
              ┌─────────────┐        ┌─────────────┐
              │    api/     │───────▶│  web/ view  │  read-back + live
              └─────────────┘        └─────────────┘
```

- **`activity/`** — active-vs-idle detection from the Wayland idle signal. On Wayland the
  compositor tracks input at the *seat* level (keyboard + mouse + touch together), which
  collapses the "merge two input streams" problem into one signal. This is *proven* in
  build-plan Step 1.1, not assumed.
- **`focus/`** — the currently focused window's identity, reported out of the compositor
  (KWin scripting / DBus). Window-identity fields and the title-privacy stance are decided
  in Step 2.2.
- **`model/`** — pure time model: turns instantaneous observations into non-overlapping
  durations. Owns the **active→idle boundary rule** (an active span ends near last-input,
  not near detection — the back-dating case). No hardware; fully unit-testable.
- **`storage/`** — single-writer SQLite datastore under the tested model; reads must not
  block or corrupt writes.
- **`collector/`** — merges the two live signals and owns the daemon loop that writes spans.
- **`api/`** — read-back query layer: current state, today's per-app totals, and a timeline.
- **`web/`** — a minimal live view that agrees with the API and with reality.

## Major Decisions

1. **Python + `uv`, Python 3.13.** Matches repo conventions and the tracker's system-level needs.
2. **Pure logic isolated from hardware.** The time model is fully unit-tested with fake
   timestamps; DBus/KWin/Wayland parts carry almost no logic. This seam is what makes
   per-step testing possible.
3. **Activity is one signal.** Seat-level input tracking on Wayland; verified in Step 1.1.
4. **Local-only / privacy-first.** No network egress; window titles treated as sensitive.
5. **Dependencies added per phase**, not up front — the build is test-driven.
6. **Web surface kept minimal.** The upstream `website-architecture` / `ui-frontend` /
   accessibility skills are **not present** in this repo and are intentionally out of
   scope: the live view is a small local surface backed by the read-back API, not a
   public web app. Revisit only if the view grows into a real front end.
7. **Agent tooling: Claude Code** is the configured environment for this session; pointer
   files live in `.claude/skills/`. Other tools can be added by mirroring the pointers.

## Current Status

**Initialized (scaffolding + docs + skills), pre-implementation.** The repository has its
canonical docs, migrated skills, agent pointers, and an empty package/test tree ready for
the build plan. No tracker functionality is implemented yet — execution follows
`docs/plans/activity-tracker-build-plan.md`, starting at Phase 0.

See `docs/checklist.md` for the initialization Definition of Done and remaining work.
