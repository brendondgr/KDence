# Repository Structure — KDence

The canonical map of the repository. Keep it current whenever directories or key files are
added, moved, or removed.

**Guiding principle: lean root, grow per need.** Directories are created when code needs
them, never pre-scaffolded empty. Two consequences worth knowing before you add anything:
`scripts/` does not exist (its lifecycle helpers live in the importable, unit-testable
`src/kdence/service/`), and there is no top-level `web/` (the live view is packaged at
`src/kdence/web/` so `STATIC_DIR` resolves from the installed package).

## Tree

```text
TimeKeeper-v2/
├── docs/                            # Source of truth: docs, skills, plans, references
│   ├── documentation.md             # Purpose, stack, architecture, binding decisions, state
│   ├── structure.md                 # This file
│   ├── workflow.md                  # Commands, environment, verification, git
│   ├── checklist.md                 # What is actually still open (the live gates)
│   ├── design-system.md             # Live-view tokens + panel/data contract
│   ├── honesty-review.md            # What the tracker measures vs. not + 11 known limits
│   ├── plans/                       # Build history — how each phase was planned and closed
│   │   ├── activity-tracker-build-plan.md   # The authoritative test-driven build order
│   │   ├── phase-0-platform-notes.md        # Recorded Wayland/Plasma + idle/focus facts
│   │   ├── phase-1-activity-detection.md
│   │   ├── phase-2-focus-detection.md
│   │   ├── phase-3-live-merge.md
│   │   ├── phase-4-time-model-and-storage.md
│   │   ├── phase-5-readback-api.md
│   │   ├── phase-6-live-view.md
│   │   ├── phase-7-productionization.md
│   │   ├── phase-8-integration-review.md
│   │   ├── phase-9-historical-navigation.md
│   │   ├── phase-13-in-app-detail.md
│   │   ├── browser-activity-tracking.md     # Added scope: per-site breakdown
│   │   ├── application-grouping.md          # Added scope: user categories
│   │   ├── site-viz-and-categories.md       # Added scope: site bars + site categories
│   │   ├── dashboard-refinement.md          # Panel/layout refinement pass
│   │   ├── mobile-responsive-overhaul.md    # Mobile breakpoints (desktop unchanged)
│   │   ├── robust-install.md                # The env-driven installer
│   │   └── docs-overhaul.md                 # This documentation audit + rewrite
│   ├── references/
│   │   ├── frontend/                # Live-view design comp (reference only, not app code)
│   │   │   ├── README.md            # What the comp is + observed design tokens
│   │   │   ├── Activity Tracker.dc.html
│   │   │   └── support.js
│   │   └── protocols/
│   │       └── ext-idle-notify-v1.xml       # Vendored spec the idle wire client targets
│   ├── images/
│   │   └── dashboard.png            # Dashboard screenshot used by the root README
│   └── skills/                      # Canonical skill definitions (read by every agent)
│       ├── global-project-rules/SKILL.md
│       ├── planner/{SKILL.md, planner.md}
│       └── repository-structure/SKILL.md
├── src/
│   └── kdence/
│       ├── __init__.py
│       ├── activity/                # Active-vs-idle detection
│       │   ├── __init__.py          # Public surface (ActivityMonitor, WaylandIdleSource)
│       │   ├── monitor.py           # Pure threshold logic (no hardware)
│       │   ├── wayland_idle.py      # Stdlib ext_idle_notifier_v1 wire client (hardware)
│       │   ├── experiment.py        # Idle experiment (python -m kdence.activity.experiment)
│       │   └── __main__.py          # Live state printer (python -m kdence.activity)
│       ├── focus/                   # Focused-window detection
│       │   ├── __init__.py          # Public surface (WindowIdentity, FocusReporter, KWinFocusSource)
│       │   ├── identity.py          # Pure identity + title-privacy policy (no hardware)
│       │   ├── reporter.py          # Pure "current window" tracker (change-deduped)
│       │   ├── kwin_source.py       # KWin-script loader (+ re-inject) & dbus-fast receiver
│       │   ├── _service.py          # DBus receiver interface (no future-annotations, for dbus-fast)
│       │   ├── kwin_focus_report.js # KWin script: windowActivated + captionChanged → callDBus
│       │   └── __main__.py          # Live focus printer (python -m kdence.focus)
│       ├── detail/                  # In-app detail: what you were doing inside an app
│       │   ├── __init__.py          # Package overview (opt-in, default OFF)
│       │   ├── caption.py           # Pure title → document label; path → "(local file)"
│       │   ├── config.py            # detail.json: providers + denylist + hidden[] (UI-written)
│       │   └── mpris/
│       │       ├── __init__.py
│       │       ├── policy.py        # Pure metadata → "Artist — Title" (no I/O)
│       │       ├── tracker.py       # Pure focus-gated latest-player-per-app + TTL (no I/O)
│       │       └── source.py        # dbus-fast session-bus poller (hardware side)
│       ├── browser/                 # Active-tab hostname as a sub-dimension under browsers
│       │   ├── __init__.py          # Public surface (normalize_site, BrowserTabTracker, …)
│       │   ├── site.py              # Pure hostname policy; local/private → "(local app)"
│       │   ├── tracker.py           # Pure focus-gated tracker + engine map (browsers.json)
│       │   └── ingest.py            # Loopback-only POST /tab receiver (127.0.0.1)
│       ├── collector/               # Merge the live signals; own the daemon loop
│       │   ├── __init__.py          # Public surface (merge, MergedSample)
│       │   ├── merge.py             # Pure merge rule (idle suppresses the app; carries detail)
│       │   ├── providers.py         # DetailProvider registry: priority site→mpris→caption
│       │   └── __main__.py          # The daemon (python -m kdence.collector)
│       ├── model/                   # Pure time model — where correctness lives
│       │   ├── __init__.py          # Public surface (Span, OpenSpan, Timeline)
│       │   └── timeline.py          # Observations → honest non-overlapping spans
│       ├── storage/                 # Single-writer SQLite under the model
│       │   ├── __init__.py          # Public surface (Store, SpanRow, SpanReader)
│       │   ├── store.py             # SQLite writer: WAL, crash recovery, additive migration
│       │   ├── reader.py            # Read-only SpanReader (mode=ro) + extent()
│       │   ├── paths.py             # Durable XDG store path + config paths
│       │   └── __main__.py          # Span-store dump / verify (python -m kdence.storage PATH)
│       ├── grouping/                # Roll per-app totals up into user categories
│       │   ├── __init__.py          # Public surface (palette, Category/CategoryConfig, …)
│       │   ├── palette.py           # 12-colour palette + pure member-shade variant()
│       │   └── categories.py        # Category config + app/site maps; validate + atomic save
│       ├── api/                     # Read-back query layer (stdlib http.server)
│       │   ├── __init__.py          # Public surface (queries + serve)
│       │   ├── queries.py           # Pure aggregates, windowing, drill-down, group rollup
│       │   ├── server.py            # Thin ThreadingHTTPServer on 127.0.0.1; JSON per panel
│       │   └── __main__.py          # Run the server (python -m kdence.api)
│       ├── service/                 # Session lifecycle (systemd user units + soak)
│       │   ├── __init__.py          # Public surface (UnitContext, render_all, summarize)
│       │   ├── units.py             # Pure systemd user-unit renderers (no systemd) — testable
│       │   ├── soak.py              # Pure RSS-slope / flat-verdict summary (no I/O)
│       │   └── __main__.py          # print/install/uninstall/soak (python -m kdence.service)
│       └── web/                     # The live view, served by the API at /
│           ├── __init__.py          # STATIC_DIR resolver
│           └── static/
│               ├── index.html       # Panel shell (design-system tokens/layout)
│               ├── styles.css       # Tokens/layout + the mobile tiers (860/640/430)
│               ├── fonts.css        # @font-face for the vendored JetBrains Mono
│               ├── app.js           # Polls the API, buckets spans, drives ECharts
│               └── vendor/          # echarts.min.js (5.5.0) + fonts/*.woff2 (committed)
├── tests/                           # Mirrors src/; headless suites + 4 @pytest.mark.live
│   ├── __init__.py
│   ├── test_scaffold.py             # Runner sanity check
│   ├── activity/                    # monitor (pure) + wayland_live (live)
│   ├── focus/                       # identity, reporter, kwin_reinject (pure) + kwin_live (live)
│   ├── detail/                      # caption, config, mpris policy/tracker/source
│   ├── browser/                     # site, tracker, ingest, extension manifest invariants
│   ├── collector/                   # merge, providers, detail wiring, detail runtime
│   ├── model/                       # the four named honesty cases — the critical suite
│   ├── storage/                     # persistence, crash recovery, durable paths
│   ├── grouping/                    # palette distinctness, category defaults + round-trip
│   ├── api/                         # queries, navigation, server, categories, detail API
│   └── service/                     # unit-file content, soak-slope verdicts
├── browser-extension/               # WebExtension tab-reporter (hostname → loopback ingest)
│   ├── gecko/                       # LibreWolf / Firefox (MV2): manifest.json + tab-reporter.js
│   ├── chromium/                    # Brave / Chromium / Chrome (MV3): same two files
│   └── README.md                    # What it sends + per-browser load steps
├── .claude/skills/                  # Claude Code pointers → docs/skills/*
├── .agents/skills/                  # OpenAI Codex pointers → docs/skills/*
├── .cursor/rules/                   # Cursor rules (*.mdc) → docs/skills/*
├── install.sh                       # The single idempotent install/restart path
├── .env.example                     # KDENCE_* config contract → copy to .env
├── .python-version                  # 3.13
├── pyproject.toml                   # uv project + pytest/ruff config
├── uv.lock
├── LICENSE                          # MIT
└── README.md                        # Portfolio front page → overview, install, docs/
```

