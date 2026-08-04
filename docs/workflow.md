# Workflow — KDence

Environment, commands, verification, and git rules. Every agent reads this before working
(see [`docs/skills/global-project-rules/SKILL.md`](skills/global-project-rules/SKILL.md)).

## Environment

- **Runtime:** Python 3.13, pinned in `.python-version`.
- **Manager:** `uv` is mandatory. No pip/poetry/conda unless an environment constraint forces
  it — and document the reason if so.
- **Platform:** KDE Plasma 6 on Wayland. The idle and focus paths need a live graphical
  session; those tests are marked `live` and run locally, never in headless CI.
- **Dependencies:** `dbus-fast` is the only runtime dependency. Adding a second one is a
  decision, not a convenience — see binding decision 2 in [documentation.md](documentation.md).

## Everyday commands

| Task | Command |
|---|---|
| Install / sync deps | `uv sync` |
| Add a runtime dep | `uv add <pkg>` |
| Add a dev dep | `uv add --dev <pkg>` |
| Run the full headless suite | `uv run pytest -m "not live"` |
| Run one area | `uv run pytest tests/model` (or `activity`, `focus`, `detail`, `browser`, `collector`, `storage`, `grouping`, `api`, `service`) |
| Run the live tests (needs Wayland/KDE) | `uv run pytest -m live` |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |

## Install, run, restart

| Task | Command |
|---|---|
| **Install / restart everything** | `cp .env.example .env` (edit ports if desired) then `./install.sh`. It reads `.env`, generates and installs the systemd user units, aligns the extension to the ingest port, enables + (re)starts both services, and verifies `/api/health`. **Re-running it *is* the restart.** |
| Open the dashboard | `http://127.0.0.1:5785` |
| Install the units manually | `uv run python -m kdence.service install [--api-port N] [--ingest-port N] [--threshold S] [--store PATH] [--titles] [--detail-providers caption,mpris] [--detail-denylist LIST]`, then `systemctl --user daemon-reload && systemctl --user enable --now kdence-collector.service kdence-api.service` |
| Preview the units without writing | `uv run python -m kdence.service print` |
| Uninstall the units | `systemctl --user disable --now kdence-collector.service kdence-api.service` then `uv run python -m kdence.service uninstall` |
| Soak sampler | `uv run python -m kdence.service soak --interval 60 --out /tmp/soak.jsonl` (Ctrl-C summarizes) |

Installer-only overrides (env vars, not `.env`): `KD_REPO_URL`, `KD_INSTALL_DIR`,
`KD_SKIP_UV_INSTALL=1`, `KD_NO_ENABLE=1`.

## Running components directly (development)

| Task | Command |
|---|---|
| Live activity state | `uv run python -m kdence.activity` |
| Idle experiment | `uv run python -m kdence.activity.experiment` |
| Live focus reporter | `uv run python -m kdence.focus` (`--titles` to capture captions) |
| The collector | `uv run python -m kdence.collector` — persists to the durable XDG store by default; `--no-store` for print-only, `--store PATH` to override |
| The API + dashboard | `uv run python -m kdence.api` (defaults: durable store, `127.0.0.1:5785`) |
| Dump the span store | `uv run python -m kdence.storage ~/.local/share/kdence/kdence.db` |

> **Threshold note:** the *deployed* idle threshold is **300 s**
> (`KDENCE_IDLE_THRESHOLD_SECONDS` in `.env`, passed into the units). Running
> `python -m kdence.collector` bare uses a **5 s** default so a developer sees the idle
> transition without waiting five minutes. Pass `--threshold 300` to match production.

## API surface

All on `127.0.0.1:5785`, all JSON, all loopback-only.

| Method | Route | Returns |
|---|---|---|
| `GET` | `/api/health` | Liveness — what `install.sh` polls |
| `GET` | `/api/current` | Current focus + session state |
| `GET` | `/api/summary` | Totals, per-app `apps[]` (each with `details[]`, browsers also `sites[]`), and `groups[]` |
| `GET` | `/api/timeline` | Raw spans for the window |
| `GET` | `/api/buckets` | Server-bucketed series — what the charts read |
| `GET` | `/api/extent` | The navigable date range of the archive |
| `GET` / `POST` | `/api/categories` | Category config: read / validate + atomically save |
| `GET` / `POST` | `/api/detail` | Detail runtime (providers, denylist, hidden): read / validate + atomically save |

Window parameters on `summary` / `timeline` / `buckets`:
`?range=today|day|week|month|year` optionally with `&date=YYYY-MM-DD` (the period *containing*
that date), or `?start=YYYY-MM-DD&end=YYYY-MM-DD` for a custom window.

```bash
curl -s '127.0.0.1:5785/api/summary?range=today' | python -m json.tool
```

## Features and where they are configured

