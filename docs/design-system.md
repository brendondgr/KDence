# Design System — KDence Live View

The token and panel contract the dashboard is built from. **This describes what ships**, in
`src/kdence/web/static/`, not an aspiration. The original visual target — the design comp at
[`docs/references/frontend/`](references/frontend/README.md) — remains as a reference for where
the look came from; this file is the source of truth for what it is now.

If the design shifts, update this file in the same change.

## Look and feel

A dark, monospace terminal dashboard. The header wears the project's honesty motifs
(`KDE Plasma · Wayland · read-back · local-only`, and *presence ≠ productivity*), plus a
**⚙ Options** menu on the right.

The monospace face is load-bearing for the aesthetic — keep it everywhere, **including
numbers**.

## Tokens

Colours are literal hex values in `styles.css` (no CSS custom properties). These are the ones in
use; reuse them rather than introducing near-misses.

### Surfaces and text

| Role | Value | Used for |
|---|---|---|
| Background (base) | `#0a0e0f` | page, with a radial highlight toward the top |
| Panel surface | `#0f1416` / `#141b1c` | cards, table rows |
| Panel surface (raised) | `#0d1213` | inset wells |
| Border (neutral) | `#1c2527` | the most common border |
| Border (accent) | `#1f3a24` | green-tinted edges on active elements |
| Text (bright) | `#e8f0f1` | headings, current values |
| Text (primary) | `#c8d3d5` | body |
| Text (muted) | `#8a9a9d` / `#7c8b8d` | labels, secondary |
| Text (faint) | `#5f6f71` | axis ticks, captions |

### Status

| Role | Value |
|---|---|
| **Active (green)** — the primary accent | `#3fb950`, hover `#56d364` |
| **Idle (amber)** — idle / excluded time | `#e3b341` |

Active-green and idle-amber are semantic. Do not reuse them for decoration.

### Two palettes, on purpose

- **Application series** (`app.js`, client-side) — the ECharts categorical order:
  `#3fb950` `#4c9aff` `#bc8cff` `#39c5cf` `#f0883e` `#e3b341`.
- **Categories** (`grouping/palette.py`, **server-side**) — a 12-colour palette
  (red, orange, amber, lime, green, teal, blue, purple, pink, brown, slate, light grey) plus a
  reserved `#6e7681` for **Uncategorized**. Member apps are painted as deterministic lightness
  **variants** of their category's base.

The category palette and the `variant()` maths live on the server so there is exactly one tested
implementation and a swatch always matches the colour the row wears.

### Typography

`'JetBrains Mono', ui-monospace, monospace`, antialiased. Vendored as woff2 under
`static/vendor/fonts/` — weights 400/500/600/700.

### Charts

ECharts **5.5.0**, vendored at `static/vendor/echarts.min.js`. **Nothing loads from a CDN.**
The comp did; the app must not, and no runtime network egress is permitted. Same rule for the
font.

## Panels → endpoints

Each panel maps to a read-back endpoint. This is the API↔view contract; changing a panel's data
needs is a change to both sides.

| Panel | Shows | Backed by |
|---|---|---|
| **Top-stat strip** (one row, 9 tiles) | Active time · Idle time · Focus switches · App views · Longest session — for the *selected window*; then Focus window · Stage · Current session · Active today — **always live** | `/api/summary` + `/api/buckets` + `/api/timeline` for the window; `/api/current` + `/api/summary?range=today` for the live tiles |
| **Activity distribution · active vs. idle** | Per-app active time as stacked bars, plus an idle line, on the shared bucket axis | `/api/buckets` (server-bucketed, so a year view never ships every span) |
| **Application share** | Donut of per-app share, beside a collapsible height-capped breakdown list | `/api/summary` per-app totals |
| **Per-application totals** | Table: Application · Sessions · Active time · Share %. Rows **expand** to a per-detail mini bar chart (browsers show hostnames; every app shows documents/tracks tagged by source). A **By app / By group** toggle rolls totals up by category, with an inline **Edit groups** editor for both apps and browser sites | `/api/summary` `apps[]` (each with `details[]`, browsers also `sites[]`) + `groups[]`; `/api/categories` for config + palette |
| **Date navigation** | Day/Week/Month/Year/Custom + prev/next + a date picker bounded by the archive, plus a NOW button | `range`/`date`/`start`/`end` params + `/api/extent` |
| **⚙ Options menu** | Live toggles for the caption and MPRIS detail providers, and the **Hidden entries** list with restore | `GET`/`POST /api/detail` |

The strip's live tiles and the window-following panels poll independently every ~2s. A failed
fetch flips an **"offline · retrying"** badge, freezes the counters, and keeps polling — it must
recover on its own rather than wedging.

## Responsive behaviour

The **desktop composition is the reference** and must stay byte-identical as widths shrink past
it. Three primary tiers narrow the layout, with component-level adjustments in between:

| Breakpoint | Change |
|---|---|
| `1250 / 1100 / 1000 px` | Component fits: the share panel's basis, the stat strip from 9 to 5 columns, breakdown reflow |
| **`860 px`** | Stacked header; full-width range controls with ≥34 px touch targets |
| **`640 px`** | Stat strip to 3 columns; shorter charts with a capped breakdown list; the per-application table reflows from six columns into a three-row card (**same DOM**, re-placed by `grid-template-areas`); the ⚙ Options popover becomes a bottom sheet |
| **`430 px`** | Stat strip to 2 columns; smaller donut |

Touch: under `@media (hover: none)` the hover-revealed per-entry **✕** is always visible, and
the breakdown hint reads "Tap a column…" instead of "Hover".

**No horizontal overflow at any width.** Wide content scrolls inside its own container.

## Privacy in the UI

Window titles are **off** by default and in-app detail providers are **off** unless the user
opts in (see `kdence.focus.identity` and `kdence.detail`). So:

- Every panel must be meaningful with the **application class alone**. Titles and detail are an
  enhancement, never a requirement.
- A hidden detail value must vanish from the drill-down immediately — past *and* future — while
  its time stays counted under `(other)`.
- Nothing in the view may cause a network request. No CDN, no font host, no analytics, no
  favicon fetch.
