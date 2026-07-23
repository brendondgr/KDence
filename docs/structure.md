# Repository Structure — KDence

This file is the canonical map of the repository. Keep it current whenever directories or
key files are added, moved, or removed.

## Guiding principle: lean root, grow per phase

The root is kept deliberately uncluttered. Only `docs/`, `src/`, and `tests/` exist as
visible top-level folders today. Directories that a build-plan phase will need
(`web/`, `scripts/`, `utils/`, `libs/`, and the `src/kdence/` component subpackages)
are **created when that phase begins**, not pre-scaffolded empty. Their intended homes are
documented below so there is no ambiguity when the time comes.

## Current Tree

```text
TimeKeeper-v2/
├── docs/                          # Source of truth: docs, skills, plans, references
│   ├── documentation.md           # Purpose, stack, architecture, decisions, status
│   ├── structure.md               # This file
│   ├── workflow.md                # Commands, environment, verification, git, handoff
│   ├── checklist.md               # Init Definition of Done + remaining work
│   ├── design-system.md           # Live-view tokens + panel/data contract (from the comp)
│   ├── honesty-review.md          # Step 8.3: what the tracker measures vs. not + known limits
│   ├── plans/
│   │   ├── activity-tracker-build-plan.md   # Authoritative test-driven build order
│   │   ├── phase-0-platform-notes.md        # Recorded Wayland/Plasma + idle/focus facts
│   │   ├── phase-1-activity-detection.md    # Phase 1 implementation plan
│   │   ├── phase-2-focus-detection.md       # Phase 2 implementation plan
│   │   ├── phase-3-live-merge.md            # Phase 3 implementation plan
│   │   ├── phase-4-time-model-and-storage.md # Phase 4 plan + the 4.1 written model design
│   │   ├── phase-5-readback-api.md          # Phase 5 read-back API plan
│   │   ├── phase-6-live-view.md             # Phase 6 live-view plan
│   │   ├── phase-7-productionization.md     # Phase 7 systemd user units + soak plan
│   │   ├── phase-8-integration-review.md    # Phase 8 E2E + regression + honesty-review plan
│   │   └── phase-9-historical-navigation.md # Phase 9 (added scope) date-navigation plan
│   ├── references/
│   │   ├── frontend/              # Live-view design comp (reference only, not app code)
│   │   │   ├── README.md          # What the comp is + observed design tokens
│   │   │   ├── Activity Tracker.dc.html
│   │   │   └── support.js
│   │   └── protocols/
│   │       └── ext-idle-notify-v1.xml       # Vendored spec the idle wire client targets
│   ├── images/                    # Screenshots referenced by the top-level README (dashboard.png)
│   └── skills/                    # Canonical skill definitions (read by all agents)
│       ├── global-project-rules/SKILL.md
│       ├── planner/{SKILL.md, planner.md, SETUP.md}
│       └── repository-structure/{SKILL.md, SETUP.md, structures/*}
├── src/
│   └── kdence/
│       ├── __init__.py            # Package root; subpackages added per phase (see below)
│       ├── activity/             # Phase 1: active-vs-idle detection
│       │   ├── __init__.py        # Public surface (ActivityMonitor, WaylandIdleSource)
│       │   ├── monitor.py         # Pure threshold logic (no hardware) — where correctness lives
│       │   ├── wayland_idle.py    # Stdlib ext_idle_notifier_v1 wire client (hardware side)
│       │   ├── experiment.py      # Step 1.1 idle experiment (python -m kdence.activity.experiment)
│       │   └── __main__.py        # Step 1.2 live state printer (python -m kdence.activity)
│       ├── focus/               # Phase 2: focused-window detection
│       │   ├── __init__.py        # Public surface (WindowIdentity, FocusReporter, KWinFocusSource)
│       │   ├── identity.py        # Pure identity + title-privacy policy (no hardware)
│       │   ├── reporter.py        # Pure "current window" tracker (change-deduped)
│       │   ├── kwin_source.py     # KWin-script loader + dbus-fast receiver (hardware side)
│       │   ├── _service.py        # DBus receiver interface (no future-annotations, for dbus-fast)
│       │   ├── kwin_focus_report.js  # KWin script (callDBus reporter) injected into the compositor
│       │   └── __main__.py        # Step 2.3 live focus printer (python -m kdence.focus)
│       ├── collector/           # Phase 3: merge the live signals (+ Phase 4 --store wiring)
│       │   ├── __init__.py        # Public surface (merge, MergedSample)
│       │   ├── merge.py           # Pure merge rule (idle suppresses the app; carries in-app detail)
│       │   ├── providers.py       # Phase 13: DetailProvider protocol + registry (priority+denylist) + Site/Caption/Mpris providers
│       │   └── __main__.py        # Live merged line; --store persists; runs tab-ingest + detail providers (python -m kdence.collector)
│       ├── browser/             # Browser activity: the active-tab site as a sub-dimension under browsers
│       │   ├── __init__.py        # Public surface (normalize_site, BrowserTabTracker, load_browser_classes, TabIngestServer)
│       │   ├── site.py            # Pure hostname->site policy; local/private -> "(local app)" (no I/O)
│       │   ├── tracker.py         # Pure focus-gated latest-tab-per-engine tracker + config-driven engine map (browsers.json)
│       │   └── ingest.py          # Loopback-only POST /tab receiver feeding the tracker (127.0.0.1)
│       ├── detail/              # Phase 13: in-app detail providers (what you were doing inside an app)
│       │   ├── __init__.py        # Package overview (opt-in, default OFF; generalises browser site)
│       │   ├── caption.py         # Pure window-title -> document/tab label; per-app suffix strip; path -> "(local file)"
│       │   └── mpris/             # MPRIS media detail (structured now-playing over D-Bus)
│       │       ├── __init__.py    # Subpackage overview
│       │       ├── policy.py      # Pure metadata -> "Artist — Title"; file:// -> "(local file)" (no I/O)
│       │       ├── tracker.py     # Pure focus-gated latest-player-per-app tracker with a TTL (no I/O)
│       │       └── source.py      # dbus-fast session-bus poller feeding the tracker (hardware side)
│       ├── model/               # Phase 4: pure time model — where correctness lives
│       │   ├── __init__.py        # Public surface (Span, OpenSpan, Timeline)
│       │   └── timeline.py        # Observations -> honest non-overlapping spans (+ detail/detail_source sub-identity; no hardware/SQL)
│       ├── storage/             # Phase 4: single-writer SQLite under the model
│       │   ├── __init__.py        # Public surface (Store, SpanRow, SpanReader)
│       │   ├── store.py           # SQLite writer (WAL, crash recovery, additive site+detail/detail_source migration); stdlib sqlite3
│       │   ├── reader.py          # Read-only SpanReader (mode=ro) + extent() — writer isolation
│       │   ├── paths.py           # Durable XDG store path (Phase 9) + config paths for categories.json / browsers.json
│       │   └── __main__.py        # Span-store dump / verify (python -m kdence.storage PATH)
│       ├── api/                 # Phase 5: read-back query layer (stdlib http.server)
│       │   ├── __init__.py        # Public surface (queries + serve)
│       │   ├── queries.py         # Pure aggregates + windowing + per-app detail drill-down + per-category group totals
│       │   ├── server.py          # Thin ThreadingHTTPServer, 127.0.0.1; JSON per panel + GET/POST /api/categories
│       │   └── __main__.py        # Run the server (python -m kdence.api --store PATH [--categories PATH])
│       ├── grouping/            # Application grouping: roll per-app totals up into user categories
│       │   ├── __init__.py        # Public surface (palette, Category/CategoryConfig, load/save, ...)
│       │   ├── palette.py         # 12-colour starting palette + pure member-shade variant() (no I/O)
│       │   └── categories.py      # Category config + app->category & site->category maps + defaults; validate + atomic load/save
│       ├── service/              # Phase 7: productionization (systemd user units + soak)
│       │   ├── __init__.py        # Public surface (UnitContext, render_all, summarize)
│       │   ├── units.py           # Pure systemd user-unit renderers (no systemd) — testable
│       │   ├── soak.py            # Pure RSS-slope / flat-verdict summary (no I/O) — testable
│       │   └── __main__.py        # print/install/uninstall/soak CLI (python -m kdence.service)
│       └── web/                 # Phase 6: live view (served by the API at /)
│           ├── __init__.py        # STATIC_DIR resolver
│           └── static/            # dashboard assets, vendored libs (no runtime egress)
│               ├── index.html     # Panels shell (design-system tokens/layout)
│               ├── styles.css     # Tokens/layout translated from the comp
│               ├── fonts.css      # @font-face for the vendored JetBrains Mono
│               ├── app.js         # Polls the API, buckets spans, drives ECharts
│               └── vendor/        # echarts.min.js (5.5.0) + fonts/*.woff2 (committed)
├── tests/
│   ├── __init__.py
│   ├── test_scaffold.py           # Runner sanity check; real suites added per phase
│   ├── activity/                 # Phase 1 suites
│   │   ├── __init__.py
│   │   ├── test_monitor.py        # Synthetic pure-logic tests (headless)
│   │   └── test_wayland_live.py   # @pytest.mark.live idle-source smoke test
│   ├── focus/                    # Phase 2 suites
│   │   ├── __init__.py
│   │   ├── test_identity.py       # Synthetic identity/privacy tests (headless)
│   │   ├── test_reporter.py       # Synthetic reporter-fidelity tests (headless)
│   │   ├── test_kwin_reinject.py  # Phase 13: focus-script liveness re-inject decision (headless)
│   │   └── test_kwin_live.py      # @pytest.mark.live focus-source smoke test
│   ├── collector/                # Phase 3 + Phase 13 suites
│   │   ├── __init__.py
│   │   ├── test_merge.py          # Synthetic merge-rule tests (+ in-app detail) (headless)
│   │   ├── test_providers.py      # Phase 13: registry priority/denylist + Site/Caption providers
│   │   └── test_detail_wiring.py  # Phase 13: --detail-* opt-in default OFF + env fallback
│   ├── detail/                   # Phase 13: in-app detail suites (headless + one live smoke)
│   │   ├── __init__.py
│   │   ├── test_caption.py        # Caption suffix-strip + local-file generalisation
│   │   ├── test_mpris_policy.py   # Metadata -> label; file:// -> (local file); stopped -> None
│   │   ├── test_mpris_tracker.py  # Focus-gated player match + TTL
│   │   └── test_mpris_source.py   # Source helpers headless + @pytest.mark.live bus smoke
│   ├── browser/                  # Browser-activity suites (headless)
│   │   ├── __init__.py
│   │   ├── test_site.py           # Local/private/public hostname classification
│   │   ├── test_tracker.py        # Freshness TTL + focus gating + config-driven engine map
│   │   ├── test_ingest.py         # Loopback POST -> tracker; malformed input; busy-port non-fatal
│   │   └── test_extension_manifests.py  # WebExtension privacy invariants (loopback-only)
│   ├── grouping/                 # Application-grouping suites (headless)
│   │   ├── __init__.py
│   │   ├── test_palette.py        # 12-colour distinctness + variant() ordering
│   │   └── test_categories.py     # Defaults, auto-assign, validation, round-trip
│   ├── model/                    # Phase 4 suites — the critical correctness suite
│   │   ├── __init__.py
│   │   └── test_timeline.py       # The four named honesty cases (a)-(d), headless
│   ├── storage/                  # Phase 4 suites
│   │   ├── __init__.py
│   │   ├── test_store.py          # Persistence + crash-recovery tests (headless)
│   │   └── test_paths.py          # Phase 9: durable XDG default store path
│   ├── api/                      # Phase 5–6 suites (headless — localhost HTTP + SQLite)
│   │   ├── __init__.py
│   │   ├── test_queries.py        # Pure aggregates + windowing + Step 5.2 boundaries + group rollup
│   │   ├── test_categories.py     # /api/categories GET/POST + grouped summary reconciliation
│   │   ├── test_queries_navigation.py # Phase 9: anchored/custom windows + bucket_series
│   │   ├── test_server.py         # Endpoint reconciliation, read/write isolation, static-route serving
│   │   └── test_server_navigation.py # Phase 9: /api/extent, date-aware summary, /api/buckets
│   └── service/                  # Phase 7 suites (headless — unit text + soak math)
│       ├── __init__.py
│       ├── test_units.py          # Unit ordering/restart/durable-store/local-host assertions
│       └── test_soak.py           # Flat vs climbing RSS series verdicts
├── browser-extension/             # WebExtension tab-reporter (hostname -> loopback ingest)
│   ├── gecko/                     # LibreWolf / Firefox build (MV2): manifest.json + tab-reporter.js
│   ├── chromium/                  # Brave / Chromium / Chrome build (MV3): manifest.json + tab-reporter.js
│   └── README.md                  # What it sends (hostname only) + per-browser load steps
├── .claude/skills/                # Claude Code pointers → docs/skills/*
├── .agents/skills/                # OpenAI Codex pointers → docs/skills/*
├── .cursor/rules/                 # Cursor rules (*.mdc) → docs/skills/*
├── install.sh                     # env-driven installer/restarter (reads .env; units + extension + services)
├── .env.example                   # KDENCE_* config contract (ports default 5785/5786) -> copy to .env
├── .python-version                # 3.13
├── pyproject.toml                 # uv project + tooling config
├── uv.lock
├── initialize.md                  # Initialization playbook (retained; see checklist)
├── LICENSE                        # MIT
└── README.md                      # Portfolio front page → overview, install.sh walkthrough, docs/
```

