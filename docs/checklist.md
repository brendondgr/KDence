# Checklist — KDence

What is **still open**. Everything implemented and headless-verified has been removed from
this file — the build record lives in [`docs/plans/`](plans/), and current measured state is in
[documentation.md](documentation.md).

All code work in the build plan is done: the headless suite passes, `ruff` is clean, and the
systemd units are installed and running against the durable store (measured state, with counts,
is in [documentation.md](documentation.md)). What remains is a set of
gates that **cannot be automated** — they need a human at a real KDE Plasma 6 / Wayland
keyboard, and in several cases a stopwatch or a full working day.

## Live gates (need a human)

Tick these off as you confirm them on your own machine. Each names the thing being proven, not
just the thing being clicked.

### Sensing

- [ ] **Keyboard-only and mouse-only idle reset** (Step 1.1). Go idle past the threshold, then
      resume with *only* the keyboard; repeat with *only* the mouse. Both must flip the state
      back to active. Proves the seat-level assumption the whole activity model rests on.
- [ ] **Focus identity follows a two-app switch** (Step 2.4). Alt-tab between two apps and
      confirm the reported identity changes each time.
- [ ] **Merged line tracks app switches and return-to-active** (Step 3.1). One process, one
      line: the app name follows focus, and typing after a walk-away flips `idle` → `active`.
- [ ] **KWin emits `captionChanged` for the focused window** (Step 13.0). With a focus probe
      running, switch document or tab *within one focused window* and confirm a new caption is
      reported outside the compositor. This gates the caption provider's usefulness on Plasma
      6.7 — nothing headless depends on it.

### Durability

- [ ] **Live persistence and hard-kill recovery** (Step 4.3). Run a few minutes, dump the store
      (`python -m kdence.storage …`), and confirm the spans match what you did. Then
      `kill -9` the collector mid-span, restart, and confirm the open span was closed at its
      **last heartbeat** — not extended to restart time.
- [ ] **Logout/login survival** (Step 7.1). Log out and back in; both units must start and data
      must resume with no manual steps.
- [ ] **Kill → restart** (Step 7.1). `systemctl --user kill kdence-collector.service`; it must
      come back on its own.
- [ ] **Full-day soak** (Step 7.2). Leave both units running a whole working day. At day's end
      the RSS slope must read `flat` (`python -m kdence.service soak`), the API totals must pass
      your own smell test of the day, and a mid-day suspend/resume must leave spans intact.

### The dashboard

- [ ] **The view tracks reality** (Step 6.1). Work, switch apps, walk away. The numbers must
      follow, and the counters must **freeze** when you go idle rather than drifting upward.
- [ ] **The view recovers, not wedges** (Step 6.2). Restart the collector with the dashboard
      open; the "offline · retrying" badge must appear and then clear on its own.
- [ ] **Multi-month scrub over a real archive** (Step 9.3). As your own history grows, scrub
      across months and years and confirm the navigation stays coherent and the totals stay
      believable.

### Added-scope features

- [ ] **Browser extension attribution** (Step 10.4). Load the extension in one Gecko browser and
      one Chromium browser, visit two public sites and one `localhost` app, then confirm the
      drill-down shows the two hostnames plus a single `(local app)` bucket.
- [ ] **Live caption attribution** (Step 13.3). With `caption` enabled, switch documents inside
      one app and watch the detail follow. Separately, confirm an evicted KWin script
      **re-injects** rather than freezing focus and mislabelling hours.
- [ ] **Live MPRIS attribution** (Step 13.4). With `mpris` enabled, play media in a focused
      player and confirm the track appears in the drill-down and clears when it stops — and
      that it does **not** add active time (honesty limit #1).
- [ ] **Real-use detail sanity** (Step 13.7). After a normal day with providers on, confirm the
      per-app detail bars describe what you actually did.

### The measurement gate

- [ ] **Cold-start stopwatch E2E** (Step 8.1). The one that proves the whole pipeline end to
      end. Start from a clean store; work ~2 minutes in each of three apps with a stopwatch;
      walk away > 5 minutes; return. Then:

      ```bash
      curl -s '127.0.0.1:5785/api/summary?range=today' | python -m json.tool
      ```

      **Pass condition:** each app's total matches your stopwatch within one poll interval, and
      the away time is **excluded**. Full procedure in
      [phase-8-integration-review.md](plans/phase-8-integration-review.md).

## Optional / nice to have

- [ ] Add a `.claude/settings.json` permission allowlist to cut permission prompts, if the
      repeated prompts become annoying.
- [ ] Refresh [`docs/images/dashboard.png`](images/dashboard.png) once the dashboard has a full
      real archive behind it — the current capture is from a shorter run.

## Definition of Done

A phase is not complete until:

1. Its **Review** pass (read what you built) and **Test** pass (prove behaviour against an
   explicit Pass condition) have both been met.
2. `uv run pytest -m "not live"` is green and `uv run ruff check` is clean.
3. Every doc the change made stale has been updated in the **same** change — see the
   maintenance table in [workflow.md](workflow.md).
4. Any newly discovered work has been added to this file rather than left in a commit message.

Do not claim completion otherwise.
