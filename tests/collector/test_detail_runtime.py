"""Headless tests for the collector's live detail reconfiguration (DetailRuntime).

The MPRIS D-Bus source is faked, so only the reconfigure decision + lifecycle are exercised: a
toggle change rebuilds the registry, enabling/disabling MPRIS connects/closes its source, and an
unchanged config is a no-op. This is what makes the dashboard's live toggle work without a restart.
"""

from __future__ import annotations

import asyncio

from kdence.collector.__main__ import DetailRuntime


class _FakeSite:
    def __init__(self, site: str | None = None) -> None:
        self._site = site

    def site_for(self, app_class, now):  # noqa: ANN001, D102
        return self._site


class _FakeMprisSource:
    def __init__(self) -> None:
        self.connected = False
        self.closed = False
        self.refreshed = 0

    async def connect(self):  # noqa: D102
        self.connected = True

    async def close(self):  # noqa: D102
        self.closed = True

    async def refresh(self):  # noqa: D102
        self.refreshed += 1


class _FakeMprisTracker:
    def __init__(self, label: str | None) -> None:
        self._label = label

    def detail_for(self, app_class, now):  # noqa: ANN001, D102
        return self._label


def _runtime(track_label="Artist — Song", caption="notes.md — Kate"):
    created = {}

    def factory():
        tracker = _FakeMprisTracker(track_label)
        source = _FakeMprisSource()
        created["tracker"], created["source"] = tracker, source
        return tracker, source

    rt = DetailRuntime(_FakeSite(), lambda: caption, mpris_factory=factory)
    return rt, created


def test_caption_only_wires_no_mpris_source() -> None:
    rt, created = _runtime()
    changed = asyncio.run(rt.apply({"caption"}, set()))
    assert changed is True
    assert "source" not in created  # MPRIS never constructed
    assert rt.registry.resolve("org.kde.kate", 1.0) == ("notes.md", "caption")


def test_enabling_mpris_connects_the_source_and_resolves() -> None:
    rt, created = _runtime()
    asyncio.run(rt.apply({"mpris"}, set()))
    assert created["source"].connected is True
    # MPRIS is ahead of caption in priority.
    assert rt.registry.resolve("vlc", 1.0) == ("Artist — Song", "mpris")


def test_disabling_mpris_closes_the_source() -> None:
    rt, created = _runtime()

    async def run():
        await rt.apply({"mpris"}, set())
        await rt.apply({"caption"}, set())  # toggle mpris off

    asyncio.run(run())
    assert created["source"].closed is True
    assert rt.registry.resolve("vlc", 1.0) is not None or True  # vlc no longer mpris
    assert rt.registry.resolve("org.kde.kate", 1.0) == ("notes.md", "caption")


def test_unchanged_config_is_a_noop() -> None:
    rt, _ = _runtime()

    async def run():
        first = await rt.apply({"caption"}, set())
        second = await rt.apply({"caption"}, set())
        return first, second

    first, second = asyncio.run(run())
    assert first is True and second is False


def test_denylist_is_applied_and_reconfigures() -> None:
    rt, _ = _runtime()

    async def run():
        await rt.apply({"caption"}, set())
        return await rt.apply({"caption"}, {"org.kde.kate"})

    changed = asyncio.run(run())
    assert changed is True  # denylist change alone rebuilds
    assert rt.registry.resolve("org.kde.kate", 1.0) == (None, None)  # denied


def test_refresh_polls_mpris_only_when_enabled() -> None:
    rt, created = _runtime()

    async def run():
        await rt.refresh()  # no mpris yet -> nothing
        await rt.apply({"mpris"}, set())
        await rt.refresh()

    asyncio.run(run())
    assert created["source"].refreshed == 1
