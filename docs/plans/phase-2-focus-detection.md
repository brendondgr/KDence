# Phase 2 — Focus Detection (Implementation Plan)

Derived from [activity-tracker-build-plan.md](activity-tracker-build-plan.md) Phase 2
(Steps 2.1–2.4). Platform facts proven in Step 2.1 are recorded in
[phase-0-platform-notes.md](phase-0-platform-notes.md#focus-source-investigation-feeds-phase-2).

## 1. Introduction

Phase 2 answers: *"which application is focused right now?"* On **KDE Plasma 6 / Wayland**
there is no simple DBus property for the active window's class. The honest channel is a
**KWin script** loaded over `org.kde.kwin.Scripting`, which connects to
`workspace.windowActivated` and calls back out via `callDBus` — the only reliable egress
from KWin's sandboxed engine (`print` is swallowed, timers are unavailable). We host the
receiver as a small **local** DBus service using `dbus-fast` (pure-Python — installs without
a compiler, unlike the rejected `pywayland`).

The pure/hardware seam mirrors Phase 1:

- **`KWinFocusSource`** (hardware) — loads the script, owns the DBus service, forwards raw
  `(resourceClass, caption)`; no identity logic.
- **`WindowIdentity` + `FocusReporter`** (pure) — decide what a window *is* and hold "current
  focused window," fully unit-testable with fake activations.

## 2. Gaps & Unanswered Questions

- **Window identity fields (Step 2.2).** *Decision:* keep the **app class always**; **titles
  are opt-in, default off** (they leak document names and URLs — the global privacy rule).
  `make_identity(..., capture_titles=False)` enforces it.
- **Reporting a switch outside the compositor (Step 2.1).** *Resolved by probe:* `callDBus`
  works; `print`/journal does not; `setTimeout` is unavailable. See platform notes.
- **The two-app manual switch.** Confirming that switching between two *real* apps changes the
  reported identity needs a human (like Phase 1's keyboard-only check). The agent proved the
  read path and a forced activation automatically; the human check is in the handoff.
- **Empty title / desktop (Step 2.3).** Focus on the desktop arrives as a null window → empty
  class → the canonical `NO_WINDOW`. Empty captions collapse to `title=None`. Both covered by
  pure tests.

## 3. Hierarchical Step-by-Step Instructions

### Step 2.1 — Prove the compositor emits focus (gate)
- **Locations:** live probe; facts recorded in `phase-0-platform-notes.md`.
- **Action:** Load a KWin script that reports `workspace.activeWindow` and reacts to
  `workspace.windowActivated`, calling `callDBus` into a throwaway service. Confirm the real
  focused window's identity arrives, and that a change reports a different identity.
- **Pass:** A real focus change seen outside the compositor. **Satisfied.**

### Step 2.2 — Decide and test window identity
- **Locations:** `src/timekeeper/focus/identity.py`, `tests/focus/test_identity.py`.
- **Action:** `WindowIdentity(app_class, title)` + `make_identity` (normalise, collapse empty
  class to `NO_WINDOW`, drop title unless opted in). Assert three windows are stable and
  distinguishable; titles kept only when captured.
- **Pass:** Identities stable/distinguishable; privacy default holds. **Satisfied.**

### Step 2.3 — Focus reporter component
- **Locations:** `src/timekeeper/focus/reporter.py`, `kwin_source.py`, `_service.py`,
  `kwin_focus_report.js`, `__main__.py`; `tests/focus/test_reporter.py`,
  `test_kwin_live.py`.
- **Action:** `FocusReporter` holds current identity, emits `on_change` once per genuine
  switch (no drops), never for a repeat (no duplicates). Edge cases: desktop (no window),
  empty title. Live smoke test proves the source reports the current window.
- **Pass:** No crashes on edge cases; current value always correct; live source reports.
  **Satisfied** (synthetic + live green).

### Step 2.4 — Regression checkpoint
- **Action:** `uv run pytest -m "not live"` — Phase 1 activity tests still pass with focus
  present.
- **Pass:** Nothing from Phase 1 broke. **Satisfied** (30 headless green).

> Commit (do not push):
> `[Activity Tracker] (2/8) Complete: Focus detection — KWin-script focus source + pure identity/reporter`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Window identity | Pure identity + title-privacy policy | `src/timekeeper/focus/identity.py` |
| Focus reporter | Pure "current window" tracker, change-deduped | `src/timekeeper/focus/reporter.py` |
| KWin focus source | KWin-script loader + local DBus receiver (`dbus-fast`) | `src/timekeeper/focus/kwin_source.py` |
| DBus receiver iface | `Report(tag, class, title)` callback object | `src/timekeeper/focus/_service.py` |
| KWin script | `callDBus` reporter injected into the compositor | `src/timekeeper/focus/kwin_focus_report.js` |
| Live printer | `python -m timekeeper.focus` (Step 2.3 demo) | `src/timekeeper/focus/__main__.py` |
| Synthetic tests | Identity + reporter fidelity (headless) | `tests/focus/test_identity.py`, `test_reporter.py` |
| Live smoke test | `@pytest.mark.live`: current window reported | `tests/focus/test_kwin_live.py` |
