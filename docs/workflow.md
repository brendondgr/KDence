# Workflow — KDence

Operational rules: environment, commands, documentation maintenance, verification, and
git/handoff. Every agent reads this before working (see
`docs/skills/global-project-rules/SKILL.md`).

## Environment

- **Runtime:** Python 3.13 (pinned in `.python-version`).
- **Manager:** `uv` is mandatory. Do not use pip/poetry/conda unless an environment
  constraint forces it, and document the reason.
- **Platform:** KDE Plasma 6 on Wayland. Some tests (idle/focus) require a live graphical
  session and cannot run in headless CI; they are marked and run locally.

## Commands

| Task | Command |
|---|---|
| Install / sync deps | `uv sync` |
| Add a runtime dep | `uv add <pkg>` |
| Add a dev dep | `uv add --dev <pkg>` |
| Run a module | `uv run python -m kdence.<component>` |
| Live activity state (Phase 1) | `uv run python -m kdence.activity` |
| Idle experiment (Step 1.1) | `uv run python -m kdence.activity.experiment` |
| Live focus reporter (Phase 2) | `uv run python -m kdence.focus` (add `--titles` to capture captions) |
| Live merged line (Phase 3) | `uv run python -m kdence.collector` |
| Persist spans (Phase 4/9) | `uv run python -m kdence.collector` (defaults to the durable XDG store; `--no-store` for print-only, `--store PATH` to override) |
| Browser tab-ingest (browser activity) | runs inside the collector on `127.0.0.1:8766` by default; `--ingest-port PORT` to move it, `--no-ingest` to disable. Needs the WebExtension (`browser-extension/`, see its README) loaded per browser |
| Per-browser site drill-down | in the dashboard, expand a browser row under *Per-application totals*; or `curl -s '127.0.0.1:8765/api/summary?range=today'` and read each browser app's `sites[]` |
| Application grouping (categories) | dashboard: *Per-application totals* → **By group** toggle + **Edit groups** (create categories, assign apps **and browser sites**, Auto-categorize, Save). A browser's time splits across categories by site. Config in `$XDG_CONFIG_HOME/kdence/categories.json` (`assignments` + `site_assignments`); `--categories PATH` on the API to relocate it |
| Read/write categories | `curl -s 127.0.0.1:8765/api/categories` · `curl -X POST 127.0.0.1:8765/api/categories -d @categories.json` (validated + atomically saved) |
| Dump the span store (Phase 4) | `uv run python -m kdence.storage ~/.local/share/kdence/kdence.db` |
| Serve the read-back API + live view (Phase 5–6/9) | `uv run python -m kdence.api` (defaults to the durable XDG store; 127.0.0.1:8765) |
| Open the live view (Phase 6/9) | browse to `http://127.0.0.1:8765/`; use the Day/Week/Month/Year/Custom selector + prev/next to scrub history |
| Query the API (Phase 5) | `curl -s '127.0.0.1:8765/api/summary?range=today' \| python -m json.tool` |
| Query a past period (Phase 9) | `curl -s '127.0.0.1:8765/api/summary?range=month&date=2026-03-15'` / `…?start=2026-02-01&end=2026-05-01` |
| Data extent + buckets (Phase 9) | `curl -s 127.0.0.1:8765/api/extent` · `curl -s '127.0.0.1:8765/api/buckets?range=year&date=2026-01-01'` |
| Preview systemd user units (Phase 7) | `uv run python -m kdence.service print` |
| Install the user units (Phase 7) | `uv run python -m kdence.service install` (writes to `~/.config/systemd/user`; then enable — see below) |
| Enable at login (Phase 7, your step) | `systemctl --user daemon-reload && systemctl --user enable --now kdence-collector.service` (add `kdence-api.service` for the dashboard) |
| Uninstall the user units (Phase 7) | `uv run python -m kdence.service uninstall` |
| Soak sampler (Phase 7) | `uv run python -m kdence.service soak --interval 60 --out /tmp/soak.jsonl` (Ctrl-C to summarize) |
| Run tests | `uv run pytest` |
| Run one area | `uv run pytest tests/activity` (or `tests/focus`, `tests/collector`, `tests/browser`, `tests/grouping`, `tests/model`, `tests/storage`, `tests/api`, `tests/service`) |
| Run hardware-free tests only | `uv run pytest -m "not live"` |
| Run live tests (needs Wayland/KDE) | `uv run pytest -m live` |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |

