# Frontend Reference — Live-View Design Comp

Design reference for the Phase 6 live view. **Reference only — not app code, not a build
target.** The real live view is implemented under `web/` when Phase 6 begins.

## Files

| File | What it is |
|---|---|
| `Activity Tracker.dc.html` | A rendered dark-terminal dashboard mockup of the activity daemon UI. Loads `./support.js` and ECharts from a CDN. |
| `support.js` | The "dc-runtime" that renders the comp (generated bundle; do not edit here). |

> The HTML references `./support.js` by relative path, so the two files must stay in the
> same directory. Open the HTML directly in a browser to view the comp.

## Design tokens observed in the comp (starting point for Phase 6)

- **Type:** JetBrains Mono (monospace), antialiased.
- **Background:** `#0a0e0f` base, with a radial highlight toward the top; panels around `#0f1618`.
- **Text:** primary `#c8d3d5`, muted `#5f6f71` / `#7c8b8d`.
- **Accent (green):** `#3fb950`, hover `#56d364`; subtle borders like `#1f3a24` / `#1c2527`.
- **Charts:** ECharts 5.x.
- **Motifs:** "presence ≠ productivity", reader/writer isolation, local time model — matches
  the honesty caveat in the build plan (Step 8.3).

## How to use it

Treat this as a visual/interaction target, not a spec. These tokens **and** the comp's panel
layout have been translated into **[`docs/design-system.md`](../../design-system.md)** — the
source of truth the Phase 5 API is shaped against and the Phase 6 `web/` view is built from.
Keep the view a minimal local surface backed by the read-back API, and do **not** pull the
CDN dependencies (ECharts, the font) into the app — vendor them locally (the project is
local-first, no runtime network egress).
