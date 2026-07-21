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
| Time model | Stitched-heartbeat spans with back-dating (pure `model/`) | **Adopted (Phase 4)** — no dependency |
| Time-span storage | SQLite (stdlib `sqlite3`), single writer, WAL | **Adopted (Phase 4)** — no dependency |
| Read-back API | FastAPI + Uvicorn | Proposed — confirm at Phase 5.1 |
| Activity / idle source | Stdlib Wayland wire client for `ext_idle_notifier_v1` | **Adopted (Phase 1)** — no dependency |
| Compositor focus access | KWin script over `org.kde.kwin.Scripting` + `dbus-fast` receiver | **Adopted (Phase 2)** — `dbus-fast` |
| Live view | Minimal HTML/JS served by the API; ECharts (vendored, not CDN) | Proposed — confirm at Phase 6.1; design in `docs/design-system.md` |

A frontend **design comp** for the live view is kept at
`docs/references/frontend/` (a dark-terminal dashboard mockup + its runtime) as a visual
reference for Phase 6. It is reference-only, not app code — its tokens and panel/data
contract are translated into [`docs/design-system.md`](design-system.md), the source of
truth the Phase 5 API is shaped against and the Phase 6 view is built from.

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
10. **Focus comes from a KWin script, via `dbus-fast`.** On Plasma 6 / Wayland there is no
    DBus property for the active window's class. `focus/` loads a KWin script (over
    `org.kde.kwin.Scripting`) that connects to `workspace.windowActivated` and calls back
    out via `callDBus` — the only reliable egress from KWin's sandboxed engine (`print` is
    swallowed; timers are unavailable). A small **local** DBus service (`dbus-fast`,
    pure-Python — no compiler) receives the calls. `dbus-fast` is the first runtime
    dependency; it installs cleanly where `pywayland` did not. Proven live in Step 2.1.
11. **Window titles are opt-in (default off).** `focus/` keeps the app class always but
    drops titles unless `capture_titles=True`, because captions leak document names and
    URLs (the privacy rule: default to the more private option). The live view is designed
    to be meaningful with the app class alone.
12. **Time model = stitched heartbeats with back-dating.** `model/Timeline` turns per-interval
    `active` heartbeats into contiguous, non-overlapping spans: same-window heartbeats within
    a `max_gap` extend one span; a different window starts a new contiguous one. Two honesty
    rules are baked in — the active span ends at the **back-dated last-input** instant on
    idle (not at detection, so trailing idle is never counted), and any heartbeat gap larger
    than `max_gap` (a suspend/stall) is **not** active time. Idle is stored as the *absence*
    of a span. Fully hardware-free; proven in `tests/model` (the four named cases). Written
    up in `docs/plans/phase-4-time-model-and-storage.md`.
13. **Storage is single-writer SQLite (stdlib), day-agnostic.** `storage/Store` persists one
    SQLite write per model event (open / extend / close) in WAL mode so Phase 5 readers never
    block the writer; at most one row is ever `open=1`. On startup it finalizes any span left
    `open` by a crash **at its last stored heartbeat** — never extended to restart time (no
    invented hours). Spans store absolute wall-clock `start_at`/`end_at`; the "local day"
    definition and any midnight split live in the Phase 5 read layer, not at write time.
    `sqlite3` is stdlib, so Phase 4 added **no** runtime dependency.

## Current Status

**Phases 1–4 complete.** Phase 0 gates (platform confirmed: Wayland, Plasma 6.7.3;
trustworthy test runner), Phase 1 (Wayland idle source + pure activity monitor), Phase 2
(KWin-script focus source + pure identity/reporter), Phase 3 (live merge of both signals),
and Phase 4 (pure time model + single-writer SQLite storage under it) are done and
validated — **48 synthetic tests pass headless** (including the four named Step 4.2 honesty
cases and the crash-recovery test), **3 live tests pass** on the session, the merged live
line tracks the app and flips to idle after the threshold, and lint/format are clean. Phase
4 added **no** runtime dependency (`sqlite3` is stdlib); the only runtime dep remains
`dbus-fast` (Phase 2). Remaining **manual checks** (need a human): keyboard-only vs
mouse-only idle reset (Phase 1); two-app focus switching and keyboard return-to-active
(Phases 2–3); and a live persistence eyeball (`collector --store` → `python -m
timekeeper.storage`) plus a hard-kill crash-recovery check (Phase 4). Next up is Phase 5
(read-back API). Execution follows `docs/plans/activity-tracker-build-plan.md`; per-phase
detail lives under `docs/plans/`.

See `docs/checklist.md` for the Definition of Done and remaining work.
