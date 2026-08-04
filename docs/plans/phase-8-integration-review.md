# Full Integration Review & End-to-End — Plan (Phase 8)

## 1. Introduction

Phases 1–7 built and validated each part in isolation — activity detection, focus detection,
the pure time model + storage, the read-back API, the live view, and the systemd lifecycle.
Phase 8 is the capstone: prove the *whole* thing is honest end-to-end, that every prior suite
still passes **in one sweep**, and that the system's known measurement limits are written down
so the numbers are never quietly misleading. It adds essentially **no new feature code** — it
is verification and a durable honesty record.

There are three moves, matching the build plan:

- **8.1 Cold-start E2E** — a human, stopwatch in hand, works in three apps for known durations,
  walks away past the threshold, comes back; the API totals must match the stopwatch within one
  poll interval per app, and the away time must be excluded. This is inherently a **live gate**.
- **8.2 Full regression sweep** — every hardware-free suite from Phases 1–7 green *simultaneously*.
  This is the automatable pass and the one point where "works after each step" becomes "works as
  a whole." Live-marked tests are enumerated with the exact conditions a human runs them under.
- **8.3 Honesty review** — not a code test. Record what the system measures vs. what the user
  *means* by "working" (presence ≠ productivity), and log each known limit as an accepted
  trade-off or a future feature, in a discoverable `docs/honesty-review.md`.

## 2. Gaps & Unanswered Questions

- **Live tests vs. the running collector.** The Phase 2/3 live focus tests attach a second focus
  source, but the single-writer collector already owns the `org.kdence.Focus` DBus name (by
  design). So `pytest -m live` for focus must be run with the systemd collector **stopped**
  (`systemctl --user stop kdence-collector`), and the idle live test needs genuine no-input.
  These are recorded as human-run, not part of the headless sweep. *Not a regression — the
  single-focus-source design working.*
- **What "matches the stopwatch" tolerance is.** *Assumption*: within **one poll interval**
  (~2s default, or `--interval`) per app, since a heartbeat lands at most one interval late. The
  back-dating rule (Phase 4.1) means walk-away time is excluded to the last-input instant, not
  detection.
- **8.1 automation.** The stopwatch comparison is a human measurement; no code can stand in for
  it. The plan gives the exact procedure and the one-line API query to read totals back.
- **Scope of the honesty review.** *Assumption*: cover the measurement gaps that can mislead
  (media keeps you "active"; a long read looks "idle"; titles-off means class-only attribution;
  DST skew over long history; suspend handling) — each marked *accepted limit* or *future work*,
  not silently left for the user to rediscover.

## 3. Hierarchical Step-by-Step Instructions

### Step 8.1 — Cold-start end-to-end (live gate, human + stopwatch)
- **Locations**: procedure documented here and in `docs/checklist.md`; no code.
- **Procedure**:
  1. Start clean: `systemctl --user stop kdence-collector kdence-api`, move any existing
     store aside (`mv ~/.local/share/kdence/kdence.db{,.bak}`), then
     `systemctl --user start kdence-collector kdence-api`.
  2. With a stopwatch, work **~2 min in app A**, **~2 min in app B**, **~2 min in app C**
     (e.g. editor, browser, terminal). Then **walk away > 5 min** (past the 300s threshold).
     Come back and work **~1 min** in app A again.
  3. Read totals back:
     `curl -s '127.0.0.1:5785/api/summary?range=today' | python -m json.tool`.
- **Validation / Pass**: each app's reported active time matches your stopwatch within one poll
  interval; the walk-away window is **not** counted; the returning session adds to app A. Record
  the observed vs. expected in the checklist.
- **Action**: no commit (measurement gate); tick the checklist item once observed.

### Step 8.2 — Full regression sweep (automatable)
- **Locations**: whole test tree; results captured in the checklist and the Phase 8 commit body.
- **Validation**:
  - Headless, one pass, all green: `uv run pytest -m "not live"` — every Phase 1–7 hardware-free
    suite (activity, focus, collector, model, storage, api, service).
  - Lint/format clean: `uv run ruff check` and `uv run ruff format --check`.
  - Live suite (human-run, collector stopped / genuine idle): `uv run pytest -m live` — enumerate
    which passed and under what conditions.
- **Pass**: the headless sweep is fully green in a single invocation; the live results are
  recorded with their conditions.
- **Action**: commit (no push): `[Activity Tracker] (8/8) Complete: full regression sweep + integration review`.

### Step 8.3 — Honesty review (written deliverable)
- **Locations**: new `docs/honesty-review.md`; linked from `docs/documentation.md` and
  `docs/checklist.md`.
- **Content**: what the tracker *does* measure (focused-window active time, presence) vs. what it
  does **not** (engagement/productivity); the enumerated known limits each tagged *accepted* or
  *future work*; and the honest one-line framing for the dashboard ("presence ≠ productivity").
- **Validation / Pass**: the doc names each limit a user could otherwise be misled by, and states
  the project's stance on it. Re-read for accuracy against the actual implementation.
- **Action**: fold into the Step 8.2 commit (docs in the same change).

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Cold-start E2E procedure | Exact stopwatch protocol + read-back query; a human gate | this plan + `docs/checklist.md` |
| Regression sweep evidence | Full headless suite green in one pass; live results with conditions | commit body + `docs/checklist.md` |
| Honesty review | Presence ≠ productivity; enumerated known limits (accepted / future) | `docs/honesty-review.md` |
| Docs update | Status → Phases 1–8; link the honesty review | `docs/documentation.md`, `docs/checklist.md` |
