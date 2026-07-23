"""Detail providers -- resolve the in-app "what were you doing" sub-identity.

A :class:`DetailProvider` maps the focused window's ``app_class`` (+ wall-clock ``now``) to a
detail string, or ``None`` when it has nothing to say. Each provider names its ``source``
(``site`` | ``caption`` | ``mpris``), which rides onto the span as ``detail_source`` so the
drill-down can label where the detail came from.

The collector owns all hardware; a provider is a small, pure-ish adapter over state the
collector already gathered -- the browser tab tracker, the focused window's caption, the MPRIS
players -- so each is independently testable. :class:`DetailRegistry` queries providers in
**priority order** and returns the first non-``None`` result, so a focused browser keeps
resolving to its site even when a media provider is also enabled (site is placed first). A
per-app-class **denylist** short-circuits every provider, so sensitive apps (password managers,
banking, messaging) are never detailed regardless of which providers are on.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, runtime_checkable

from kdence.detail.caption import parse_caption


@runtime_checkable
class DetailProvider(Protocol):
    """Resolves an in-app detail for the focused window, or ``None``."""

    source: str

    def detail_for(self, app_class: str | None, now: float) -> str | None: ...


class DetailRegistry:
    """Ordered detail providers + a denylist; resolves one ``(value, source)`` per interval.

    Args:
        providers: providers in priority order (highest first). The first to return a
            non-``None`` value wins.
        denylist: app classes (case-insensitive) that must never be detailed -- any focused
            window of such a class resolves to ``(None, None)`` before any provider runs.
    """

    def __init__(
        self,
        providers: Iterable[DetailProvider],
        denylist: Iterable[str] = (),
    ) -> None:
        self._providers = list(providers)
        self._denylist = frozenset(d.strip().lower() for d in denylist if d and d.strip())

    def is_denied(self, app_class: str | None) -> bool:
        """Whether ``app_class`` is on the denylist (so no detail is ever recorded for it)."""
        return bool(app_class) and app_class.strip().lower() in self._denylist

    def resolve(self, app_class: str | None, now: float) -> tuple[str | None, str | None]:
        """The winning ``(detail, source)`` for the focused window, or ``(None, None)``."""
        if self.is_denied(app_class):
            return (None, None)
        for provider in self._providers:
            value = provider.detail_for(app_class, now)
            if value is not None:
                return (value, provider.source)
        return (None, None)


class SiteProvider:
    """The built-in browser-site provider: the focused browser's active-tab host.

    Thin adapter over :class:`~kdence.browser.tracker.BrowserTabTracker`, which is already
    focus-gated and TTL-bounded. Present in the registry whenever the tab-ingest runs (the
    existing browser-activity feature), independently of the opt-in caption/MPRIS providers.
    """

    source = "site"

    def __init__(self, tracker: object) -> None:
        # Duck-typed to BrowserTabTracker.site_for; kept loose so tests can pass a fake.
        self._tracker = tracker

    def detail_for(self, app_class: str | None, now: float) -> str | None:
        return self._tracker.site_for(app_class, now)  # type: ignore[attr-defined]


class CaptionProvider:
    """The focused window's caption, parsed to a document/tab/track label (Tier 1, opt-in).

    Thin adapter over :func:`kdence.detail.caption.parse_caption`: ``get_caption`` returns the
    live raw caption of the currently focused window (maintained by the collector from the KWin
    focus stream, which now also fires on in-window caption changes). The app-name suffix is
    stripped and filesystem paths are generalised in the pure policy, so nothing here touches
    hardware and the whole thing is testable with a fake getter.
    """

    source = "caption"

    def __init__(self, get_caption: Callable[[], str | None]) -> None:
        self._get_caption = get_caption

    def detail_for(self, app_class: str | None, now: float) -> str | None:
        return parse_caption(app_class, self._get_caption())
