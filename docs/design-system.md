# Design System — TimeKeeper-v2 Live View

**Derived from the design comp at [`docs/references/frontend/`](references/frontend/README.md)**
(`Activity Tracker.dc.html` + `support.js`). That comp is the visual/interaction target;
this file is the actionable translation the **Phase 6 live view** (`web/`) is built from,
and the **Phase 5 read-back API** is shaped to feed. Treat this as the source of truth for
tokens and layout; treat the comp as the picture of where it should end up.

> Status: **reference captured, not yet implemented.** No `web/` code exists until Phase 6.
> This document exists now so the API (Phase 5) and the view (Phase 6) are designed against
> the same target instead of reverse-engineering the comp later.

## Look and feel

A dark, monospace "activity daemon" terminal dashboard. Header reads
`activity daemon · KDE Plasma · Wayland · read-back · local-only` — the UI wears the
project's honesty motifs (presence ≠ productivity, reader/writer isolation, local-only).

## Design tokens

Observed in the comp; use these exact values.

### Color

| Role | Token | Notes |
|---|---|---|
| Background (base) | `#0a0e0f` | radial highlight toward the top |
| Panel surface | `#0f1416` / `#141b1c` | cards, table rows |
| Panel surface (raised) | `#0d1213` | inset wells |
| Border (neutral) | `#1c2527` | most common border |
| Border (accent) | `#1f3a24` | green-tinted edges on active elements |
| Text (bright) | `#e8f0f1` | headings, current values |
| Text (primary) | `#c8d3d5` | body |
| Text (muted) | `#8a9a9d` / `#7c8b8d` | labels, secondary |
| Text (faint) | `#5f6f71` | axis ticks, captions |
| **Accent — active (green)** | `#3fb950` | the "active" state, primary accent; hover `#56d364` |
| Status — idle (amber) | `#e3b341` | idle / excluded time |

### Categorical palette (per-application charts)

ECharts series colors, in order:
`#3fb950` (green), `#4c9aff` (blue), `#bc8cff` (purple), `#39c5cf` (cyan),
`#f0883e` (orange), `#e3b341` (yellow).

### Typography

`'JetBrains Mono', ui-monospace, monospace`, antialiased. The monospace face is load-bearing
for the terminal aesthetic — keep it everywhere, including numbers.

### Charts

ECharts **5.x** (the comp pins `echarts@5.5.0`). **Local-first caveat:** the comp loads
ECharts and the font from a CDN; the app must **not** — vendor the library and font into
`web/` (or choose a lighter local charting approach) and record the decision in Phase 6.
No network egress is allowed at runtime.

## Layout → data contract

Each panel maps to a read-back API shape. This is the bridge between Phase 5 (API) and
Phase 6 (view): build the endpoints to serve exactly these.

| Panel (comp) | Shows | Backed by (read-back API) |
|---|---|---|
| **Current session** | Focused window (app class; title only if captured), State (active/idle), active time in the current span | "current state" endpoint (Step 5.1) |
| **KPI cards** | Active today, current session length, etc. (`label` / `value` / `sub`) | today's totals (Step 5.1) |
| **Active vs. idle over time** | Timeline of active spans; idle explicitly **excluded** | timeline endpoint (Step 5.1) |
| **Per-application totals** | Table: Application (`cls`/`name`), Time, Sessions, Share % , State | today's per-app totals (Step 5.1) |
| **Application share / distribution** | Donut/bar of per-app share | same per-app totals |
| **Focus timeline · today** | Ordered focus spans across the day | timeline endpoint |
| **Range toggle** | TODAY / WEEK / MONTH | query window param on the endpoints |
| **Date navigation** (added, Phase 9) | Day/Week/Month/Year/Custom + prev/next + date picker over the full history | anchored/custom window params + `/api/extent` + `/api/buckets` (see `phase-9-historical-navigation.md`) |

### Privacy in the UI

The default privacy stance (titles **off** — see build-plan Step 2.2 and
`timekeeper.focus.identity`) means the view shows the **application class**, not window
titles, unless the user has opted into title capture. Design the "Focused window" and
per-app rows to be meaningful with class alone; treat titles as an enhancement, never a
requirement.

## How this gets used

1. **Phase 5** — shape each read-back endpoint to the "backed by" column above.
2. **Phase 6** — implement `web/` against these tokens and panels: a minimal local surface
   served by the API, ECharts vendored locally, no CDN. Keep the comp open beside it as the
   visual target; keep this file as the token/contract source of truth and update it if the
   design shifts during implementation.