> Dependencies are added **per build-plan phase**, not all at once. `pyproject.toml` starts
> with only the dev toolchain (`pytest`, `ruff`); runtime deps arrive as their phase begins.
> Phase 1 added **no** runtime dependency — the Wayland idle client is hand-written against
> the wire protocol using only the standard library (`pywayland` was rejected because it
> compiles a CFFI extension needing system dev headers). Phase 2 added **`dbus-fast`** (the
> first runtime dependency) — pure-Python, installs cleanly, used to host the local DBus
> receiver for the KWin focus script. Phase 3 added no dependency. Phase 4 added **no**
> dependency either — the time model is pure Python and the datastore uses stdlib `sqlite3`.
> Phase 5 added **no** dependency too — the read-back API uses stdlib `http.server`
> (`ThreadingHTTPServer`), confirmed over FastAPI at Step 5.1. Phase 6 added **no** Python
> dependency — the live view is static HTML/CSS/JS with **ECharts 5.5.0 and JetBrains Mono
> vendored** into `src/kdence/web/static/vendor/` (committed binaries, no CDN, no runtime
> egress), confirmed over a hand-rolled charting approach at Step 6.1. Phase 7 added **no**
> dependency — session lifecycle is stdlib-rendered systemd **user** units and the soak
> sampler/summary is stdlib-only (`/proc`, `systemctl --user show`). Phase 9 (historical
> navigation) added **no** dependency either — a durable XDG default store path, anchored/custom
> windows + server-side bucketing in the pure query layer, and date-navigation controls in the
> existing vendored-ECharts view. **Browser activity** (added scope) added **no** Python
> dependency — the site policy, tracker, and loopback tab-ingest are stdlib-only, the `site`
> column is an additive SQLite migration, and the tab source is a separate WebExtension
> (`browser-extension/`, loaded per browser) that POSTs the active tab's **hostname only** to
> `127.0.0.1:8766` — loopback-only, no external egress. A pre-existing store is migrated in
> place on first open (the new `site` column is added as nullable; history is preserved).
> **Application grouping** (added scope) added **no** Python dependency — category config is
> stdlib JSON in `$XDG_CONFIG_HOME/kdence/categories.json` (off the span store), the rollup
> and colour maths are pure, and the API's one write endpoint (`POST /api/categories`) validates
> strictly and atomically writes **only** that config file — the span store stays read-only.

### Test markers

- Tests that need a live Wayland/KDE session are marked `@pytest.mark.live`.
- Pure-logic tests (the `tests/model/` suite especially) carry no marker and must always
  pass anywhere. Lean on them for correctness.

## Documentation Maintenance

Update docs in the same change that makes them stale:

- `docs/structure.md` — directories/key files added, moved, or removed.
- `docs/documentation.md` — new decisions, stack/dependency changes, status shifts.
- `docs/workflow.md` — command, environment, or verification changes.
- `docs/checklist.md` — check items off; add newly discovered work.
- `docs/plans/` — new plans and handoff plans; keep the active build plan current.

## Verification Workflow

The build plan is test-driven. **Every step ends with two passes:**

1. **Review** — read what you built and confirm it does what the step intends.
2. **Test** — prove behavior with an explicit **Pass condition**.

Do not advance a step until both pass. Regression checkpoints (Steps 1.3, 2.4, 4.4, 8.2)
re-run prior suites; nothing earlier may break.

Special critical gates:
- **Step 1.1** — the five-minute idle experiment (learn the real idle signal before designing).
- **Step 2.1** — prove the compositor emits focus at all.
- **Step 3.1** — the merged live line you'd "bet money on."
- **Step 4.2** — the pure-logic time-model suite; the back-dating (active→idle) case is the one people get wrong.

## Git & Handoff

- Work on a branch; avoid committing straight to a shared `main` without reason.
- **Commit at the end of each validated phase. Commit only — do not push** unless the user
  explicitly asks.
- Phase commit message format:
  `[Plan Name] (Current/Total) Complete: <what was done>`.
- Co-author trailer for AI commits:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Handoff: write a handoff note under `docs/plans/` capturing what's done, what's next, and
  any open decisions, so another agent can continue without re-asking.

## Supported Agent Tools

Configured (all route to the canonical `docs/skills/`):

- **Claude Code** — `.claude/skills/<skill>/SKILL.md`
- **OpenAI Codex** — `.agents/skills/<skill>/SKILL.md` (same format as Claude)
- **Cursor** — `.cursor/rules/<rule>.mdc` (global rule is `alwaysApply: true`)

To add another tool (Gemini CLI, Antigravity), mirror the same pointer pattern into that
tool's folder — never duplicate full instructions; point to `docs/`.
