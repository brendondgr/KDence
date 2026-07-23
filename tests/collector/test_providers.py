"""Pure tests for the detail provider registry (Phase 13.1)."""

from __future__ import annotations

from kdence.collector.providers import CaptionProvider, DetailRegistry, SiteProvider


class _Fixed:
    """A provider that always returns the same value for a given source."""

    def __init__(self, source: str, value: str | None) -> None:
        self.source = source
        self._value = value

    def detail_for(self, app_class: str | None, now: float) -> str | None:
        return self._value


class _FakeTracker:
    def __init__(self, site: str | None) -> None:
        self._site = site
        self.asked: list[tuple[str | None, float]] = []

    def site_for(self, app_class: str | None, now: float) -> str | None:
        self.asked.append((app_class, now))
        return self._site


def test_registry_returns_first_non_none_in_priority_order() -> None:
    reg = DetailRegistry(
        [_Fixed("site", None), _Fixed("caption", "notes.md"), _Fixed("mpris", "x")]
    )
    assert reg.resolve("org.kde.kate", 1.0) == ("notes.md", "caption")


def test_registry_returns_none_when_all_abstain() -> None:
    reg = DetailRegistry([_Fixed("site", None), _Fixed("caption", None)])
    assert reg.resolve("code", 1.0) == (None, None)


def test_empty_registry_is_inert() -> None:
    assert DetailRegistry([]).resolve("code", 1.0) == (None, None)


def test_hidden_value_is_suppressed_without_falling_through() -> None:
    # A hidden site must NOT reveal the browser's page title via the caption provider instead.
    reg = DetailRegistry(
        [_Fixed("site", "mybank.com"), _Fixed("caption", "My Bank — Secret — Firefox")],
        hidden=["mybank.com"],
    )
    assert reg.resolve("firefox", 1.0) == (None, None)


def test_non_hidden_value_still_resolves() -> None:
    reg = DetailRegistry([_Fixed("site", "github.com")], hidden=["mybank.com"])
    assert reg.resolve("firefox", 1.0) == ("github.com", "site")


def test_denylist_short_circuits_every_provider() -> None:
    reg = DetailRegistry([_Fixed("caption", "secret.kdbx")], denylist=["org.keepassxc.KeePassXC"])
    # Case-insensitive; denied class yields nothing regardless of what a provider would return.
    assert reg.resolve("org.keepassxc.keepassxc", 1.0) == (None, None)
    assert reg.is_denied("ORG.KEEPASSXC.KEEPASSXC") is True
    # A non-denied class still resolves.
    assert reg.resolve("org.kde.kate", 1.0) == ("secret.kdbx", "caption")


def test_site_provider_delegates_to_the_tracker() -> None:
    tracker = _FakeTracker("youtube.com")
    provider = SiteProvider(tracker)
    assert provider.source == "site"
    assert provider.detail_for("librewolf", 42.0) == "youtube.com"
    assert tracker.asked == [("librewolf", 42.0)]


def test_caption_provider_parses_the_live_caption() -> None:
    caption = {"v": "notes.md — Kate"}
    provider = CaptionProvider(lambda: caption["v"])
    assert provider.source == "caption"
    assert provider.detail_for("org.kde.kate", 1.0) == "notes.md"
    # It reflects the live caption changing under it (in-window switch).
    caption["v"] = "/home/bdgr/secret.md — Kate"
    assert provider.detail_for("org.kde.kate", 2.0) == "(local file)"
    caption["v"] = None
    assert provider.detail_for("org.kde.kate", 3.0) is None


def test_caption_provider_in_registry_loses_to_site_for_a_browser() -> None:
    # Priority site -> caption: a focused browser keeps its host even with caption enabled.
    tracker = _FakeTracker("github.com")
    caption = {"v": "GitHub — Mozilla Firefox"}
    reg = DetailRegistry([SiteProvider(tracker), CaptionProvider(lambda: caption["v"])])
    assert reg.resolve("firefox", 1.0) == ("github.com", "site")
