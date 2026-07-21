"""Browser-activity seam: the active tab's site as a sub-dimension under browsers.

Pure, hardware-free logic lives here -- the site-identity policy (:mod:`site`) and the
focus-gated tab tracker (:mod:`tracker`). The loopback ingest that feeds the tracker from the
WebExtension is :mod:`kdence.browser.ingest` (the I/O side). A browser stays a single
entity in the charts; the site only ever surfaces in the per-application table drill-down.
"""

from __future__ import annotations

from kdence.browser.ingest import DEFAULT_INGEST_PORT, TabIngestServer
from kdence.browser.site import LOCAL_APP, is_local_host, normalize_site
from kdence.browser.tracker import (
    BROWSER_CLASSES,
    BrowserTabTracker,
    engine_for_class,
)

__all__ = [
    "LOCAL_APP",
    "is_local_host",
    "normalize_site",
    "BROWSER_CLASSES",
    "BrowserTabTracker",
    "engine_for_class",
    "DEFAULT_INGEST_PORT",
    "TabIngestServer",
]
