"""Pure site-identity policy -- a hostname in, a storable site label out (no hardware, no I/O).

This is the logic side of the browser seam. The WebExtension (the hardware-equivalent side)
only ever forwards the active tab's raw *hostname* + scheme to the loopback ingest; deciding
*what a site is to this system* -- a real public host to log by name, or private/local work to
collapse into one generic bucket -- happens here so the decision stays unit-testable, exactly
like :mod:`kdence.focus.identity` does for windows.

Privacy stance (build-plan browser-activity scope): a hostname that resolves to the local
machine -- loopback, an RFC1918 private range, link-local, an mDNS ``.local`` name, or a bare
single-label host with no public TLD -- is **never** logged by name. It becomes the single
:data:`LOCAL_APP` sentinel, because "working on a private/local app" is precisely the thing
the user asked us not to record specifically. Public hosts are normalised (lowercased, a
leading ``www.`` dropped) to the registrable-ish host. Paths, queries and fragments never
reach this module at all -- the extension strips them before the POST.
"""

from __future__ import annotations

import ipaddress

# The one bucket every local/private hostname collapses into; compares equal across the app.
LOCAL_APP = "(local app)"

# Only real web navigations carry a loggable site. Internal pages (``about:``, ``file:``,
# ``chrome:``, ``moz-extension:`` ...) have no public host and are dropped.
_WEB_SCHEMES = frozenset({"http", "https"})


def is_local_host(hostname: str) -> bool:
    """True when ``hostname`` names the local machine / a private network, not a public site.

    Covers loopback (``localhost``, ``127.0.0.0/8``, ``::1``), RFC1918 / unique-local /
    link-local IPs, mDNS ``.local`` names, and bare single-label hosts (no dot -> no public
    TLD, so it cannot be a registrable public domain).
    """
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host == "localhost.localdomain" or host.endswith(".localhost"):
        return True
    if host.endswith(".local"):
        return True
    # IPv6 literals arrive bracketed from ``URL.hostname`` (e.g. "[::1]"); unwrap them.
    ip_str = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Not an IP literal. A dot-less single label ("router", "nas") has no public TLD,
        # so treat it as a local/intranet host rather than logging the name.
        return "." not in host
    return ip.is_loopback or ip.is_private or ip.is_link_local


def normalize_site(hostname: str, scheme: str | None = None) -> str | None:
    """Reduce a raw hostname (+ optional scheme) to the site label this system stores.

    Returns :data:`LOCAL_APP` for anything local/private, the normalised public host
    (lowercased, ``www.`` stripped) otherwise, and ``None`` when there is no loggable site --
    an empty host or a non-web scheme (an internal browser page).
    """
    if scheme is not None and scheme.strip().lower().rstrip(":") not in _WEB_SCHEMES:
        return None
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return None
    if is_local_host(host):
        return LOCAL_APP
    if host.startswith("www."):
        host = host[4:]
    return host or None
