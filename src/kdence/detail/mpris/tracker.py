"""Pure MPRIS tracker -- the latest now-playing label per player, focus-gated with a TTL.

No hardware, no I/O: it remembers the most recent policy-normalised label each MPRIS player
reported (keyed by the player's *identifier* -- the bus-name tail, e.g. ``vlc``, ``mpv``,
``firefox``), each stamped with the instant it arrived and a freshness TTL. The collector asks
:meth:`MprisTracker.detail_for` once per interval with the focused ``app_class``; it gets a
label back only when a **matching** player's report is still fresh. So a closed player, a paused-
long-ago track, or a non-media focus never keeps attributing stale media.

Matching mirrors the browser tracker's engine gating but fuzzier, because an MPRIS bus name and a
window ``resourceClass`` only loosely align (``org.mpris.MediaPlayer2.vlc`` ↔ ``vlc``;
``...firefox.instance123`` ↔ ``firefox``). A player is attributed to the focused window when
either name contains the other after normalisation -- enough to line media up with its window
without cross-attributing unrelated apps.
"""

from __future__ import annotations

from dataclasses import dataclass

# A report older than this is treated as gone (a few collector intervals), matching the browser
# tracker's default so both sub-dimensions age out on the same timescale.
DEFAULT_TTL_SECONDS = 15.0


def _normalise(name: str | None) -> str:
    return (name or "").strip().lower()


def matches(player_id: str, app_class: str | None) -> bool:
    """Whether an MPRIS player identifier lines up with a focused window's ``app_class``."""
    pid = _normalise(player_id)
    cls = _normalise(app_class)
    if not pid or not cls:
        return False
    return pid == cls or pid in cls or cls in pid


@dataclass(frozen=True)
class _Report:
    label: str | None
    at: float


class MprisTracker:
    """Latest now-playing label per MPRIS player, with a freshness TTL.

    Args:
        ttl_seconds: how long a report stays valid. Must be positive.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = float(ttl_seconds)
        self._by_player: dict[str, _Report] = {}

    def report(self, player_id: str, label: str | None, at: float) -> None:
        """Record ``player_id``'s current now-playing ``label`` (already policy-normalised)."""
        pid = _normalise(player_id)
        if not pid:
            return
        self._by_player[pid] = _Report(label=label, at=at)

    def forget(self, player_id: str) -> None:
        """Drop a player that vanished from the bus (its bus name lost its owner)."""
        self._by_player.pop(_normalise(player_id), None)

    def detail_for(self, app_class: str | None, now: float) -> str | None:
        """The now-playing label to attribute to a focused window of ``app_class`` at ``now``.

        ``None`` unless some matching player has a fresh, non-``None`` report. When several
        players match (rare), the freshest wins, so the most recently updated one is used.
        """
        if not app_class:
            return None
        best: _Report | None = None
        for pid, rep in self._by_player.items():
            if not matches(pid, app_class):
                continue
            if (now - rep.at) > self._ttl:
                continue
            if best is None or rep.at > best.at:
                best = rep
        return best.label if best is not None else None