| Feature | How |
|---|---|
| **Per-site browser breakdown** | Load the WebExtension (`browser-extension/`, see its [README](../browser-extension/README.md)) in each browser — no installer can do this for you. The collector's tab-ingest runs on `127.0.0.1:5786`; `--ingest-port` moves it, `--no-ingest` disables it. Then expand a browser row under *Per-application totals*. |
| **Extend the browser engine map** | Add a browser with no code change: write `$XDG_CONFIG_HOME/kdence/browsers.json` = `{"gecko":["zen"],"chromium":["vivaldi"]}` (unioned onto the bundled default). |
| **In-app detail (opt-in, default OFF)** | Set `KDENCE_DETAIL_PROVIDERS=caption,mpris` in `.env` then `./install.sh`, or pass `--detail-providers`. `caption` = the focused document/file/tab; `mpris` = the playing media track. Exclude sensitive apps with `KDENCE_DETAIL_DENYLIST=org.keepassxc.KeePassXC,…`. Local file paths always generalise to `(local file)`. |
| **Toggle detail live** | Dashboard header → **⚙ Options** → flip **Caption** / **MPRIS**. Writes `$XDG_CONFIG_HOME/kdence/detail.json`; the collector re-reads it each interval and reconfigures without a restart. |
| **Hide a specific entry** | Hover a row in an app's drill-down and click **✕** — e.g. a bank host under Brave. It drops from the drill-down (past *and* future) and the collector stops recording it; the time stays counted under `(other)`. Restore via **⚙ Options → Hidden entries**. Past rows remain on disk — hidden, not deleted (honesty limit #11). |
| **Application grouping** | Dashboard: *Per-application totals* → **By group** toggle + **Edit groups** (create categories, assign apps *and* browser sites, Auto-categorize, Save). A browser's time splits across categories by site. Config: `$XDG_CONFIG_HOME/kdence/categories.json`; `--categories PATH` on the API relocates it. |
| **History navigation** | Dashboard: the Day/Week/Month/Year/Custom selector + prev/next + a date picker bounded by `/api/extent`. |

## Testing

- Tests needing a live Wayland/KDE session carry `@pytest.mark.live` (4 of them). Everything
  else must pass anywhere, headlessly.
- **Correctness lives in `tests/model/`** — the four named honesty cases. Lean on it hardest.
- The `tests/focus` live test needs the systemd collector **stopped**
  (`systemctl --user stop kdence-collector`) because it owns the `org.kdence.Focus` bus name
  by design. The idle live test needs genuine no-input.

Every build-plan step ends with two passes, both required before advancing:

1. **Review** — read what you built and confirm it does what the step intends.
2. **Test** — prove behaviour against an explicit **Pass condition**.

## Documentation maintenance

Update docs in the **same change** that makes them stale:

| File | Update when |
|---|---|
| [structure.md](structure.md) | Directories or key files are added, moved, or removed. |
| [documentation.md](documentation.md) | A binding decision changes, a dependency changes, or the measured state shifts. |
| [workflow.md](workflow.md) | Commands, environment, the API surface, or verification steps change. |
| [checklist.md](checklist.md) | A live gate closes, or new work is discovered. |
| [honesty-review.md](honesty-review.md) | Anything changes what the numbers mean, or a new limit appears. |
| [design-system.md](design-system.md) | Tokens, panels, or the panel→endpoint contract shift. |
| [`docs/plans/`](plans/) | A new plan or handoff note — one file per plan, kept as the build record. |

Test counts appear in exactly two places — [documentation.md](documentation.md) and the root
`README.md`. If you change the suite, update both or neither.

## Git

- Work on a branch; avoid committing straight to a shared `main` without reason.
- **Commit at the end of each validated phase. Commit only — do not push** unless the user
  explicitly asks.
- Commit message format: `[Plan Name] (Current/Total) Complete: <what was done>`.
- AI commits carry a co-author trailer naming the model that wrote them, e.g.
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Handoff: write a note under [`docs/plans/`](plans/) capturing what is done, what is next, and
  any open decisions, so the next agent can continue without re-asking.

## Privacy rules (non-negotiable)

- No network egress. No telemetry. No cloud sync. Ever.
- Anything that could leak defaults to the **more private** option: titles off, detail
  providers off, hostname-only, loopback-only, local paths generalised.
- Window titles and in-app detail leak document names and URLs. Treat every change touching
  them as a privacy decision and record it.

## Supported agent tools

All route to the canonical [`docs/skills/`](skills/) — the pointer files hold no instructions
of their own.

- **Claude Code** — `.claude/skills/<skill>/SKILL.md`
- **OpenAI Codex** — `.agents/skills/<skill>/SKILL.md`
- **Cursor** — `.cursor/rules/<rule>.mdc` (the global rule is `alwaysApply: true`)

To add another tool, mirror the same pointer pattern into that tool's folder. Never duplicate
full instructions — point at `docs/`.
