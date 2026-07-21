"""Pure browser-tab tracker -- the latest active tab per browser engine, focus-gated.

No hardware, no I/O: it just remembers the most recent active-tab *site* each browser engine
reported to the loopback ingest, each stamped with the wall-clock instant it arrived and a
short freshness TTL. The collector asks :meth:`BrowserTabTracker.site_for` once per interval
with the currently focused ``app_class``; it gets a site back only when that class is a known
browser **and** the matching engine's report is still fresh. So a closed tab, a crashed/
unloaded extension, or a non-browser focus never keeps attributing a stale site.

Reports are keyed by *engine* ("gecko" | "chromium"), not by the specific browser, because
that is all the WebExtension can reliably know about itself and all we need to line a report
up with the focused window's ``resourceClass``. Two browsers on the same engine (Firefox and
LibreWolf both open) share one slot -- an accepted ambiguity, since only the focused one is
ever attributed and the compositor's class alone cannot tell same-engine browsers apart.
"""

from __future__ import annotations

from dataclasses import dataclass

# A report older than this is treated as gone (a few collector intervals). Tuned alongside
# the collector interval; the current session's DEFAULT_STALE_AFTER_SECONDS is the sibling.
DEFAULT_TTL_SECONDS = 15.0

# Focused-window ``resourceClass`` (lowercased) -> browser engine. The WebExtension tags each
# POST with its own engine token; mapping the focused class to the same token is what gates
# attribution to the browser that actually holds focus. Extend the sets for more browsers.
BROWSER_CLASSES: dict[str, frozenset[str]] = {
    "gecko": frozenset({"librewolf", "firefox"}),
    "chromium": frozenset({"chromium", "brave-browser", "brave", "google-chrome", "chrome"}),
}

_CLASS_TO_ENGINE: dict[str, str] = {
    cls: engine for engine, classes in BROWSER_CLASSES.items() for cls in classes
}


def engine_for_class(app_class: str | None) -> str | None:
    """The browser engine a focused ``resourceClass`` belongs to, or ``None`` if it is not a
    known browser."""
    if not app_class:
        return None
    return _CLASS_TO_ENGINE.get(app_class.strip().lower())


@dataclass(frozen=True)
class _Report:
    site: str | None
    at: float


class BrowserTabTracker:
    """Latest active-tab site per browser engine, with a freshness TTL.

    Args:
        ttl_seconds: how long a report stays valid. Must be positive.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = float(ttl_seconds)
        self._by_engine: dict[str, _Report] = {}

    def report(self, browser: str, site: str | None, at: float) -> None:
        """Record that ``browser``'s (an engine token) active tab is on ``site`` as of ``at``.

        ``site`` is already the policy-normalised label (:func:`site.normalize_site`), so it is
        a public host, :data:`~kdence.browser.site.LOCAL_APP`, or ``None`` (internal page).
        An unknown engine token is ignored.
        """
        engine = (browser or "").strip().lower()
        if engine not in BROWSER_CLASSES:
            return
        self._by_engine[engine] = _Report(site=site, at=at)

    def site_for(self, app_class: str | None, now: float) -> str | None:
        """The site to attribute to a window of class ``app_class`` at wall-time ``now``.

        ``None`` unless ``app_class`` is a known browser whose engine has a report no older
        than the TTL. A fresh report of ``None`` (an internal browser page) also yields
        ``None`` -- the browser is focused but on nothing loggable.
        """
        engine = engine_for_class(app_class)
        if engine is None:
            return None
        rep = self._by_engine.get(engine)
        if rep is None or (now - rep.at) > self._ttl:
            return None
        return rep.site
