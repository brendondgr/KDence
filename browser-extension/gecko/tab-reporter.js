/* KDence tab-reporter (Gecko build: LibreWolf / Firefox).
 *
 * Reports ONLY the active tab's hostname + scheme to the KDence collector's loopback
 * ingest, so browser time can be attributed to a site in the per-application drill-down.
 * Privacy: no path, query, or fragment is ever read or sent; the only network target is
 * 127.0.0.1 (declared in the manifest). If the collector isn't running, posts fail quietly.
 *
 * This file is identical to the Chromium build's copy except for KDENCE_ENGINE below --
 * keep the two in sync when editing.
 */
const KDENCE_ENGINE = "gecko";
const ENDPOINT = "http://127.0.0.1:8766/tab";

const api = typeof browser !== "undefined" ? browser : chrome;

function hostAndScheme(url) {
  try {
    const u = new URL(url);
    return { hostname: u.hostname, scheme: u.protocol.replace(/:$/, "") };
  } catch (e) {
    return { hostname: "", scheme: "" };
  }
}

function post(hostname, scheme) {
  // Fire-and-forget to loopback only; swallow every failure (collector may be down).
  try {
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ browser: KDENCE_ENGINE, hostname: hostname, scheme: scheme }),
      keepalive: true,
    }).catch(function () {});
  } catch (e) {
    /* ignore */
  }
}

function reportActive() {
  // The active tab of the currently focused browser window.
  api.tabs.query({ active: true, lastFocusedWindow: true }, function (tabs) {
    const tab = tabs && tabs[0];
    if (!tab || !tab.url) {
      post("", ""); // browser focused but on an internal page -> no loggable site
      return;
    }
    const hs = hostAndScheme(tab.url);
    post(hs.hostname, hs.scheme);
  });
}

api.tabs.onActivated.addListener(reportActive);
api.tabs.onUpdated.addListener(function (id, info) {
  if (info.url || info.status === "complete") reportActive();
});
api.windows.onFocusChanged.addListener(reportActive);
// Report once on load so the collector isn't blank until the first switch.
reportActive();
