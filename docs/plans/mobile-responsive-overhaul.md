# Plan — Mobile responsive overhaul of the live view

**Goal:** the dashboard at `src/kdence/web/static/` reads well on a phone (360–430 px wide)
while the desktop layout stays exactly as it is today.

**Non-goals:** no new panels, no data/API changes, no separate mobile template. One stylesheet,
progressive breakpoints, plus the minimum JS needed for touch (hover-only affordances).

## Breakpoint ladder

| Width | What changes |
|---|---|
| > 1100 px | Desktop — unchanged. |
| ≤ 1100 px | Top-stat strip 9 → 5 columns *(existing)*. |
| ≤ 1000 px | Charts stack; Breakdown donut moves above its list *(existing)*. |
| ≤ 860 px | Page gutters shrink; header stacks brand over badges; range/nav row goes full-width; group editor goes near-full-bleed. |
| ≤ 640 px | Top stats 3 columns; **per-app table reflows from 6 columns to a 3-row card**; hero chart shortens; drill-down bars compress. |
| ≤ 430 px | Top stats 2 columns; tighter type scale; period toggle buttons share the row evenly. |

## Steps

1. **Shell + header** — reduce `.page` padding, stack `.header`, keep the options popover
   inside the viewport (`width: min(320px, 100vw - 24px)`).
   *Validate:* no horizontal scrollbar at 360 px; the ⚙ menu opens fully on-screen.
2. **Controls** — `.nav` becomes full width; `.toggle` groups stretch and their buttons flex
   evenly; touch targets ≥ 34 px tall; the custom-range row wraps cleanly.
   *Validate:* every control is tappable and none overflows at 360 px.
3. **Charts** — shorter hero/donut on small screens; cap `.bd-body` height so the breakdown
   list doesn't run the page length. ECharts already re-renders on `resize`.
   *Validate:* both charts render and stay legible at 360 px.
4. **Per-app table** — at ≤ 640 px drop the column header row and reflow each `.table-row`
   into `swatch | name | time` / `sessions | share` / `bar`, via `grid-template-areas` on the
   existing DOM (no markup change). Drill-down (`.bc-*`) rows compress.
   *Validate:* rows stay aligned, expand/collapse still works, nothing truncates badly.
5. **Touch affordances** — the per-entry ✕ hide button is hover-revealed, which is invisible on
   touch: always show it under `@media (hover: none)`. The breakdown placeholder copy says
   "Hover a column…"; say "Tap a column…" on coarse pointers.
   *Validate:* on a touch viewport the ✕ is visible and the hint reads correctly.
6. **Modal** — group editor full-bleed with a single-column assign grid and stacked new-category row.
   *Validate:* editor usable at 360 px; sticky header still sticks.
7. **Docs + commit** — update `docs/structure.md` / `docs/checklist.md`, run `ruff` + `pytest`,
   commit (no push).

## Verification

- `uv run pytest -m "not live"` — green (no Python touched, this is a regression guard).
- Serve `uv run python -m kdence.api` and inspect at 360×800, 430×930, 768×1024, 1440×900.
- Desktop screenshot compared against the pre-change layout — must be unchanged.
