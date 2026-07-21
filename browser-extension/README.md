# KDence Tab Reporter (browser extension)

A tiny WebExtension that tells KDence which **website** is in your active browser tab, so
browser time can be broken down by host in the dashboard's per-application drill-down. It is
the only reliable way to read the active tab's URL on Wayland (the compositor won't tell us).

## What it does — and what it deliberately does not

- On every tab switch, navigation, and window-focus change it reads the **active tab's
  hostname** and `POST`s `{ browser, hostname, scheme }` to `http://127.0.0.1:5786/tab`.
- It sends the **hostname only** — never the path, query string, or fragment. Those are the
  sensitive parts of a URL and they never leave the browser.
- The **only** network destination is `127.0.0.1` (loopback). This is enforced by the
  manifest's host permission (`http://127.0.0.1:5786/*`); the extension cannot reach anything
  off your machine.
- KDence itself then generalises anything local (loopback / private IP / `.local`) to a single
  `"(local app)"` bucket, so private/local work is never logged by name.
- If the KDence collector isn't running, posts fail silently — the extension is harmless when
  nothing is listening.

The collector must be running with its tab-ingest enabled (it is by default; disable with
`--no-ingest`, or move it with `--ingest-port PORT` — match the `ENDPOINT` in the reporter if
you change it).

## Install

Two self-contained builds share one script (identical except an engine tag):

- `gecko/` — **LibreWolf, Firefox** (Manifest V2)
- `chromium/` — **Brave, Chromium, Chrome** (Manifest V3)

### LibreWolf / Firefox (temporary — clears on restart)

1. Open `about:debugging#/runtime/this-firefox`.
2. **Load Temporary Add-on…** → pick `browser-extension/gecko/manifest.json`.

Temporary add-ons are removed when the browser restarts. To keep it loaded permanently you
must package and sign it, or set `xpinstall.signatures.required` to `false` in `about:config`
(LibreWolf allows unsigned add-ons) and install a zipped build.

### Brave / Chromium / Chrome

1. Open `chrome://extensions` (or `brave://extensions`).
2. Enable **Developer mode** (top-right).
3. **Load unpacked** → pick the `browser-extension/chromium/` folder.

## Verify it's working

With the collector running, switch between a couple of real sites and a `localhost` app, then
open the dashboard and expand that browser's row in **Per-application totals** — you should see
the hosts you visited (and a single `(local app)` bucket for the local one). You can also watch
the collector's console: active browser lines gain a `— <host>` suffix.