## Why each top-level path exists

| Path | Purpose |
|---|---|
| `docs/` | Single source of truth: project docs, canonical skills, plans, references. |
| `src/kdence/` | The application package, split by the architecture seam (see [documentation.md](documentation.md)). |
| `tests/` | Purpose-grouped suites mirroring `src/`. `tests/model/` is hardware-free and is where correctness actually lives. |
| `browser-extension/` | The one non-Python component: a cross-browser tab reporter, loaded manually per browser. |
| `.claude/`, `.agents/`, `.cursor/` | Thin per-tool pointers routing to `docs/skills/`. Never the only copy of anything. |
| `install.sh`, `.env.example` | The supported install/restart path and its configuration contract. |
| `pyproject.toml`, `uv.lock`, `.python-version` | Define the runtime. |
| `LICENSE`, `README.md` | MIT; portfolio-facing front page. |

## Conventions for new code

- **Mirror the seam.** Pure logic goes in a module with no I/O and gets a headless test.
  Hardware access goes in a separate module and gets a `@pytest.mark.live` smoke test at most.
- **Mirror the tree.** New code in `src/kdence/<area>/` gets tests in `tests/<area>/`.
- **File length.** Keep files under ~500 lines; ~800 is the hard ceiling. Past that, split.
- **New directories.** Create one only when there is code to put in it, and add it here in the
  same change.
- **Never add a runtime dependency casually** — see binding decision 2.
