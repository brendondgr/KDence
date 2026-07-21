# Activity Tracker — Test-Driven Build Plan

A step-by-step plan for building a local, privacy-preserving "how long was I
actually working" tracker for **KDE Plasma 6 on Wayland**. Every step ends with a
**Review** pass (read what you built) and a **Test** pass (prove it behaves),
each with an explicit **Pass condition**. You cannot advance until both are met.

Where a real design decision belongs to you, it is left as a decision — the plan
specifies *what your test must prove*, not what to write.

---

## Guiding principles

- **Separate pure logic from hardware-dependent code.** The time model can be
  fully unit-tested with fake timestamps and needs no Wayland at all. The
  DBus/KWin parts need the live session but carry almost no logic. Keeping that
  seam clean is what makes per-step testing possible.
- **Two platform gates come first.** Steps 1.1 and 2.1 are the only places the
  platform can genuinely block you, so they gate everything after them.
- **Correctness lives in the pure-logic tests (Phase 4).** Lean on those hardest;
  they run without any hardware.
- **Activity is one signal, not two.** On Wayland the compositor tracks input at
  the *seat* level (keyboard + mouse + touch together), which collapses the
  "merge two input streams" problem — but you will *prove* this in Step 1.1
  rather than assume it.

---

## The four sub-problems

The system decomposes into four loosely-coupled parts. Build and test each alone
before wiring them together.

| # | Problem | Depends on hardware? | Where the difficulty is |
|---|---------|----------------------|-------------------------|
| 1 | Activity detection (active vs. idle) | Yes (idle source) | Trusting the idle signal's real behavior |
| 2 | Focus detection (which app) | Yes (compositor) | Getting focus out of the compositor on Wayland |
| 3 | Time model + storage (durations over time) | No | The active→idle boundary rule |
| 4 | Read-back + live view | No | Reader/writer isolation |

---

## Phase 0 — Harness and environment

### Step 0.1 — Confirm platform assumptions
- **Goal:** Eliminate the two things that would invalidate later steps.
- **Review:** Confirm you're on Wayland (not an X11 fallback) and record your
  exact Plasma major version — the window-activation signal was renamed between
  Plasma 5 and 6, and you'll rely on knowing which.
- **Test:** Read session type and compositor version from a terminal; write both
  into a notes file.
- **Pass:** You can state "Wayland, Plasma 6.x" with certainty.

### Step 0.2 — Build the test scaffold before any feature
- **Goal:** A trustworthy place to run assertions.
- **Review:** Decide your test runner and a `tests/` layout.
- **Test:** Write one trivial passing test and one deliberately failing one;
  confirm the runner reports both correctly.
- **Pass:** Green and red both show up as expected. Every later step depends on
  the runner being trustworthy, so this is not optional.

---

## Phase 1 — Activity detection

### Step 1.1 — The five-minute experiment (do this before designing anything)
- **Goal:** Learn the ground truth of your idle source instead of assuming it.
- **Test:** Read the idle value in a tight loop and log it while you
  (a) sit still for 30s, (b) touch **only** the keyboard, (c) move **only** the
  mouse. Record the raw numbers.
- **Pass:** You can answer three questions:
  1. What unit is the value *really* in?
  2. Does it reset on **both** keyboard and mouse independently?
  3. Is it monotonic while idle?
- **Note:** The keyboard-only case is the critical one. If it resets there too,
  your two-input-stream worry is gone and activity is a single signal.

### Step 1.2 — Build the activity monitor
- **Goal:** A component that answers "active or idle right now."
- **Review:** Whatever design you chose (polling the counter vs. subscribing to
  the idle-notify protocol), confirm it does **not** assume the unit you
  *expected* — it must rely on what Step 1.1 actually showed. If the unit is
  unreliable across versions, key your logic off *resets* and time the idle span
  with your own clock.
- **Test (two parts):**
  - *Synthetic (no hardware):* Feed a sequence of fake readings into the decision
    logic; assert it reports active→idle at the right threshold.
  - *Live:* Sit still past your threshold, assert it flips to idle; touch a key,
    assert it flips back within one poll interval.
- **Pass:** Both tests pass, and the live test passed using the **keyboard
  alone**.

