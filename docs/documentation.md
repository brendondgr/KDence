# KDence — Project Documentation

Purpose, stack, architecture, the decisions that still bind, and current state.
For layout see [structure.md](structure.md); for commands see [workflow.md](workflow.md);
for what the numbers mean see [honesty-review.md](honesty-review.md).

## Purpose

KDence is a **local, privacy-preserving activity tracker** for **KDE Plasma 6 on Wayland**.
It answers one honest question — *"how long was I actually working, and in what?"* — by
observing activity (active vs. idle) and window focus (which app), converting those
observations into durations, storing them locally, and serving a read-back API plus a live
dashboard.

All data stays on the machine: no cloud, no telemetry, no network egress. The intended user
is a single desktop user on their own machine — single writer, not multi-tenant.

## Tech Stack

| Concern | Choice | Dependency |
|---|---|---|
| Language / runtime | Python 3.13 (`.python-version`) | — |
| Package / env manager | `uv` | — |
| Test runner / lint | `pytest` / `ruff` | dev only |
| Activity / idle source | Stdlib Wayland wire client for `ext_idle_notifier_v1` | none |
| Compositor focus access | KWin script over `org.kde.kwin.Scripting` + a local DBus receiver | **`dbus-fast`** |
| In-app detail (MPRIS) | Session-bus poll on the collector interval | reuses `dbus-fast` |
| Time model | Stitched-heartbeat spans with back-dating (pure `model/`) | none |
| Storage | SQLite (stdlib `sqlite3`), single writer, WAL | none |
| Read-back API | Stdlib `http.server` (`ThreadingHTTPServer`), 127.0.0.1 | none |
| Live view | Static HTML/CSS/JS served by the API; ECharts 5.5.0 + JetBrains Mono **vendored** | none |
| Session lifecycle | systemd **user** units bound to `graphical-session.target` | none |
| Browser sites | Cross-browser WebExtension → loopback ingest | none (not Python) |
| Category config | Stdlib JSON under `$XDG_CONFIG_HOME/kdence/` | none |

**`dbus-fast` is the only runtime dependency.** Everything else is standard library or a
vendored static asset. That is a deliberate property, not an accident — see decision 2.

The live view's visual target is the design comp under
[`docs/references/frontend/`](references/frontend/README.md); its tokens and panel contract
are translated into [design-system.md](design-system.md).

## Architecture

The core design rule is a **clean seam between pure logic and hardware-dependent code**.
Correctness lives entirely on the pure side and runs headless with fake timestamps.

```
 hardware-dependent (needs a live Wayland session, little logic)
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │  activity/  │   │   focus/    │   │   detail/   │
   │ active/idle │   │  which app  │   │ what inside │
   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
          └─────────────────┼─────────────────┘
                            ▼
                     ┌─────────────┐   ┌──────────┐  pure logic (no hardware)
                     │ collector/  │──▶│  model/  │  observations → durations
                     └──────┬──────┘   └────┬─────┘
                            ▼               ▼
                     ┌─────────────┐  single-writer SQLite (WAL)
                     │  storage/   │
                     └──────┬──────┘
                            ▼
                     ┌─────────────┐   ┌─────────────┐
                     │    api/     │──▶│  web/ view  │  read-back + live
                     └─────────────┘   └─────────────┘
```

