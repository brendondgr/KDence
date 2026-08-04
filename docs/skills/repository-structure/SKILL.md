---
name: repository-structure
description: Use this skill when setting up, restructuring, documenting, or enforcing repository layout in KDence — where new code, tests, assets, and docs belong, and which directories deliberately do not exist.
---

# Repository Structure Standard — KDence

How this repository is laid out and where new work goes. The full annotated tree is
[`docs/structure.md`](../../structure.md) — **that file is the map; this one is the rules.**

## Guiding principle: lean root, grow per need

Directories are created when there is code to put in them, never pre-scaffolded empty. Two
consequences to know before you add anything:

- **There is no `scripts/`.** Session-lifecycle and soak helpers live in `src/kdence/service/`
  so they are importable and unit-testable rather than loose shell files.
- **There is no top-level `web/`.** The live view is packaged at `src/kdence/web/` so
  `STATIC_DIR` resolves from the installed package, mirroring how `focus/` carries its KWin
  script asset.

`utils/` and `libs/` do not exist either. Create them only if genuinely cross-cutting or
genuinely shared code appears — not speculatively.

## Actual top-level layout

```text
root/
├── docs/                # Source of truth: docs, canonical skills, plans, references
├── src/kdence/          # The application package
├── tests/               # Purpose-grouped suites mirroring src/
├── browser-extension/   # The one non-Python component (gecko MV2 + chromium MV3)
├── install.sh           # The single idempotent install/restart path
└── .claude/ .agents/ .cursor/   # Per-tool pointers → docs/skills/
```

## 1. Documentation (`docs/`)

All project documentation lives here, and `docs/structure.md` is **mandatory** — it must be
current whenever directories or key files move. `docs/skills/` holds the canonical skill
definitions every agent reads; `docs/plans/` holds the build record, one file per plan;
`docs/references/` holds read-only external material (the design comp, the vendored Wayland
protocol spec).

> **Out of scope by decision:** heavier web-architecture and accessibility standards. KDence's
> web surface is a minimal local view backed by the read-back API, not a public web app. See
> binding decision 13 in [`docs/documentation.md`](../../documentation.md). Revisit only if the
> view grows into a real front end.

## 2. Application code (`src/kdence/`)

The package is split by the architecture seam — **hardware-dependent sensing on one side, pure
logic on the other** — so correctness can be tested without a live session.

| Package | Role | Side |
|---|---|---|
| `activity/` | Active-vs-idle detection (Wayland idle) | both (`monitor.py` pure, `wayland_idle.py` hardware) |
| `focus/` | Focused-window reporter (KWin script + DBus) | both (`identity.py`/`reporter.py` pure) |
| `detail/` | In-app detail: caption + MPRIS | both (`caption.py`, `mpris/policy.py`, `mpris/tracker.py` pure) |
| `browser/` | Active-tab hostname sub-dimension | mostly pure (`ingest.py` does loopback I/O) |
| `collector/` | Merges signals; owns the daemon loop | `merge.py` pure, `__main__.py` the daemon |
| `model/` | Observations → honest durations | **pure — where correctness lives** |
| `storage/` | Single-writer SQLite under the model | I/O |
| `grouping/` | Per-app totals → user categories | pure |
| `api/` | Read-back query layer | `queries.py` pure, `server.py` a thin shell |
| `web/` | The live dashboard (static assets) | — |
| `service/` | systemd unit renderers + soak | pure renderers, thin CLI |

**When you add code, decide which side it is on first.** If it has logic and touches hardware,
split it into two modules.

## 3. Tests (`tests/`)

Grouped by the area they cover, mirroring `src/kdence/`:

```text
tests/
├── activity/  focus/  detail/  browser/  collector/   # sensing + merge
├── model/                                             # THE critical suite — no hardware
├── storage/  grouping/  api/  service/                # persistence, rollup, read-back, lifecycle
└── test_scaffold.py                                   # runner sanity check
```

- New code in `src/kdence/<area>/` gets tests in `tests/<area>/`.
- Prefer `tests/<area>/test_<behaviour>.py` over one oversized flat folder.
- **Correctness lives in `tests/model/`** — the four named honesty cases. Lean on it hardest;
  it needs no live Wayland session.
- Anything requiring a real KDE/Wayland session is marked `@pytest.mark.live` and excluded from
  headless runs. Keep those to a bare smoke test — logic belongs on the pure side.

## 4. Assets and config

- **Static assets ship inside the package** (`src/kdence/web/static/`,
  `src/kdence/focus/kwin_focus_report.js`) so paths resolve from an installed wheel.
- **Vendored third-party assets are committed**, never fetched at runtime — ECharts and
  JetBrains Mono live under `web/static/vendor/`. No CDN, no runtime egress.
- **User config lives off the span store**, as JSON under `$XDG_CONFIG_HOME/kdence/`
  (`categories.json`, `browsers.json`, `detail.json`). Never add user settings to the SQLite
  span store — that would break the single-writer isolation the read layer depends on.
- **Data lives at `$XDG_DATA_HOME/kdence/kdence.db`.** Never default anything durable to `/tmp`.

## 5. Code guidelines

- **File length:** ideal under 500 lines, hard ceiling 800. Past that, split into modules.
- **Package management:** `uv` only — `uv add`, `uv run`, `uv sync`. Adding a runtime
  dependency needs a recorded justification (`dbus-fast` is currently the only one).
- **Python subpackages need an `__init__.py`**, and it should state the package's public
  surface rather than being empty.

## Before you finish

Any change to the layout updates [`docs/structure.md`](../../structure.md) in the **same
commit**. A tree that lies is worse than no tree at all.