### Step 1.3 — Regression checkpoint
- **Test:** Re-run Step 0.2's harness and Step 1.2's unit tests together.
- **Pass:** Nothing from Phase 0 broke.

---

## Phase 2 — Focus detection

### Step 2.1 — Prove the compositor will talk to you at all
- **Goal:** De-risk the hardest part early.
- **Test:** By hand (no daemon yet), get the compositor to emit the currently
  focused window's identity once — to a log or console via whatever channel you
  chose. Switch focus between two apps and confirm the identity changes.
- **Pass:** You've seen a real focus change reported *outside* the compositor.
- **Stop rule:** If this fails, resolve it before writing anything else.
  Everything downstream assumes it works, and Plasma version quirks and
  script-loading issues surface here.

### Step 2.2 — Decide and test your window identity
- **Goal:** Settle what a window *is* to your system.
- **Review:** Choose which fields you keep (app class, title, both) and your
  title-privacy stance — titles leak document names and URLs.
- **Test:** For three deliberately-chosen windows (e.g. a browser, an editor, a
  terminal), assert you get stable, distinguishable identities, and that rapid
  switching neither drops nor duplicates events.
- **Pass:** Identities are stable and switching is captured faithfully.

### Step 2.3 — Build the focus reporter as a standalone component
- **Goal:** A component that always holds "current focused window," updated on
  change.
- **Test:** Run it alone; assert that after any focus change, querying it returns
  the new window within your latency target. Test the edge cases: focus on
  nothing (the desktop), and a window with an empty title.
- **Pass:** No crashes on the edge cases; current value always correct.

### Step 2.4 — Regression checkpoint
- **Test:** Re-run Phase 1 tests.
- **Pass:** Activity detection still works with the focus reporter also running.

---

## Phase 3 — Live merge (still no persistence)

### Step 3.1 — Combine the two live signals
- **Goal:** One process that prints, once per interval, "app X — active/idle."
- **Review:** Confirm the merge rule — when idle, you probably want to suppress
  the app entirely (you're not "in" anything if you're away).
- **Test:** Watch the console line while you work in one app, switch apps, then
  walk away. Assert the line tracks app changes and flips to idle after the
  threshold.
- **Pass:** The live line is trustworthy for several minutes of real use.
- **Stop rule:** Do not proceed until you'd bet money this line is correct.
  Everything stored later is only as good as this signal.

---

## Phase 4 — Time model and storage

### Step 4.1 — Design the model on paper first
- **Goal:** Decide how instantaneous observations become durations *before*
  writing storage.
- **Review:** Sketch your options (stitched heartbeats vs. open/close intervals)
  and pick one. Then work the one case that decides whether your data is honest —
  the active→idle transition — and write down your boundary rule: where does an
  active span truly end when you only *detect* idleness after the timeout?
- **Pass:** You have a written rule for: the end boundary, the day definition,
  suspend-gap handling, and what happens to an open span if the process dies.

### Step 4.2 — Unit-test the time logic with zero hardware
- **Goal:** Prove the model before touching a database.
- **Test:** Feed synthetic event sequences into your model and assert durations.
  Include these named cases explicitly:
  - **(a) Continuous work** for T seconds records ≈ T active.
  - **(b) Work then walk away** — assert the active total does **not** include the
    trailing idle window; the active span ends near last-input, not near
    detection. *(This is the back-dating case, and the one people get wrong.)*
  - **(c) Rapid app switching** produces contiguous, non-overlapping spans that
    sum correctly.
  - **(d) A suspend gap** does not become phantom active time.
- **Pass:** All four assert correctly. This is your most important test suite —
  if it's right, your numbers are trustworthy.

### Step 4.3 — Add the datastore under the tested logic
- **Goal:** Persist what Step 4.2 computes.
- **Review:** Confirm single-writer discipline and that reads won't block or
  corrupt writes.
- **Test:** Run the merged process a few minutes, then query the store directly
  and assert the spans match what you observed live. Kill the process mid-span
  and restart; assert your "open span on crash" rule actually fired (no invented
  hours).
- **Pass:** Stored data matches reality and the crash rule holds.

