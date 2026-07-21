# Design System — KDence Live View

**Derived from the design comp at [`docs/references/frontend/`](references/frontend/README.md)**
(`Activity Tracker.dc.html` + `support.js`). That comp is the visual/interaction target;
this file is the actionable translation the **Phase 6 live view** (`web/`) is built from,
and the **Phase 5 read-back API** is shaped to feed. Treat this as the source of truth for
tokens and layout; treat the comp as the picture of where it should end up.

> Status: **implemented.** The live view ships in `src/kdence/web/` (Phase 6), served by
> the API, and Phase 9 added full date navigation on top of it (Day/Week/Month/Year/Custom +
> prev/next + a date picker bounded by the data extent). This document remains the token/panel
> source of truth; update it if the design shifts.

## Look and feel

A dark, monospace terminal dashboard. Header reads
`KDence · activity tracker · KDE Plasma · Wayland · read-back · local-only` — the UI wears the
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

> **Refinement pass (feedback):** the current-session bar and the KPI cards were collapsed
> into a **single compact top-stat strip** (9 tiles); the "Activity distribution" and "Active
> vs. idle over time" charts were **merged** into one (per-app stacked bars + an idle line on
> the shared bucket axis); and "Focus timeline · today" was **removed**. The strip's last four
> tiles are always-live (they poll `/api/current` + today's summary every ~2s and tick each
> second) while the first five + the charts + the table follow the selected window.

| Panel (view) | Shows | Backed by (read-back API) |
|---|---|---|
| **Top-stat strip** (one row) | Active time · Idle time · Focus switches · App views · Longest session (selected window) then Focus window · Stage · Current session · Active today (always live) | `/api/summary` + `/api/buckets` + `/api/timeline` for the window; `/api/current` + `/api/summary?range=today` for the live tiles |
| **Activity distribution · active vs. idle** | Per-app active as stacked bars **plus** an idle line, on the bucket axis | `/api/buckets` (server-bucketed) |
| **Application share** | Donut of per-app share | `/api/summary` per-app totals |
| **Per-application totals** | Table: Application (`cls`/`name`), Sessions, Active time, Share %. **Browser rows expand** to a per-host drill-down; a **By app / By group** toggle rolls totals up by category (category rows expand to member apps in lighter/darker **variants** of the category colour), with an inline **Edit groups** mode | `/api/summary` per-app `apps[]` + `groups[]`; `/api/categories` for the config + palette |
| **Date navigation** (Phase 9) | Day/Week/Month/Year/Custom + prev/next + date picker over the full history | `range`+`date`/`start`+`end` params + `/api/extent` + `/api/buckets` |

### Privacy in the UI

The default privacy stance (titles **off** — see build-plan Step 2.2 and
`kdence.focus.identity`) means the view shows the **application class**, not window
titles, unless the user has opted into title capture. Design the "Focused window" and
per-app rows to be meaningful with class alone; treat titles as an enhancement, never a
requirement.

## How this gets used

1. **Phase 5** — shape each read-back endpoint to the "backed by" column above.
2. **Phase 6** — implement `web/` against these tokens and panels: a minimal local surface
   served by the API, ECharts vendored locally, no CDN. Keep the comp open beside it as the
   visual target; keep this file as the token/contract source of truth and update it if the
   design shifts during implementation.
