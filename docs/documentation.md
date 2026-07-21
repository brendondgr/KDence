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
| Read-back API | Stdlib `http.server` (`ThreadingHTTPServer`), 127.0.0.1 | **Adopted (Phase 5)** — no dependency |
| Activity / idle source | Stdlib Wayland wire client for `ext_idle_notifier_v1` | **Adopted (Phase 1)** — no dependency |
| Compositor focus access | KWin script over `org.kde.kwin.Scripting` + `dbus-fast` receiver | **Adopted (Phase 2)** — `dbus-fast` |
| Live view | Static HTML/CSS/JS served by the API; **ECharts 5.5.0 vendored** (not CDN) | **Adopted (Phase 6)** — no runtime egress; design in `docs/design-system.md` |
| Session lifecycle | systemd **user** units bound to `graphical-session.target`; venv interpreter in `ExecStart` | **Adopted (Phase 7)** — no dependency; rendered/tested pure in `service/units.py` |

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
  Pure aggregates (`api/queries.py`) served by a thin stdlib `http.server`; reads run over
  **read-only** SQLite connections so they never block the writer. The local-day rule and any
  midnight split live here, not in storage.
- **`web/`** — a minimal live view (dark-terminal dashboard) that agrees with the API and
  with reality. Static assets served by the API itself; polls every ~2s; charts are ECharts
  vendored locally. No runtime network egress.

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
14. **Read-back API is stdlib `http.server`, not FastAPI.** Confirmed at Step 5.1 (the plan
    proposed FastAPI+Uvicorn but flagged it for confirmation). The read surface is ~4 local
    GET endpoints returning JSON to a single user on `127.0.0.1`; a `ThreadingHTTPServer`
    (thread per request) handles concurrent reads with **no new dependency**, matching the
    project's stdlib-first pattern. Correctness lives in a pure query module
    (`api/queries.py`) — totals, per-app share, timeline, current-state, and local
    TODAY/WEEK/MONTH windowing — unit-tested without HTTP; the server is a thin shell.
15. **Reads are isolated from the writer by construction.** Each request opens its own
    read-only (`mode=ro`) connection against the WAL database, so any number of readers run
    without blocking or corrupting the collector's single writer, and threads never share a
    connection. "Current session" is derived from the store's open row rather than a live
    channel to the collector, keeping the isolation clean.
16. **Live view: vendored ECharts, served by the API, polling (not streaming).** Confirmed at
    Step 6.1 (the plan offered hand-rolled SVG vs. vendored ECharts; vendored chosen for the
    closest match to the comp). ECharts 5.5.0 and JetBrains Mono woff2 are committed under
    `web/static/vendor/` and loaded locally, so there is **no runtime network egress**. The
    Phase 5 `http.server` gained a traversal-safe static route serving the dashboard at `/`.
    The page polls `/api/current` + `/api/summary` + `/api/timeline` every ~2s (data changes
    ~every collector interval, so polling beats streaming) and buckets the timeline spans
    client-side for the charts — **no API change** was needed. Assets live inside the package
    (`src/timekeeper/web/`, resolved via `STATIC_DIR`) like the `focus/` KWin asset, so the
    top-level `web/` from the original layout plan was not created.
17. **Session lifecycle is systemd user units, rendered as pure text.** Phase 7 makes both
    processes start with the graphical session (`After=`/`PartOf=`/`WantedBy=graphical-session.target`,
    so DBus and the compositor are up first) and restart on failure with a start-rate backoff.
    The unit *content* — the ordering, restart policy, `ExecStart`, durable store, and
    local-only bind — is generated by a pure module (`service/units.py`) and unit-tested
    without systemd; only enabling the units and surviving a real logout/login is a live gate.
    `ExecStart` uses the **project venv interpreter** (not `uv run`) so the service does no
    sync/network at start. The unit passes an **explicit** durable
    `--store %h/.local/share/timekeeper/tk.db`; this deliberately does **not** change the
    collector's default (the persistent-default work stays deferred as Phase 9), but it means
    the service writes to reboot-surviving storage today. No runtime dependency was added.
