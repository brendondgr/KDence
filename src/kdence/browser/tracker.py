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

import json
from dataclasses import dataclass
from pathlib import Path

# A report older than this is treated as gone (a few collector intervals). Tuned alongside
# the collector interval; the current session's DEFAULT_STALE_AFTER_SECONDS is the sibling.
DEFAULT_TTL_SECONDS = 15.0

# Focused-window ``resourceClass`` (lowercased) -> browser engine, the bundled default. The
# WebExtension tags each POST with its own engine token; mapping the focused class to the same
# token is what gates attribution to the browser that actually holds focus. Because both
# extension builds are engine-generic, adding a browser is just adding its class here (or, at
# runtime, in ``browsers.json`` -- see :func:`load_browser_classes`) with **no** code change.
BROWSER_CLASSES: dict[str, frozenset[str]] = {
    "gecko": frozenset({"librewolf", "firefox", "zen", "waterfox", "floorp"}),
    "chromium": frozenset(
        {
            "chromium",
            "brave-browser",
            "brave",
            "google-chrome",
            "chrome",
            "vivaldi-stable",
            "vivaldi",
            "opera",
            "microsoft-edge",
            "edge",
        }
    ),
}

_CLASS_TO_ENGINE: dict[str, str] = {
    cls: engine for engine, classes in BROWSER_CLASSES.items() for cls in classes
}


def load_browser_classes(path: str | Path | None = None) -> dict[str, frozenset[str]]:
    """The engine->classes map, merging an optional ``browsers.json`` onto the bundled default.

    The config is ``{engine: [resourceClass, ...]}``; its classes are **unioned** onto the
    defaults (lowercased), so a user adds ``"zen"`` (or a whole new engine) without a code
    change and never loses the built-ins. A missing, unreadable, or malformed file falls back to
    the defaults untouched -- the map is never returned empty, so browser attribution can't be
    accidentally disabled by a bad config.
    """
    merged: dict[str, set[str]] = {eng: set(classes) for eng, classes in BROWSER_CLASSES.items()}
    if path is not None and Path(path).exists():
        try:
            raw = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            raw = None
        if isinstance(raw, dict):
            for engine, classes in raw.items():
                if not isinstance(engine, str) or not isinstance(classes, (list, tuple)):
                    continue
                bucket = merged.setdefault(engine.strip().lower(), set())
                bucket.update(str(c).strip().lower() for c in classes if str(c).strip())
    return {eng: frozenset(classes) for eng, classes in merged.items() if classes}


def engine_for_class(
    app_class: str | None, browser_classes: dict[str, frozenset[str]] | None = None
) -> str | None:
    """The browser engine a focused ``resourceClass`` belongs to, or ``None`` if not a browser."""
    if not app_class:
        return None
    mapping = _CLASS_TO_ENGINE
    if browser_classes is not None:
        mapping = {cls: eng for eng, classes in browser_classes.items() for cls in classes}
    return mapping.get(app_class.strip().lower())


@dataclass(frozen=True)
class _Report:
    site: str | None
    at: float


class BrowserTabTracker:
    """Latest active-tab site per browser engine, with a freshness TTL.

    Args:
        ttl_seconds: how long a report stays valid. Must be positive.
    """

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        browser_classes: dict[str, frozenset[str]] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = float(ttl_seconds)
        self._by_engine: dict[str, _Report] = {}
        # The engine->classes map this tracker gates on: the caller's (from browsers.json) or
        # the bundled default. Its inverse gates focused-class -> engine attribution.
        self._classes = dict(browser_classes) if browser_classes is not None else BROWSER_CLASSES
        self._class_to_engine = {
            cls: engine for engine, classes in self._classes.items() for cls in classes
        }

    def report(self, browser: str, site: str | None, at: float) -> None:
        """Record that ``browser``'s (an engine token) active tab is on ``site`` as of ``at``.

        ``site`` is already the policy-normalised label (:func:`site.normalize_site`), so it is
        a public host, :data:`~kdence.browser.site.LOCAL_APP`, or ``None`` (internal page).
        An unknown engine token is ignored.
        """
        engine = (browser or "").strip().lower()
        if engine not in self._classes:
            return
        self._by_engine[engine] = _Report(site=site, at=at)

    def site_for(self, app_class: str | None, now: float) -> str | None:
        """The site to attribute to a window of class ``app_class`` at wall-time ``now``.

        ``None`` unless ``app_class`` is a known browser whose engine has a report no older
        than the TTL. A fresh report of ``None`` (an internal browser page) also yields
        ``None`` -- the browser is focused but on nothing loggable.
        """
        if not app_class:
            return None
        engine = self._class_to_engine.get(app_class.strip().lower())
        if engine is None:
            return None
        rep = self._by_engine.get(engine)
        if rep is None or (now - rep.at) > self._ttl:
            return None
        return rep.site
