"""In-app detail providers -- what you were doing *inside* a focused app.

Generalises the browser-only ``site`` sub-dimension (``kdence.browser``) to non-browser apps.
Each detail source has a pure policy module here (hardware-free, unit-tested) and a thin
hardware adapter wired into the collector:

- :mod:`kdence.detail.caption` -- the focused window's title, parsed per-app (Tier 1).
- :mod:`kdence.detail.mpris` -- structured media metadata over D-Bus (Tier 2).

All of it is **opt-in and default OFF** (privacy), gated by ``KDENCE_DETAIL_PROVIDERS`` and an
app-class denylist; local file paths never leave the machine by name (they collapse to a
generic bucket), exactly as :mod:`kdence.browser.site` collapses local hosts.
"""
