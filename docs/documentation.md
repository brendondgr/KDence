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
| Activity / idle source | Stdlib Wayland wire client for `ext_idle_notifier_v1` | **Adopted (Phase 1)** — no dependency |
| Compositor focus access | `dbus-fast`/KWin scripting (or stdlib) | Proposed — confirm at Phase 2 |
| Live view | Minimal HTML/JS served by the API | Proposed — confirm at Phase 6.1 |

A frontend **design comp** for the live view is kept at
`docs/references/frontend/` (a dark-terminal dashboard mockup + its runtime) as a visual
reference for Phase 6. It is reference-only, not app code.

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
7. **Agent tooling: Claude Code, OpenAI Codex, and Cursor** are configured; pointer files
   live in `.claude/skills/`, `.agents/skills/`, and `.cursor/rules/` respectively, each
   routing to the canonical `docs/skills/`. Other tools can be added the same way.
8. **Lean root.** Only `docs/`, `src/`, `tests/` exist as visible top-level folders;
   phase-specific dirs (`web/`, `scripts/`, `utils/`, component subpackages) are created
   when their build-plan phase begins rather than pre-scaffolded empty.
9. **Idle is read from the compositor, not DBus.** A probe confirmed
   `GetSessionIdleTime` is `NotSupported` on Wayland. `activity/` therefore speaks the
   `ext_idle_notifier_v1` protocol directly over the Wayland socket using only the
   standard library (no `pywayland`/CFFI compile, no `sudo`, no third-party dependency).
   The event-based signal (`idled`/`resumed`) is turned into a threshold decision by the
   pure `ActivityMonitor`, which owns the clock — keeping the hardware/logic seam clean.

## Current Status

**Phase 1 (Activity detection) complete.** Phase 0 gates (platform confirmed:
Wayland, Plasma 6.7.3; trustworthy test runner) and Phase 1 (Wayland idle source + pure
activity monitor) are done and validated — synthetic tests pass headless, the live idle
source is verified on the session (`idled` fires), and lint/format are clean. Remaining
manual check: the keyboard-only vs mouse-only *resumed* reset (needs a human). Next up is
Phase 2 (focus detection). Execution continues to follow
`docs/plans/activity-tracker-build-plan.md`; per-phase detail lives under `docs/plans/`.

See `docs/checklist.md` for the Definition of Done and remaining work.
