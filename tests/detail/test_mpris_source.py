"""Tests for the MPRIS source: pure helpers headless, a live smoke test behind the marker."""

from __future__ import annotations

import asyncio

import pytest

from dbus_fast import Variant

from kdence.detail.mpris.source import MprisSource, _unwrap, player_identifier
from kdence.detail.mpris.tracker import MprisTracker


@pytest.mark.parametrize(
    ("bus_name", "expected"),
    [
        ("org.mpris.MediaPlayer2.vlc", "vlc"),
        ("org.mpris.MediaPlayer2.mpv", "mpv"),
        ("org.mpris.MediaPlayer2.firefox.instance_1_15", "firefox"),
        ("org.mpris.MediaPlayer2.chromium.instance1234", "chromium"),
        ("org.mpris.MediaPlayer2.Elisa", "elisa"),
    ],
)
def test_player_identifier_strips_prefix_and_instance(bus_name, expected) -> None:
    assert player_identifier(bus_name) == expected


def test_unwrap_flattens_variants_and_containers() -> None:
    raw = Variant(
        "a{sv}",
        {
            "xesam:title": Variant("s", "Song"),
            "xesam:artist": Variant("as", ["A", "B"]),
            "mpris:length": Variant("x", 1000),
        },
    )
    assert _unwrap(raw) == {
        "xesam:title": "Song",
        "xesam:artist": ["A", "B"],
        "mpris:length": 1000,
    }


def test_refresh_without_connect_is_a_noop() -> None:
    # No bus -> refresh does nothing (and does not raise), so the collector guard is safe.
    src = MprisSource(MprisTracker())
    asyncio.run(src.refresh())


@pytest.mark.live
def test_live_enumerates_players_without_error() -> None:
    # Needs a live session bus. Passes whether or not a player is running; it only asserts the
    # enumerate/read path works and never raises. Play something to see a real label.
    async def run() -> None:
        async with await MprisSource(MprisTracker()).connect() as src:
            await src.refresh()

    asyncio.run(run())
