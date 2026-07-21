# Honesty Review — what KDence does and does not measure

Build-plan Step 8.3. Not a code test — a durable record of the gap between what the system
*measures* and what a person *means* by "working," so the numbers are never quietly misleading.
The dashboard wears the one-line version of this in its header ("presence ≠ productivity");
this document is the full accounting behind it.

## What it measures

**Focused-window active time.** For each interval, the system records *which application class
holds focus* and *whether the seat saw input recently* (keyboard, mouse, or touch, together, via
the Wayland idle protocol). Stitched heartbeats become non-overlapping spans; the active→idle
boundary is **back-dated to the last input**, so trailing walk-away time is excluded (Phase 4.1).
The totals answer: *"how long was I present and interacting, in which app."*

## What it does NOT measure

It does not measure engagement, comprehension, output, or value. "Active" means *input happened
while a window was focused* — nothing more. It cannot tell deep work from idle scrolling, nor a
productive hour from a busy one.

## Known limits

Each is tagged **[accepted]** (a deliberate trade-off we keep) or **[future]** (a candidate
feature, recorded so it isn't rediscovered as a surprise).

| # | Limit | Effect on the numbers | Stance |
|---|---|---|---|
| 1 | **Passive consumption reads as idle.** Watching a video, a long read, or listening in a call produces no input; past the 300s threshold it counts as **idle**. | *Under-counts* genuine screen time you'd call "working." | **[accepted]** for a keyboard-driven work tracker. **[future]**: an optional media-aware or "presence without input" weighting. |
| 2 | **Presence isn't productivity.** Time spent mindlessly in an app still counts as active. | *Over-counts* low-value busywork relative to its worth. | **[accepted]** — the tool measures presence by design; judging value is the user's. |
| 3 | **Class-only attribution (titles off by default).** With titles off (the private default, Step 2.2), all time in an app collapses to the app class — no per-document / per-site / per-project split. | Coarser breakdown; can't separate "the report" from "reddit" inside one browser. | **[accepted]** as the private default; opt into `--titles` for finer detail, accepting the sensitivity. |
| 4 | **Idle threshold is blunt.** A single 300s cutoff decides active vs. away. Pauses shorter than it (thinking, reading a paragraph) count as active; longer ones are excluded. | Short genuine-work pauses are (correctly) kept; the exact cutoff is a judgement call. | **[accepted]** — 300s is the documented default; tunable via `--threshold`. |
| 5 | **Single machine, single seat.** Only this device's graphical session is tracked. Meetings, whiteboards, phone work, or a second machine are invisible. | *Under-counts* work done away from this keyboard. | **[accepted]** — local-only is a core privacy property, not a bug. |
| 6 | **DST / timezone over long history.** Day/week/month windows are interpreted in the machine's *current* local zone at query time; a span crossing a DST boundary can skew by an hour. | Tiny, rare boundary skew in historical windows. | **[accepted]** as a recorded known limit for a personal tracker (Phase 4.1). |
| 7 | **Suspend/resume and crashes.** A heartbeat gap larger than the stitch window is treated as a suspend/stall, not active time; a collector crash leaves the span open, closed to the last heartbeat on read. | Sleeping the machine or a crash does **not** invent phantom active hours. | **[accepted]** — handled and tested (suspend-gap + open-span-on-crash rules). |

## Bottom line

The number to trust is *"time present and interacting, by app."* Read it as a floor on
keyboard-driven work and a coarse map of where attention went — **not** as a productivity score.
Limits 1 and 2 are the two that most bias a naive reading (passive work under-counts; busywork
over-counts); everything else is small or by design. If future weighting is ever added, it
should be opt-in and clearly separated from this raw, honest presence signal.
