"""Pure MPRIS policy -- player metadata in, a storable detail label out (no D-Bus, no I/O).

The hardware side (:mod:`kdence.detail.mpris.source`) unwraps the raw D-Bus variants into a
plain metadata ``dict`` + ``PlaybackStatus`` string and hands them here. This module decides
*what a now-playing item means to this system*: an ``"Artist — Title"`` label, or the generic
:data:`LOCAL_FILE` bucket when the item is a local file (its path must never be logged), or
``None`` when nothing loggable is playing.

Mirrors :mod:`kdence.browser.site` and :mod:`kdence.detail.caption`: the privacy generalisation
(local files → one sentinel) lives in the pure layer so it is unit-testable and cannot be
bypassed by the hardware side.
"""

from __future__ import annotations

from typing import Any

# The bucket a local-file track collapses into -- shared spelling with the caption policy so the
# drill-down shows one "(local file)" label regardless of which provider produced it.
LOCAL_FILE = "(local file)"

# A stopped player has nothing loaded; only Playing/Paused carry a meaningful "what were you on".
_LIVE_STATUSES = frozenset({"Playing", "Paused"})


def _looks_like_path(value: str) -> bool:
    """True when ``value`` is a filesystem path / ``file://`` URL we must not log by name.

    A web URL (``http(s)://``) is **not** a local path -- browser-site attribution covers hosts,
    and a bare web stream carries nothing loggable here -- so it is excluded even though it too
    contains slashes.
    """
    s = value.strip()
    if not s:
        return False
    low = s.lower()
    if low.startswith(("http://", "https://")):
        return False
    return low.startswith("file://") or low.startswith("~") or "/" in s or "\\" in s


def _first(value: Any) -> str | None:
    """MPRIS ``xesam:artist`` is a list; take its first non-empty string. Tolerate a bare str."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def label_for(metadata: dict[str, Any] | None, playback_status: str | None = None) -> str | None:
    """Reduce MPRIS metadata (+ optional ``PlaybackStatus``) to the detail label to store.

    Returns ``"Artist — Title"`` (or just the title), :data:`LOCAL_FILE` when the item is a
    local file with no safe label, or ``None`` when nothing loggable is playing (stopped, empty
    metadata, or a title/url that is only a filesystem path).
    """
    if playback_status is not None and playback_status not in _LIVE_STATUSES:
        return None
    meta = metadata or {}

    title = meta.get("xesam:title")
    title = title.strip() if isinstance(title, str) else None
    url = meta.get("xesam:url")
    url = url.strip() if isinstance(url, str) else None

    if title:
        # A title that is actually a path (some players stuff the filename in here) is generalised.
        if _looks_like_path(title):
            return LOCAL_FILE
        artist = _first(meta.get("xesam:artist"))
        return f"{artist} — {title}" if artist else title

    # No title: a local file collapses to the bucket; a bare web stream has nothing loggable.
    if url and _looks_like_path(url):
        return LOCAL_FILE
    return None