### Step 4.4 — Regression checkpoint
- **Test:** Re-run Phase 1–3 tests plus Step 4.2.
- **Pass:** All green.

---

## Phase 5 — Read-back API

### Step 5.1 — Build the query layer
- **Goal:** Endpoints for current state, today's per-app totals, and a timeline.
- **Review:** Confirm reads are isolated from the writer.
- **Test:** With the collector writing live, hit each endpoint and assert the
  totals equal what you compute by hand from the raw store for the same window.
  Then the concurrency case: hammer a read endpoint in a loop while the writer is
  active and assert no errors and no stale/garbled rows.
- **Pass:** Every endpoint's numbers reconcile with the raw data, under
  concurrent load.

### Step 5.2 — Boundary tests
- **Test:** Query an empty day, a day with a single open span, and across
  midnight if your day-definition allows.
- **Pass:** No crashes, sensible values, and the day boundary behaves as your
  Step 4.1 rule says.

---

## Phase 6 — Live view

### Step 6.1 — Build the minimal live surface
- **Goal:** See current app, active/idle, and today's total updating.
- **Review:** Match your push mechanism to your real refresh needs — don't build
  streaming for data that changes every two seconds if polling suffices.
- **Test:** Open the view, work in an app, switch, walk away; assert the view
  reflects each within your latency target and the total freezes when idle.
- **Pass:** The view agrees with the API and with reality.

### Step 6.2 — Resilience test
- **Test:** Restart the collector while the view is open; assert the view recovers
  rather than wedging.
- **Pass:** It reconnects or degrades gracefully.

---

## Phase 7 — Productionization

### Step 7.1 — Session lifecycle
- **Goal:** Both processes start with your graphical session, after the
  compositor and DBus are up.
- **Review:** Confirm ordering dependencies.
- **Test:** Log out and back in; assert both come up and data resumes without
  manual steps. Kill one; assert it restarts.
- **Pass:** Survives a full logout/login and a process kill.

### Step 7.2 — Long-run soak test
- **Goal:** Catch slow leaks and drift.
- **Test:** Leave it running a full working day. At the end, assert the totals are
  plausible against your own memory of the day, check memory usage didn't climb
  unboundedly, and confirm suspend/resume during the day didn't corrupt spans.
- **Pass:** Numbers pass the smell test and resources are flat.

---

## Phase 8 — Full integration review and end-to-end test

### Step 8.1 — Cold-start end-to-end
- **Test:** From a clean login with an empty store, work in three apps for known
  short durations (use a stopwatch), walk away past the threshold, come back, work
  again. Assert the API totals match your stopwatch within one poll interval per
  app, and that the away time is excluded.
- **Pass:** Measured reality and reported numbers agree.

### Step 8.2 — Full regression sweep
- **Test:** Run every unit and integration test from Phases 1–7 in one pass.
- **Pass:** All green simultaneously — the only point where "functional after
  every step" becomes "functional as a whole."

### Step 8.3 — Honesty review (not a code test)
- **Goal:** Confirm the system measures what you intend.
- **Review:** Presence isn't productivity — a video keeps you active, a long read
  looks idle. Decide whether that gap matters for your use and record it as a
  known limit or a future weighting feature, so you're not later misled by your
  own numbers.

---

## Build order at a glance

1. **0.1–0.2** — platform confirmed, test runner trustworthy.
2. **1.1** — the five-minute idle experiment (gate).
3. **1.2–1.3** — activity monitor, tested synthetically and live.
4. **2.1** — compositor emits focus (gate).
5. **2.2–2.4** — focus reporter, tested and regression-checked.
6. **3.1** — merged live console line you'd bet money on (gate).
7. **4.1–4.4** — paper model → pure-logic tests → storage under it.
8. **5.1–5.2** — read-back API reconciled against raw data.
9. **6.1–6.2** — live view agreeing with API and reality.
10. **7.1–7.2** — session lifecycle and a full-day soak.
11. **8.1–8.3** — cold-start E2E, full regression sweep, honesty review.

**Two things to internalize:** the pure-logic tests in Step 4.2 are where
correctness actually lives and they need no hardware, so lean on them hardest;
and Steps 1.1 and 2.1 are the two places the platform can block you, which is
exactly why they come first and gate everything after them.
