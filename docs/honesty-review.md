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
| 1 | **Passive consumption reads as idle.** Watching a video, a long read, or listening in a call produces no input; past the 300s threshold it counts as **idle**. | *Under-counts* genuine screen time you'd call "working." | **[accepted]** for a keyboard-driven work tracker. The opt-in **MPRIS detail provider** (Phase 13) now *labels* what was playing while a media app was focused, but it deliberately does **not** turn playback into active time -- inventing "active" from presence-without-input would undercut the honesty this tool rests on. **[future]**: an optional, clearly-separated "presence while playing" span state. |
| 2 | **Presence isn't productivity.** Time spent mindlessly in an app still counts as active. | *Over-counts* low-value busywork relative to its worth. | **[accepted]** — the tool measures presence by design; judging value is the user's. |
| 3 | **Class-only attribution by default (in-app detail is opt-in).** By default non-browser time collapses to the app class — no per-document / per-project split. Two opt-in **detail providers** (Phase 13, default OFF) add a finer breakdown *when the user enables them*: **caption** (the focused window's document/file/tab) and **MPRIS** (the playing media track). Browsers keep their optional **per-host** split (the WebExtension). | Coarser breakdown by default; per-document/track detail only when opted in. | **[accepted]** — class-only stays the private default; each provider is enabled explicitly (`KDENCE_DETAIL_PROVIDERS`), accepting the sensitivity, and honours an app-class denylist. |
| 4 | **Idle threshold is blunt.** A single 300s cutoff decides active vs. away. Pauses shorter than it (thinking, reading a paragraph) count as active; longer ones are excluded. | Short genuine-work pauses are (correctly) kept; the exact cutoff is a judgement call. | **[accepted]** — 300s is the documented default; tunable via `--threshold`. |
| 5 | **Single machine, single seat.** Only this device's graphical session is tracked. Meetings, whiteboards, phone work, or a second machine are invisible. | *Under-counts* work done away from this keyboard. | **[accepted]** — local-only is a core privacy property, not a bug. |
| 6 | **DST / timezone over long history.** Day/week/month windows are interpreted in the machine's *current* local zone at query time; a span crossing a DST boundary can skew by an hour. | Tiny, rare boundary skew in historical windows. | **[accepted]** as a recorded known limit for a personal tracker (Phase 4.1). |
| 7 | **Suspend/resume and crashes.** A heartbeat gap larger than the stitch window is treated as a suspend/stall, not active time; a collector crash leaves the span open, closed to the last heartbeat on read. | Sleeping the machine or a crash does **not** invent phantom active hours. | **[accepted]** — handled and tested (suspend-gap + open-span-on-crash rules). |
| 8 | **Browser sites: presence on a host, not reading it.** A site's active time means that host's tab was focused with recent input — the same presence rule, one level down. It needs the WebExtension loaded (else browser time has no site), records the **hostname only** (no page/path, so two very different pages on one host merge), and collapses all local/private addresses into one `(local app)` bucket. | Same presence≠reading caveat per host; local work is intentionally unlabelled; sub-host detail is not kept. | **[accepted]** — hostname granularity and local generalisation are deliberate privacy choices; the extension is opt-in per browser. |
| 9 | **Caption detail is heuristic and app-specific.** The caption provider parses the window title, stripping a per-app name suffix; unusual titles may be mislabelled or over-trimmed, and it is presence-in-a-document, not reading it (limit #2 again, one level down). Any filesystem path is generalised to `(local file)` — the path is never stored. | Detail labels can be imperfect; local files are intentionally unlabelled. | **[accepted]** — captions are inherently unstructured; opt-in, generalised, denylist-able. |
| 10 | **MPRIS detail is what was loaded, not proof you watched it.** The MPRIS provider labels the focused player's now-playing track (`PlaybackStatus` Playing/Paused); a `file://` track is generalised to `(local file)` (its path never stored). It does **not** add active time (limit #1). | A paused/backgrounded-then-refocused player still labels its last track. | **[accepted]** — structured metadata, opt-in, generalised; presence-as-active stays `[future]`. |
| 11 | **Hiding an entry hides it, it does not delete it.** The drill-down ✕ / *Hidden entries* list stops a value being shown or recorded **going forward** and folds past occurrences into `(other)` at read time — but the original spans (with the value) remain in the SQLite store on disk. | Hidden values still exist in the raw archive; the time is still counted, just relabelled. | **[accepted]** — hide is a display/collection control, not deletion (deleting history would mutate the single-writer store from the read side); true removal would be a separate, explicit destructive action. |

## Bottom line

The number to trust is *"time present and interacting, by app."* Read it as a floor on
keyboard-driven work and a coarse map of where attention went — **not** as a productivity score.
Limits 1 and 2 are the two that most bias a naive reading (passive work under-counts; busywork
over-counts); everything else is small or by design. If future weighting is ever added, it
should be opt-in and clearly separated from this raw, honest presence signal.
