# KDence

**A local, privacy-preserving activity tracker for KDE Plasma 6 on Wayland**

![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![Platform: KDE Plasma 6 / Wayland](https://img.shields.io/badge/platform-KDE%20Plasma%206%20%2F%20Wayland-1d99f3)
![Tests: 315 headless](https://img.shields.io/badge/tests-315%20headless-brightgreen)
![Runtime dependencies: 1](https://img.shields.io/badge/runtime%20deps-1-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![No cloud](https://img.shields.io/badge/data-local%20only-lightgrey)

## Overview

I built KDence because I could never find a clean, honest way to see *which windows I was using
and at what point in the day* on my own Linux desktop. The trackers I found were cloud-based,
built for other operating systems, or just never gave a clear picture of where my time on KDE
Plasma was actually going — so I built the thing I wanted. KDence runs quietly from the moment
you log in, watches what's focused and whether you're genuinely at the keyboard, and turns that
into an honest timeline of your day. The goal was that you could install it, forget about it,
and trust it to keep running — no babysitting, no accounts, nothing leaving the machine.

Everything stays local: no cloud, no telemetry, no network egress. It's also deliberately
*honest* about what it measures — presence at a keyboard is not productivity, and the
[honesty review](docs/honesty-review.md) spells out exactly what the numbers do and don't mean,
including the cases where they under-count.

## Demo

![KDence dashboard](docs/images/dashboard.png)

There's no hosted demo, and that's inherent to the project: the dashboard reads a local SQLite
archive populated by a collector that needs a live KDE Plasma 6 / Wayland session. Anything
hosted would be showing fake data. The screenshot above is a real session.

The dashboard is a dark-terminal live view served by the app itself at
`http://127.0.0.1:5785` — per-application and per-category totals, an activity distribution with
an idle overlay, and a Day/Week/Month/Year/Custom navigator over your whole history. It polls
every ~2s, so it tracks reality and freezes when you go idle.

## Tech stack

- **Python 3.13**, managed with [`uv`](https://docs.astral.sh/uv/) — stdlib-first by design.
- **Wayland idle detection** — a hand-written stdlib wire client for the `ext_idle_notifier_v1`
  protocol. No `pywayland`, no CFFI compile, no dependency.
- **KWin focus detection** — a KWin script over `org.kde.kwin.Scripting` reporting the focused
  window out through `callDBus`, received by a small local `dbus-fast` service.
- **Storage** — single-writer SQLite (stdlib `sqlite3`, WAL), read-isolated via `mode=ro`
  connections so the dashboard can never block the collector.
- **Read-back API** — stdlib `http.server` (`ThreadingHTTPServer`) on `127.0.0.1`, JSON per panel.
- **Live view** — static HTML/CSS/JS with **ECharts vendored locally** (no CDN, no runtime egress).
- **Session lifecycle** — systemd **user** units bound to `graphical-session.target`.
- **Browser breakdown** — a cross-browser WebExtension (MV2 + MV3) posting the active tab's
  *hostname only* to a loopback listener.

**`dbus-fast` is the only runtime dependency** — everything above it is standard library or a
vendored static asset.

## Key features

- **Honest time, not raw uptime.** Active spans end at the back-dated last-input instant, so
  trailing idle is never counted, and a suspend gap never becomes phantom hours.
- **Per-app, per-site, per-document breakdowns.** Browsers drill down to per-hostname time;
  opt-in providers add the focused document (window caption) or the playing media track (MPRIS).
- **Your own categories.** Roll apps *and* browser hostnames up into groups (Work,
  Entertainment, Social, …) — a browser's time then splits across categories by site.
- **Full history navigation.** Day / Week / Month / Year / Custom windows over a durable archive
  that survives reboots, with server-side bucketing so a year view never ships every span.
- **Private by construction.** Loopback-only, hostname-only for browsers, window titles off by
  default, in-app detail off by default, and a per-entry ✕ to hide anything you'd rather not see.
- **Set-and-forget.** One `./install.sh` installs systemd user units that auto-start on login and
  restart on failure.

## Requirements

KDence is purpose-built for one desktop and **only runs there**:

- **KDE Plasma 6 on Wayland** — required. It uses Wayland idle detection and a KWin DBus focus
  script, so it will **not** run on X11, GNOME, other desktops, macOS, or Windows.
- **Python 3.13**, managed with `uv`.

The pure time model is desktop-agnostic; only the sensing layer is Plasma-specific, so porting
later means replacing the sensors, not the core.

## Install & run

```bash
git clone https://github.com/brendondgr/TimeKeeper-v2.git
cd TimeKeeper-v2
cp .env.example .env     # optionally edit ports (defaults: API 5785, tab-ingest 5786)
./install.sh             # sets up the env, installs systemd user units, starts everything
```

Then open **`http://127.0.0.1:5785`**. It auto-starts on every graphical login from here on, and
**re-running `./install.sh` is the supported way to restart** with new settings.

For per-website breakdowns, also load the browser extension (`browser-extension/`, see its
[README](browser-extension/README.md)) — no installer can do that for you.

<details>
<summary><b>What <code>install.sh</code> actually does</b></summary>

A single idempotent install/restart path:

1. **Preflight.** Confirms `git`, `systemctl`, and `ss` are present and that you're in a real
   systemd *user* session; warns (but continues) if the session isn't Wayland/KDE.
2. **Ensures `uv`.** Runs the official astral.sh installer if missing (skip with
   `KD_SKIP_UV_INSTALL=1`).
3. **Locates the source.** Uses the checkout it's run from; if piped from `curl` with no
   checkout, clones to `~/.local/share/kdence-src` (or fast-forwards an existing clone).
4. **Reads `.env`.** Your `KDENCE_*` config — ports, host, idle threshold, title capture, detail
   providers, DB path — falling back to defaults if absent.
5. **Verifies the ports — no silent bumps.** Each port must be free *or* already held by
   KDence's own service. A port owned by any **other** process is a hard error naming the `.env`
   key to change. (Deliberate: an earlier silent auto-bump is exactly what once let the
   extension's target port and the collector's ingest port drift apart, recording no site data.)
6. **Syncs the environment.** `uv sync` builds the Python 3.13 venv.
7. **Generates the systemd user units** by calling the project's own **tested** unit renderer
   (`python -m kdence.service install`) — no fragile `sed` templating.
8. **Aligns the browser extension.** Bakes the ingest port into the extension so the two can
   never diverge (a no-op unless you changed it).
9. **Enables and (re)starts the services** (skip with `KD_NO_ENABLE=1`).
10. **Verifies it came up.** Checks both units are `active` and polls `/api/health` until the API
    answers, then prints the dashboard URL and the restart/uninstall commands.

Installer-only overrides: `KD_REPO_URL`, `KD_INSTALL_DIR`, `KD_SKIP_UV_INSTALL=1`, `KD_NO_ENABLE=1`.

To uninstall:

```bash
systemctl --user disable --now kdence-collector.service kdence-api.service
uv run python -m kdence.service uninstall
```

</details>

## Architecture

A clean seam between **hardware-dependent sensing** and **pure, unit-testable logic** is the
core design rule. Correctness lives entirely on the pure side and runs headless with fake
timestamps — which is why a desktop-only project can have a meaningful test suite at all.

```
 hardware-dependent (needs a live Wayland session, little logic)
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │  activity/  │   │   focus/    │   │   detail/   │
   │ active/idle │   │  which app  │   │ what inside │
   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
          └─────────────────┼─────────────────┘
                            ▼
                     ┌─────────────┐   ┌──────────┐  pure logic (no hardware)
                     │ collector/  │──▶│  model/  │  observations → durations
                     └──────┬──────┘   └────┬─────┘
                            ▼               ▼
                     ┌─────────────┐  single-writer SQLite (WAL)
                     │  storage/   │
                     └──────┬──────┘
                            ▼
                     ┌─────────────┐   ┌─────────────┐
                     │    api/     │──▶│  web/ view  │  read-back + live
                     └─────────────┘   └─────────────┘
```

- **`activity/`** — active-vs-idle from the Wayland idle signal (seat-level, one stream).
- **`focus/`** — the focused window's identity, out of KWin via a script + local DBus receiver.
- **`detail/`** — opt-in in-app detail: the focused document (caption) or playing track (MPRIS).
- **`model/`** — the pure time model: observations → non-overlapping honest spans.
- **`storage/`** — single-writer SQLite under the model; crash-safe, read-isolated.
- **`collector/`** — merges the live signals and owns the daemon loop that writes spans.
- **`api/`** — read-back query layer: pure aggregates served by a thin stdlib HTTP server.
- **`web/`** — the live dashboard, served by the API, polling every ~2s.
- **`browser/` + `browser-extension/`** — per-site breakdown via a loopback WebExtension.
- **`grouping/`** — rolls per-app and per-site totals into user categories with a shaded palette.

## Challenges & design decisions

- **No DBus idle on Wayland.** A probe confirmed `GetSessionIdleTime` returns `NotSupported`, so
  `activity/` speaks the `ext_idle_notifier_v1` protocol directly over the Wayland socket using
  only the standard library — no CFFI compile, no `sudo`, no dependency.
- **Getting the focused window out of KWin.** Plasma 6 exposes no DBus property for the active
  window's class, and KWin's script sandbox swallows `print` and has no timers. The fix: a KWin
  script that calls back out via `callDBus` into a small local `dbus-fast` service — the one
  reliable egress, and the project's only runtime dependency. It also re-injects itself if the
  compositor evicts it, because a silently frozen focus source mislabels *hours*, not seconds.
- **Honest durations over raw uptime.** The model back-dates an active span's end to the
  last-input instant and refuses to count heartbeat gaps larger than `max_gap`. This is where
  "presence ≠ productivity" is actually enforced, and it's proven by four named cases in
  `tests/model/`.
- **Growing the schema without a backfill.** The browser-only `site` column was generalised into
  `detail` + `detail_source` via an additive, idempotent migration, with legacy values coalesced
  on read — so months of existing history kept working with no rewrite and no downtime.
- **Stdlib-first, dependencies earned.** Storage, the API, the unit renderer, and the idle client
  add **zero** runtime dependencies; ECharts and the font are vendored, not fetched. Small
  install, tiny attack surface — fitting for a privacy-first tool.

## Developing

```bash
uv sync                        # create the environment and install dev tooling
uv run pytest -m "not live"    # 315 headless tests (correctness lives in tests/model/)
uv run ruff check              # lint
```

Four tests need real hardware, are marked `@pytest.mark.live`, and are excluded from headless
runs. The `tests/focus` live test needs the systemd collector stopped — it owns the
`org.kdence.Focus` bus name by design.

## Documentation

`docs/` is the source of truth:

- [documentation.md](docs/documentation.md) — purpose, stack, architecture, binding decisions, state.
- [structure.md](docs/structure.md) — the repository layout and why each path exists.
- [workflow.md](docs/workflow.md) — commands, the API surface, verification, git rules.
- [honesty-review.md](docs/honesty-review.md) — what the tracker measures vs. not, and its limits.
- [checklist.md](docs/checklist.md) — what's still open.
- [plans/](docs/plans/) — the build record, one file per phase.

## Status

Feature-complete and headless-verified: **315 tests passing**, `ruff` clean, running as systemd
user units against a durable archive. Everything planned is built — sensing, the pure time model,
storage, the read-back API, the dashboard, historical navigation, browser sites, categories,
in-app detail with live toggles, and a mobile-responsive view.

What remains is a set of gates no test can close: they need a human at a real keyboard, and in
two cases a stopwatch or a full working day (logout/login survival, a full-day soak, a cold-start
E2E, in-browser extension attribution). They're enumerated in [checklist.md](docs/checklist.md).

## License

[MIT](LICENSE) — do whatever you like with it.
