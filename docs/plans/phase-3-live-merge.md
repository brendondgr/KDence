# Phase 3 — Live Merge (Implementation Plan)

Derived from [activity-tracker-build-plan.md](activity-tracker-build-plan.md) Phase 3
(Step 3.1). Short by design: the two hard signals already exist (Phases 1–2); this phase
only combines them. **No persistence yet** — that is Phase 4.

## 1. Introduction

One process, one asyncio loop, both live signals:

- the Wayland idle source drives the pure `ActivityMonitor` (its socket integrated with
  `loop.add_reader`);
- the KWin focus source drives the pure `FocusReporter`.

Once per interval it prints the merged line. The only new logic is the **merge rule**, kept
pure and testable in `collector/merge.py`.

## 2. The merge rule (Step 3.1 review)

**When idle, suppress the app entirely** — you are not "in" anything if you have walked
away. While active, the line carries the focused app (and title, if captured). The bare
desktop while active is reported as active-but-appless (`(desktop) — active`). Idle prints
`— idle` with no app.

This is the signal everything stored later depends on, so it is proven live (Step 3.1 stop
rule) *and* unit-tested:

- **Synthetic:** `merge(state, identity)` — idle suppresses the app; active reports it;
  desktop is appless; titles appear only when present. (`tests/collector/test_merge.py`.)
- **Live:** `python -m timekeeper.collector` prints the focused app while active and flips to
  `— idle` after the threshold. Verified: the line tracked `com.anthropic.Claude — active`,
  then `— idle` ~4s after input stopped.

## 3. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Merge rule | Pure `merge()` + `MergedSample` (idle suppresses app) | `src/timekeeper/collector/merge.py` |
| Live merge process | `python -m timekeeper.collector` — one asyncio loop, both signals | `src/timekeeper/collector/__main__.py` |
| Synthetic tests | Merge-rule cases (headless) | `tests/collector/test_merge.py` |

## 4. Manual / live checks (handoff)

The agent cannot synthesise real input or GUI focus switches, so these stay human checks:

- **App-switch tracking:** run `uv run python -m timekeeper.collector`, work in one app,
  switch to another — the line should follow the app class.
- **Return-to-active via keyboard:** after it flips to `— idle`, press a key — it should
  return to `app — active` within one interval (the seat-level activity claim, same as
  Phase 1's keyboard-only check).

> Commit (do not push):
> `[Activity Tracker] (3/8) Complete: Live merge — one process printing app + active/idle`.
