"""Pure tests for the focus-gated MPRIS tracker (Phase 13.4)."""

from __future__ import annotations

import pytest

from kdence.detail.mpris.tracker import MprisTracker, matches


@pytest.mark.parametrize(
    ("player_id", "app_class", "expected"),
    [
        ("vlc", "vlc", True),
        ("mpv", "mpv", True),
        ("firefox", "firefox", True),
        ("firefox.instance_1_15", "firefox", True),  # source strips to "firefox"; fuzzy anyway
        ("plasma-browser-integration", "firefox", False),
        ("vlc", "org.kde.kate", False),
        ("", "vlc", False),
        ("vlc", None, False),
    ],
)
def test_matches(player_id, app_class, expected) -> None:
    assert matches(player_id, app_class) is expected


def test_fresh_matching_player_is_attributed() -> None:
    t = MprisTracker(ttl_seconds=10.0)
    t.report("vlc", "Artist — Song", at=100.0)
    assert t.detail_for("vlc", now=105.0) == "Artist — Song"


def test_stale_report_is_dropped() -> None:
    t = MprisTracker(ttl_seconds=10.0)
    t.report("vlc", "Song", at=100.0)
    assert t.detail_for("vlc", now=120.0) is None  # older than TTL


def test_non_matching_focus_gets_nothing() -> None:
    t = MprisTracker(ttl_seconds=10.0)
    t.report("vlc", "Song", at=100.0)
    assert t.detail_for("org.kde.kate", now=101.0) is None


def test_forget_removes_a_player() -> None:
    t = MprisTracker(ttl_seconds=10.0)
    t.report("mpv", "Clip", at=100.0)
    t.forget("mpv")
    assert t.detail_for("mpv", now=101.0) is None


def test_freshest_matching_player_wins() -> None:
    t = MprisTracker(ttl_seconds=100.0)
    t.report("chromium", "old", at=100.0)
    t.report("chromium.instance99", "new", at=150.0)
    # Both match "chromium"; the more recent report is used.
    assert t.detail_for("chromium", now=160.0) == "new"


def test_zero_ttl_rejected() -> None:
    with pytest.raises(ValueError):
        MprisTracker(ttl_seconds=0.0)
