"""Browser-tab tracker tests (headless).

Proves the freshness TTL and the focus gating: a site is attributed only to a known browser
class whose engine has a fresh report, and engines are tracked independently.
"""

from __future__ import annotations

import pytest

from timekeeper.browser.tracker import (
    DEFAULT_TTL_SECONDS,
    BrowserTabTracker,
    engine_for_class,
)


@pytest.mark.parametrize(
    ("app_class", "engine"),
    [
        ("librewolf", "gecko"),
        ("Firefox", "gecko"),  # case-insensitive
        ("brave-browser", "chromium"),
        ("chromium", "chromium"),
        ("google-chrome", "chromium"),
        ("org.kde.konsole", None),  # not a browser
        ("", None),
        (None, None),
    ],
)
def test_engine_for_class(app_class: str | None, engine: str | None) -> None:
    assert engine_for_class(app_class) == engine


def test_fresh_report_is_attributed_to_its_engine() -> None:
    t = BrowserTabTracker(ttl_seconds=15.0)
    t.report("gecko", "youtube.com", at=100.0)
    assert t.site_for("librewolf", now=105.0) == "youtube.com"
    assert t.site_for("firefox", now=105.0) == "youtube.com"  # same engine
    # A different engine has no report of its own.
    assert t.site_for("chromium", now=105.0) is None


def test_report_goes_stale_after_ttl() -> None:
    t = BrowserTabTracker(ttl_seconds=15.0)
    t.report("gecko", "github.com", at=100.0)
    assert t.site_for("librewolf", now=114.9) == "github.com"  # within TTL
    assert t.site_for("librewolf", now=115.1) is None  # past TTL


def test_non_browser_focus_never_gets_a_site() -> None:
    t = BrowserTabTracker()
    t.report("gecko", "youtube.com", at=100.0)
    assert t.site_for("org.kde.konsole", now=101.0) is None


def test_engines_are_independent() -> None:
    t = BrowserTabTracker(ttl_seconds=15.0)
    t.report("gecko", "gecko-site.com", at=100.0)
    t.report("chromium", "chromium-site.com", at=100.0)
    assert t.site_for("librewolf", now=105.0) == "gecko-site.com"
    assert t.site_for("brave-browser", now=105.0) == "chromium-site.com"


def test_unknown_engine_token_is_ignored() -> None:
    t = BrowserTabTracker()
    t.report("safari", "apple.com", at=100.0)
    assert t.site_for("librewolf", now=101.0) is None
    assert t.site_for("chromium", now=101.0) is None


def test_fresh_none_site_means_internal_page_not_stale() -> None:
    t = BrowserTabTracker()
    t.report("gecko", None, at=100.0)  # browser focused but on about:newtab
    assert t.site_for("librewolf", now=101.0) is None


def test_ttl_must_be_positive() -> None:
    with pytest.raises(ValueError):
        BrowserTabTracker(ttl_seconds=0)
    assert DEFAULT_TTL_SECONDS > 0