| Package | Responsibility |
|---|---|
| `activity/` | Active-vs-idle from the Wayland idle signal. On Wayland the compositor tracks input at the **seat** level (keyboard + mouse + touch together), collapsing "merge two input streams" into one signal. The pure `ActivityMonitor` owns the clock and turns `idled`/`resumed` events into a threshold decision. |
| `focus/` | The focused window's identity, reported out of KWin. Pure `identity.py` (app class always; titles opt-in) + `reporter.py` (change-deduped) over a hardware `kwin_source.py`. |
| `detail/` | *What you were doing inside* a focused app: pure `caption.py` (window title → document label) and `mpris/` (media metadata → track label) plus `config.py`, the runtime `detail.json` the UI writes and the collector reads. |
| `browser/` | The active tab's **hostname** as a sub-dimension under browsers: pure `site.py` + focus-gated `tracker.py` + a loopback-only `ingest.py`. |
| `collector/` | Merges the live signals, resolves one in-app detail per interval via `providers.py`, and owns the daemon loop that writes spans. |
| `model/` | Pure time model: instantaneous observations → non-overlapping honest durations. Owns the active→idle boundary rule. No hardware, no SQL. |
| `storage/` | Single-writer SQLite under the model; crash-safe, WAL, read-isolated via a `mode=ro` reader. |
| `grouping/` | Rolls per-app (and per-site) totals up into user-defined categories. Pure palette + category config; kept **off** the span store. |
| `api/` | Read-back query layer. Pure aggregates in `queries.py` served by a thin `http.server`. The local-day rule and any midnight split live here, not in storage. |
| `web/` | The live dashboard, served by the API at `/`, polling every ~2s. Vendored charts, no runtime egress. |
| `service/` | Pure systemd user-unit renderers + the soak sampler; the `install`/`uninstall`/`soak` CLI. |

## Decisions that still bind

Chronological build history lives in [`docs/plans/`](plans/). These are the choices a
contributor must not casually reverse.

1. **Pure logic is isolated from hardware.** The time model is fully unit-tested with fake
   timestamps; the DBus/KWin/Wayland parts carry almost no logic. This seam is what makes
   headless testing possible at all — do not push logic across it.
2. **Stdlib-first; dependencies are earned.** `dbus-fast` is the only runtime dependency,
   because KWin's script sandbox offers no other reliable egress. SQLite, the HTTP server,
   the Wayland idle client, the unit renderer, and the soak sampler are all stdlib; ECharts
   and JetBrains Mono are vendored binaries, not packages. `pywayland` was rejected (CFFI
   compile, system dev headers); FastAPI + Uvicorn was rejected at Phase 5 (a ~9-route local
   read surface for one user does not warrant it).
3. **Local-only, privacy-first, by construction.** No network egress anywhere. Everything
   that could leak defaults to the more private option: window titles are **off** unless
   opted in, in-app detail providers are **off** unless listed, the browser extension sends a
   **hostname only** and binds loopback only, local/private addresses collapse to a generic
   `(local app)` bucket, and filesystem paths generalise to `(local file)` — the path is never
   stored.
4. **Idle comes from the compositor, not DBus.** A probe confirmed `GetSessionIdleTime` is
   `NotSupported` on Wayland, so `activity/` speaks `ext_idle_notifier_v1` directly over the
   Wayland socket using only the standard library.
5. **Focus comes from a KWin script via `callDBus`.** Plasma 6 exposes no DBus property for
   the active window's class, and KWin's engine swallows `print` and has no timers. A script
   loaded over `org.kde.kwin.Scripting` calls back out to a small local `dbus-fast` service.
   If the compositor evicts the script it is **re-injected** (checked via `isScriptLoaded`)
   rather than silently freezing focus and mislabelling hours.
6. **Honest durations over raw uptime.** `model/Timeline` stitches per-interval heartbeats
   into contiguous spans, with two honesty rules baked in: an active span ends at the
   **back-dated last-input** instant on idle (never at detection, so trailing idle is not
   counted), and a heartbeat gap larger than `max_gap` (a suspend or stall) is **not** active
   time. Idle is stored as the *absence* of a span. Proven by the four named cases in
   `tests/model/`.
7. **Storage is single-writer SQLite, day-agnostic.** One write per model event in WAL mode;
   at most one row is ever `open=1`. On startup a span left open by a crash is finalized **at
   its last stored heartbeat** — never extended to restart time, so a crash cannot invent
   hours. Spans store absolute wall-clock times; "local day" is a read-layer concept.
8. **Reads are isolated from the writer by construction.** Each request opens its own
   read-only (`mode=ro`) connection against the WAL database, so readers never block or
   corrupt the collector's single writer and threads never share a connection.
