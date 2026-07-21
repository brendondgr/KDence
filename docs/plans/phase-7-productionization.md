# Productionization — Plan (Phase 7)

## 1. Introduction

Phases 1–6 produced two runnable processes — the **collector** (`python -m kdence.collector`,
the single writer) and the **read-back API + live view** (`python -m kdence.api`, reader
only). They currently start by hand. Phase 7 makes them **survive real use**: start with the
graphical session (after the compositor and DBus are up), restart if they die, write to a
**durable** store, and hold flat resource usage across a full working day.

The platform target (KDE Plasma 6 / Wayland, per `docs/plans/phase-0-platform-notes.md`) means
the natural lifecycle manager is **systemd user units** bound to `graphical-session.target`.
The honest split the whole project follows applies here too: the *content* of a unit file
(ordering, restart policy, exec line, the durable store path, local-only host) is **pure text we
can generate and unit-test headlessly**; only *enabling and surviving a real logout/login* is a
live gate that needs a human at the machine. This plan builds and tests the former, and specifies
the exact manual procedure for the latter.

**Store path (Phase 9 stays deferred).** The user chose to keep Historical Navigation (Phase 9)
as a plan only. Phase 9 Step 1 would make a durable XDG path the *default* for every entry point.
Phase 7 does **not** pull that forward: it does **not** change the collector/API defaults or add
`storage/paths.py`. Instead the generated unit passes an **explicit**
`--store %h/.local/share/kdence/kdence.db` (systemd expands `%h` to the user's home), so the
service writes to durable storage today while the default-path work remains Phase 9's.

## 2. Gaps & Unanswered Questions

- **`uv run` vs. venv interpreter in `ExecStart`.** *Decision*: use the **project venv
  interpreter** (`sys.executable` at install time, i.e. `.venv/bin/python`) with
  `WorkingDirectory` = project root. This avoids `uv` doing a sync/network check at service
  start (privacy + determinism) and needs no `uv` on `PATH` inside the unit. `uv run` remains the
  documented dev entry point.
- **Which units to install.** *Decision*: two units — `kdence-collector.service` (essential;
  the writer) and `kdence-api.service` (optional; only needed to view the dashboard). The API
  unit orders `After=`/`Wants=` the collector but does not hard-require it, so the collector
  running headless is a valid configuration.
- **Idle threshold in production.** *Decision*: default the unit to the real
  `IDLE_THRESHOLD_SECONDS` (300s), not the demo 5s the CLI defaults to.
- **Titles / privacy.** *Decision*: titles **off** in the generated unit (no `--titles`), matching
  the project's default-private stance (build-plan Step 2.2). A commented hint documents opting in.
- **Host / egress.** *Decision*: the API unit binds `127.0.0.1` only (the server default), never a
  routable address — the local-only rule.
- **Soak automation limits.** The full-day soak (Step 7.2) is inherently manual. *What we can
  automate*: a resource **sampler** (RSS of both processes over time) and a pure **summary** that
  flags an upward memory slope and reports the plausibility inputs. The verdict ("resources flat,
  numbers pass the smell test") is the human's, over a real day.
- **Restart storms.** *Decision*: `Restart=on-failure` with `RestartSec=5` and a
  `StartLimitIntervalSec`/`StartLimitBurst` guard so a hard-failing unit backs off instead of
  looping forever.

## 3. Hierarchical Step-by-Step Instructions

### Step 7.1 — Session lifecycle (systemd user units + installer)
- **Locations**:
  - new `src/kdence/service/units.py` — pure renderers `collector_unit(...)` and
    `api_unit(...)` returning unit-file **text** from explicit inputs (interpreter path, working
    dir, store path, threshold, host, port, titles). Encodes: `After=graphical-session.target` +
    `PartOf=graphical-session.target` + `WantedBy=graphical-session.target`; the API unit adds
    `After=`/`Wants=kdence-collector.service`; `Restart=on-failure`, `RestartSec=5`, start-limit
    guard; the exact `ExecStart` with the durable `--store` and (7.1) local host.
  - new `src/kdence/service/__main__.py` — `python -m kdence.service {print|install|uninstall}`:
    `print` dumps both units to stdout; `install` writes them to `$XDG_CONFIG_HOME/systemd/user`
    (fallback `~/.config/systemd/user`), creates the store's parent dir, and prints the exact
    `systemctl --user daemon-reload && systemctl --user enable --now …` commands (it does **not**
    silently enable — enabling is the user's explicit action); `uninstall` removes the unit files
    and prints the disable commands.
  - new `src/kdence/service/__init__.py` — public surface.
  - new `tests/service/__init__.py`, `tests/service/test_units.py`.
- **Rationale**: The unit *content* is where mistakes hide (wrong ordering → starts before DBus;
  missing `Restart` → dies silently; `/tmp` store → data lost on reboot; wrong host → egress). A
  pure renderer makes every one of those assertable without a live session. The installer keeps the
  irreversible-ish step (enabling a unit) in the user's hands per the safety rules.
- **Validation**: `tests/service/test_units.py` asserts, for both units: `After=graphical-session.target`
  present; collector has `WantedBy=graphical-session.target`; API orders after the collector;
  `Restart=on-failure` and `RestartSec` present; `ExecStart` contains `-m kdence.collector` /
  `-m kdence.api`, the durable `--store …/.local/share/kdence/kdence.db` (not `/tmp`), and
  `--threshold 300`; the API `--host 127.0.0.1` (no routable bind); **no** `--titles` by default;
  titles flag appears only when requested. Then `uv run ruff check` / `ruff format --check`.
  **Manual gate (needs a human at the machine):** `python -m kdence.service install`, enable
  both units, **log out and back in** → both come up and data resumes with no manual steps;
  `systemctl --user kill kdence-collector` → it restarts. Recorded in the checklist as manual.
- **Action**: Once the headless validation passes, commit (no push):
  `[Activity Tracker] (7/8) Complete: session lifecycle — systemd user units + installer`.

### Step 7.2 — Long-run soak (sampler + pure summary)
- **Locations**:
  - new `src/kdence/service/soak.py` — pure `summarize(samples)` over `(t, rss_bytes)` (and
    optional span-count) series: returns min/max/last RSS, a least-squares **slope** (bytes/hour),
    and a `flat` verdict against a tolerance; plus a `plausibility` block echoing active-hours vs
    wall-hours for the human's smell test. No I/O.
  - `src/kdence/service/__main__.py` gains `soak [--interval N] [--out FILE]` — samples the two
    units' RSS (via `systemctl --user show -p MainPID` → `/proc/<pid>/status`, stdlib only) on an
    interval, appends to a log, and on exit prints `summarize(...)`. The multi-hour run is manual;
    the sampler and summary are the automatable spine.
  - new `tests/service/test_soak.py`.
- **Rationale**: Slow leaks and drift only show over hours, so the *decision* is a human's over a
  real day — but the measurement and the leak-detection math should be tested, not eyeballed. A
  synthetic flat series must read `flat=True`; a synthetic climbing series must read `flat=False`.
- **Validation**: `tests/service/test_soak.py` feeds a flat RSS series (asserts `flat` True, slope
  ≈ 0) and a steadily climbing series (asserts `flat` False, positive slope), plus an empty/1-sample
  edge (no crash). `ruff` clean. **Manual gate:** leave both units running a full working day; at
  day's end run the summary → RSS slope flat, and the API totals pass your own smell test of the
  day; confirm a suspend/resume mid-day left spans intact (the Phase 4.1 suspend-gap rule).
- **Action**: Once the headless validation passes, commit (no push):
  `[Activity Tracker] (7/8) Complete: soak sampler + pure resource-summary + docs`.

### Step 7.3 — Docs & regression
- **Locations**: `docs/structure.md` (add `src/kdence/service/`, `tests/service/`, note
  `scripts/` intent satisfied in-package), `docs/documentation.md` (Phase 7 decision: systemd user
  units, venv interpreter, explicit durable `--store`, Phase 9 still deferred), `docs/workflow.md`
  (install/enable/soak commands), `docs/checklist.md` (7.1/7.2 headless done + manual gates listed),
  `docs/plans/activity-tracker-build-plan.md` (mark Phase 7 status).
- **Validation**: full headless suite green (`uv run pytest -m "not live"`), `ruff` clean, docs
  re-read for accuracy.
- **Action**: fold into the Step 7.2 commit (or a small trailing docs commit if 7.1/7.2 already
  landed): keep docs in the same change that makes them stale.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Unit renderers (pure) | `collector_unit` / `api_unit` → unit text; ordering, restart, durable store, local host | `src/kdence/service/units.py` |
| Service CLI | `print` / `install` / `uninstall` / `soak`; install writes to `~/.config/systemd/user`, prints enable commands | `src/kdence/service/__main__.py` |
| Unit tests | Ordering, restart, durable `--store`, threshold 300, local host, titles-off-by-default | `tests/service/test_units.py` |
| Soak summary (pure) | RSS slope / flat verdict / plausibility inputs over a sample series | `src/kdence/service/soak.py` |
| Soak tests | Flat vs climbing series verdicts + empty-series edge | `tests/service/test_soak.py` |
| Docs update | structure/documentation/workflow/checklist/build-plan reflect Phase 7 | `docs/…` |
| Manual gate record | Logout/login survival, kill-restart, full-day soak listed as human-verified | `docs/checklist.md` |
