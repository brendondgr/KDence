# Phase 1 — Activity Detection (Implementation Plan)

Derived from [activity-tracker-build-plan.md](activity-tracker-build-plan.md) Phase 1
(Steps 1.1–1.3) plus the outstanding Phase 0 platform-gate items (0.1, 0.2).

## 1. Introduction

Phase 1 answers one question: *"is the user active or idle right now?"* On **KDE Plasma 6
/ Wayland** the honest source of that signal is **not** a DBus idle-time counter — a probe
confirmed `org.freedesktop.ScreenSaver.GetSessionIdleTime` returns **`NotSupported` on
Wayland**. The real source is the compositor's **`ext_idle_notifier_v1`** protocol
(advertised here at v2), which is *event-based*: you request a notification with a timeout,
the compositor sends **`idled`** once the seat has had no input for that long and
**`resumed`** on the next input. Wayland tracks input at the **seat** level (keyboard +
pointer + touch together), which is why activity collapses to a single signal.

The approach keeps the mandated **pure-logic / hardware seam** clean:

- A **`WaylandIdleSource`** (hardware) speaks just enough of the Wayland wire protocol —
  in the **standard library only**, no compiler, no DBus, no third-party dependency — to
  emit `idled` / `resumed` transitions. (`pywayland` was rejected: it compiles a CFFI
  extension needing `python3-devel` + `wayland-devel`, i.e. a `sudo` step, on a tool whose
  whole point is to stay local and light.)
- A pure **`ActivityMonitor`** (no hardware) consumes those transitions plus its own
  monotonic clock and owns the **threshold** decision. It is fully unit-testable headless —
  this is where correctness lives, per the build plan.

## 2. Gaps & Unanswered Questions

- **Idle value's unit (Step 1.1 Q1).** *Resolved by probe:* there is no ms counter on this
  platform; the signal is event transitions. We therefore time the idle span with our own
  `time.monotonic()` clock and back-date the idle start by the notification timeout — exactly
  the fallback the build plan's Step 1.2 review anticipates.
- **Does idle reset on keyboard *and* mouse independently (Step 1.1 Q2)?** *Assumption:*
  yes, because `ext_idle_notifier_v1` is seat-level. This is the one claim a headless agent
  cannot prove — it needs a human doing keyboard-only vs mouse-only input. **Human
  intervention is needed to answer this**; it is the critical live check and is listed in
  the manual-verification handoff.
- **Idle threshold default.** *Assumption:* 300 s (5 min) for real use, matching
  `.env.example` (`IDLE_THRESHOLD_SECONDS=300`). The live demo runner defaults to a short
  threshold so the flip is observable in seconds; both are configurable.
- **Notification resolution (timeout we pass the compositor).** *Assumption:* 1000 ms — small
  enough to detect idle-start promptly and back-date accurately, decoupled from the user
  threshold (which the monitor applies in Python).

## 3. Hierarchical Step-by-Step Instructions

### Step 0.1 — Confirm platform assumptions (build-plan gate)
- **Locations:** `docs/plans/phase-0-platform-notes.md` (new).
- **Rationale:** Later steps rely on knowing this is Wayland (not X11 fallback) and the
  Plasma major version (the activation signal was renamed between Plasma 5 and 6). Record the
  probe results (session type, `plasmashell`/`kwin` version, advertised idle globals, the
  `GetSessionIdleTime` NotSupported result) so the design rationale is auditable.
- **Action:** Verify the notes match live `dbus-send` / `wayland-info` output. Validated when
  we can state "Wayland, Plasma 6.x" with certainty.

### Step 0.2 — Trustworthy test scaffold (build-plan gate)
- **Locations:** `tests/activity/` (new package), `pyproject.toml` (pytest config already
  present).
- **Rationale:** Every later assertion depends on the runner reporting both green and red
  correctly. Rather than commit a permanently-red test, prove red/green once during
  execution and keep only real passing suites.
- **Action:** Show a deliberately-failing assertion goes red and a passing one goes green,
  then run `uv run pytest`. Validated when both outcomes are observed.

### Step 1.1 — The five-minute idle experiment
- **Locations:** `src/kdence/activity/wayland_idle.py` (`WaylandIdleSource`),
  `src/kdence/activity/experiment.py` (runnable via
  `uv run python -m kdence.activity.experiment`).
- **Rationale:** Learn the ground truth of the idle source instead of assuming it. The
  experiment logs every `idled`/`resumed` transition with timestamps and a running idle-seconds
  counter, so a human can run the three sub-cases (sit still 30 s; keyboard only; mouse only)
  and read the answers to the Step 1.1 questions directly.
- **Action:** Automated portion (`idled` fires with no input) is validated by the agent; the
  keyboard-only / mouse-only reset check is handed to the user. Validated when transitions are
  logged and the automated `idled` is observed.

### Step 1.2 — Build the activity monitor
- **Locations:** `src/kdence/activity/monitor.py` (`ActivityMonitor`, `ActivityState`),
  `src/kdence/activity/__main__.py` (live state printer),
  `tests/activity/test_monitor.py` (synthetic suite).
- **Rationale:** A component that answers "active or idle right now" without assuming the
  idle *unit* — it keys off transitions and times the span with its own clock, applying the
  threshold in pure Python so it is unit-testable with fake timestamps.
- **Action:** *Synthetic:* feed fake transitions/clock, assert active→idle at the threshold,
  back-dating, resume-reset, and sub-threshold flapping. *Live:* the user sits still past a
  short threshold (flips to idle) and presses a key (flips back within one poll). Validated
  when synthetic tests pass headless and the live flip works **using the keyboard alone**.

### Step 1.3 — Regression checkpoint
- **Locations:** whole `tests/` tree.
- **Rationale:** Confirm nothing from Phase 0's scaffold broke once real code landed.
- **Action:** `uv run pytest -m "not live"` (headless suite) all green; `uv run ruff check`
  clean. Validated when green.

> Per phase: once validated, **commit only (do not push)**:
> `[Activity Tracker] (1/8) Complete: Activity detection — Wayland idle source + pure monitor, synthetic + live tests`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Platform notes | Recorded Wayland/Plasma facts + idle-source probe results | `docs/plans/phase-0-platform-notes.md` |
| Wayland idle source | Stdlib-only `ext_idle_notifier_v1` client → `idled`/`resumed` | `src/kdence/activity/wayland_idle.py` |
| Activity monitor | Pure threshold logic over transitions + monotonic clock | `src/kdence/activity/monitor.py` |
| Idle experiment | Step 1.1 harness: logs transitions + running idle seconds | `src/kdence/activity/experiment.py` |
| Live state printer | Step 1.2 live check: prints active/idle + idle seconds | `src/kdence/activity/__main__.py` |
| Synthetic tests | Threshold, back-dating, resume-reset, flapping (headless) | `tests/activity/test_monitor.py` |
| Live smoke test | `@pytest.mark.live`: `idled` fires with no input | `tests/activity/test_wayland_live.py` |
| Protocol reference | Vendored `ext-idle-notify-v1.xml` (provenance of the wire client) | `docs/references/protocols/ext-idle-notify-v1.xml` |