18. **Historical navigation: durable default + anchored/custom windows + server buckets.**
    Phase 9 makes the forever-archive explorable. The store default moved off RAM-backed `/tmp`
    to `$XDG_DATA_HOME/timekeeper/tk.db` (`storage/paths.py`), so data survives reboots by
    default (the Phase 7 units already used this path). The pure query layer gained
    `range_window(anchor=…)` (the period *containing* any date), `day`/`year`, `custom_window`,
    and a calendar-aligned `bucket_series` with `auto_granularity`; the server exposes
    date-aware `/api/summary`&`/api/timeline`, `/api/extent` (the navigable range), and
    `/api/buckets` (bounded series). The view drives its charts from `/api/buckets` so a
    year/all-time view never ships every raw span, and adds a Day/Week/Month/Year/Custom
    selector + prev/next + a date picker bounded by the extent. Plain `?range=today` is
    unchanged (back-compat). No runtime dependency was added; the DST-boundary skew over long
    history is a recorded accepted limit (`docs/honesty-review.md`).

## Current Status

**Phases 1–9 complete (headless + review); live gates pending.** Phase 0 gates (platform confirmed:
Wayland, Plasma 6.7.3; trustworthy test runner), Phase 1 (Wayland idle source + pure activity
monitor), Phase 2 (KWin-script focus source + pure identity/reporter), Phase 3 (live merge of
both signals), Phase 4 (pure time model + single-writer SQLite storage under it), Phase 5
(read-back query layer over a stdlib HTTP server, isolated from the writer), Phase 6 (the
live-view dashboard served by that API), Phase 7 (session lifecycle — systemd user units —
plus the soak sampler/summary), and Phase 9 (historical navigation — durable store, anchored/
custom windows + `/api/extent` + `/api/buckets`, and date navigation in the view) are done and
validated — **114 synthetic tests pass headless** (including the four named Step 4.2 honesty
cases, the crash-recovery test, the Phase 5 endpoint-reconciliation + concurrent read/write
cases, the Phase 6 static-route/traversal tests, the Phase 7 unit-content + soak-slope tests,
and the Phase 9 anchored-window / bucket-reconciliation / extent tests). The view was verified in-session
against both a seeded store and the **live running collector** (the API returned a real active
`brave-browser` session; the per-app table reconciled with the store). Phases 4–7 each added
**no** runtime dependency (stdlib `sqlite3` / `http.server` / `/proc` + `systemctl`; ECharts +
the font are vendored assets, not Python deps); the only runtime dep remains `dbus-fast`
(Phase 2). Remaining **manual checks** (need a human): keyboard-only vs mouse-only idle reset
(Phase 1); two-app focus switching and keyboard return-to-active (Phases 2–3); a live
persistence eyeball + hard-kill crash-recovery (Phase 4); watching the view track reality /
freeze on idle / recover after a collector restart (Phase 6); and the Phase 7 live gates. The
Phase 7 units are now **installed, enabled, and verified up** — the systemd-managed collector +
API run against the durable store and track a real live session — though **logout/login
survival, kill→restart, and the full-day soak** still need a human. **Phase 8** is done bar its
one live gate: the **full regression sweep passed** (87 headless tests green in a single pass,
`ruff` clean) and the **honesty review** is written (`docs/honesty-review.md` — presence ≠
productivity, with 7 known limits tagged accepted/future); the **cold-start stopwatch E2E**
(Step 8.1) remains a human measurement gate. **Phase 9** (historical navigation) is implemented
and its endpoints verified in-session against a 7-month seeded store (live/month/year/day/custom
all reconciled); its remaining gate is the interactive scrub over your own real archive as it
grows. Execution follows `docs/plans/activity-tracker-build-plan.md`; per-phase detail lives
under `docs/plans/`.

For what the numbers do and do not mean, see **`docs/honesty-review.md`**.

See `docs/checklist.md` for the Definition of Done and remaining work.
