"""Pure tests for the MPRIS metadata -> label policy (Phase 13.4)."""

from __future__ import annotations

from kdence.detail.mpris.policy import LOCAL_FILE, label_for


def test_artist_and_title_combine() -> None:
    meta = {"xesam:title": "Redshift", "xesam:artist": ["Floating Points"]}
    assert label_for(meta, "Playing") == "Floating Points — Redshift"


def test_title_only_when_no_artist() -> None:
    assert label_for({"xesam:title": "Some Podcast Ep. 12"}, "Playing") == "Some Podcast Ep. 12"


def test_artist_may_be_a_bare_string() -> None:
    assert label_for({"xesam:title": "T", "xesam:artist": "A"}, "Paused") == "A — T"


def test_stopped_player_has_no_label() -> None:
    assert label_for({"xesam:title": "T"}, "Stopped") is None


def test_empty_metadata_is_none() -> None:
    assert label_for({}, "Playing") is None
    assert label_for(None, None) is None


def test_local_file_url_generalises() -> None:
    meta = {"xesam:url": "file:///home/bdgr/Music/secret.flac"}
    assert label_for(meta, "Playing") == LOCAL_FILE


def test_title_that_is_a_path_generalises() -> None:
    # Some players jam the path into the title; never log it.
    meta = {"xesam:title": "/home/bdgr/Videos/private.mp4"}
    assert label_for(meta, "Playing") == LOCAL_FILE


def test_web_stream_without_title_is_none() -> None:
    # A bare https stream URL with no title carries nothing loggable (the browser-site
    # provider covers hosts; MPRIS is for structured now-playing metadata).
    assert label_for({"xesam:url": "https://stream.example.com/live"}, "Playing") is None


def test_title_wins_over_a_web_url() -> None:
    meta = {"xesam:title": "Live Set", "xesam:url": "https://youtube.com/watch?v=x"}
    assert label_for(meta, "Playing") == "Live Set"