9. **Schema growth is additive and idempotent.** The browser-only `site` column was
   generalised to `detail` + `detail_source` by an in-place migration; a legacy `site` value
   is **coalesced on read** (`SpanRow.effective_*`), so existing history keeps working with no
   backfill. Any future sub-dimension follows the same shape.
10. **Config lives off the span store.** Categories (`categories.json`), the browser engine
    map (`browsers.json`), and the detail runtime (`detail.json`) are JSON under
    `$XDG_CONFIG_HOME/kdence/`. The API's only mutations (`POST /api/categories`,
    `POST /api/detail`) validate strictly and atomically write **that file only** — the span
    store stays read-only from the API side, preserving decision 8.
11. **The API and collector share files, not IPC.** The UI writes `detail.json`; the collector
    re-reads it each interval and reconfigures providers live (connecting or closing the MPRIS
    source) with no restart. Consistent with the polling design; two processes, no channel.
12. **The store default is durable.** `$XDG_DATA_HOME/kdence/kdence.db`, not `/tmp` — a RAM
    tmpfs default was a data-loss trap and was removed.
13. **The web surface stays minimal.** The live view is a small local surface backed by the
    read-back API, not a public web app. Heavier web-architecture and accessibility standards
    are intentionally out of scope; revisit only if it grows into a real front end.
14. **Charts stay per-entity.** Grouping, site, and detail breakdowns are table/drill-down
    features. The distribution and share charts treat each application as one entity so a
    browser never fragments the visual.
15. **Hiding is not deleting.** A hidden detail value is suppressed at collection and folded
    into `(other)` at read time; the original spans stay on disk. Real removal would be a
    separate, explicit, destructive action — recorded as honesty limit #11, not done silently.
16. **One env-driven installer; ports never bump silently.** `./install.sh` is the single
    idempotent install/restart path: it reads `.env`, generates the units from the **tested**
    `service/units.py` renderer (no `sed`), aligns the extension to the ingest port, and
    restarts both services. A port held by a foreign process is a **hard error** naming the
    `.env` key to change — an earlier silent auto-bump is exactly what once let the
    extension's target port and the collector's ingest port diverge, recording no site data.
    Canonical ports: **API 5785**, **tab-ingest 5786**.
17. **Agent tooling routes to one source of truth.** Claude Code (`.claude/skills/`), OpenAI
    Codex (`.agents/skills/`), and Cursor (`.cursor/rules/`) hold **pointers only**; the
    canonical skills live in [`docs/skills/`](skills/). Add a tool by mirroring the pointer
    pattern — never by duplicating instructions.
18. **Lean root, grow per phase.** Directories are created when code needs them, not
    pre-scaffolded empty. `scripts/` was superseded by the in-package `service/`; the live
    view lives at `src/kdence/web/` rather than a top-level `web/` so `STATIC_DIR` resolves
    robustly from the installed package.

## Current State

Measured on 2026-08-04, not narrated:

| | |
|---|---|
| Headless suite | **315 tests pass** (`uv run pytest -m "not live"`) |
| Live-marked tests | 4, human-run (need a real Wayland/KDE session) |
| Lint | `ruff check` clean |
| Runtime dependencies | 1 (`dbus-fast`) |
| Deployment | systemd user units installed and verified up against the durable store |

Everything in the build plan is implemented: idle detection, focus detection, live merge, the
pure time model, single-writer storage, the read-back API, the dashboard, systemd lifecycle,
historical navigation, browser sites, application grouping, site categories, in-app detail with
live toggles and hide/restore, and the mobile-responsive view.

What is **not** done is a set of live-hardware gates that require a human at the keyboard —
logout/login survival, a full-day soak, a cold-start stopwatch E2E, in-browser extension
attribution, and eyeballing live caption/MPRIS attribution. They are enumerated in
[checklist.md](checklist.md).

Read [honesty-review.md](honesty-review.md) before trusting any number this produces.