## Planned homes (created per build-plan phase)

| Path | Created in | Purpose |
|---|---|---|
| `src/kdence/activity/` | Phase 1 — **done** (see Current Tree) | Active-vs-idle detection (Wayland idle). |
| `src/kdence/focus/` | Phase 2 — **done** (see Current Tree) | Focused-window reporter (KWin script + DBus). |
| `src/kdence/collector/` | Phase 3 — **done**; Phase 4 added `--store` (see Current Tree) | Merge live signals; `--store PATH` drives the model + writer. |
| `src/kdence/model/` | Phase 4 — **done** (see Current Tree) | Pure time model (no hardware) — the critical logic. |
| `src/kdence/storage/` | Phase 4 — **done**; Phase 5 added `reader.py` (see Current Tree) | Single-writer SQLite datastore (stdlib `sqlite3`, WAL) + read-only reader. |
| `src/kdence/api/` | Phase 5 — **done** (see Current Tree) | Read-back query layer (pure aggregates + stdlib `http.server`). |
| `src/kdence/browser/` | Browser activity — **done** (see Current Tree) | Active-tab site sub-dimension: pure hostname policy + focus-gated tracker + loopback tab-ingest. Engine map extensible via `browsers.json`. |
| `src/kdence/detail/` | In-app detail (Phase 13) — **done** (see Current Tree) | Generic in-app detail providers (caption + MPRIS) behind the collector's provider registry; pure policies/trackers + a `dbus-fast` MPRIS source. Opt-in, default OFF; local paths generalised. |
| `src/kdence/grouping/` | Application grouping — **done** (see Current Tree) | Category config (off the span store) + 12-colour palette + member-shade variants; rolls per-app totals up by category. Config lives in `$XDG_CONFIG_HOME/kdence/categories.json`. |
| `browser-extension/` | Browser activity — **done** (see Current Tree) | Cross-browser WebExtension that POSTs the active tab's hostname to the loopback ingest. Not Python; loaded per browser. |
| `tests/<area>/` | with each area | Purpose-grouped suites mirroring `src`; `tests/model/` is hardware-free and where correctness lives. |
| `src/kdence/web/` | Phase 6 — **done** (see Current Tree) | Live view built from `docs/design-system.md`; **in-package** (served via `STATIC_DIR`, mirroring the `focus/` KWin asset) rather than a top-level `web/`, for robust path resolution. Vendored ECharts + JetBrains Mono (no runtime egress). |
| `src/kdence/service/` | Phase 7 — **done** (see Current Tree) | Session lifecycle: pure systemd **user**-unit renderers + soak sampler/summary + the `install`/`soak` CLI. Kept in-package (importable + unit-testable) rather than as loose `scripts/` files. |
| `scripts/` | (superseded) | Phase 7's lifecycle/soak helpers live in `src/kdence/service/` instead, so no `scripts/` dir was created. |
| `utils/` | as needed | Small cross-cutting helpers. |
| `libs/` | as needed | Shared internal packages (only when genuinely shared). |

## Why Each Existing Top-Level Path Exists

| Path | Purpose |
|---|---|
| `docs/` | Single source of truth: project docs, canonical skills, plans, and references. |
| `src/kdence/` | The application package; grows into the split above as phases land. |
| `tests/` | Test tree; grows purpose-grouped subfolders alongside the code they cover. |
| `.claude/`, `.agents/`, `.cursor/` | Thin per-tool pointers routing to `docs/skills/`. |
| root config | `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example` define the runtime. |
| `LICENSE` | MIT — permissive, portfolio-facing. |
| `README.md` | Portfolio front page: first-person overview, feature/architecture summary, and a step-by-step `install.sh` walkthrough, then routes to `docs/`. |
