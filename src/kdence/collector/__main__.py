"""Step 3.1 (live) -- the merged console line you'd bet money on.

One process, one asyncio loop, two live signals:

- the Wayland idle source drives the pure :class:`ActivityMonitor` (active vs. idle),
  its socket integrated via ``loop.add_reader``;
- the KWin focus source drives the pure :class:`FocusReporter` (which app).

Once per interval it prints the merged line ("app X — active", or "— idle" once you've
been away past the threshold). Watch it while you work in one app, switch apps, then
walk away: the line must track app changes and flip to idle after the threshold.

With ``--store PATH`` (Phase 4) it also persists spans through the pure time model into a
single-writer SQLite store: each interval feeds a wall-clock ``active`` heartbeat, and on
idle the active span is closed at the *back-dated last-input* instant (not detection), so
the trailing idle window is never counted. Dump the result with
``python -m kdence.storage PATH``. Without ``--store`` it is print-only (Phase 3).

Usage:
    uv run python -m kdence.collector [--threshold 5] [--interval 2] [--titles]
                                          [--store PATH]

``--threshold`` defaults short (demo-sized); real use is IDLE_THRESHOLD_SECONDS (300).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from kdence.activity.monitor import ActivityMonitor, ActivityState
from kdence.activity.wayland_idle import WaylandIdleSource
from kdence.browser.ingest import DEFAULT_INGEST_PORT, TabIngestServer
from kdence.browser.tracker import BrowserTabTracker, load_browser_classes
from kdence.collector.merge import merge
from kdence.collector.providers import (
    CaptionProvider,
    DetailRegistry,
    MprisProvider,
    SiteProvider,
)
from kdence.detail import config as detail_config
from kdence.detail.mpris.source import MprisSource
from kdence.detail.mpris.tracker import MprisTracker
from kdence.focus.kwin_source import KWinFocusSource
from kdence.focus.reporter import FocusReporter
from kdence.model.timeline import Timeline
from kdence.storage.paths import (
    default_browsers_path,
    default_detail_path,
    default_store_path,
)
from kdence.storage.store import Store


def _default_mpris_factory() -> tuple[MprisTracker, MprisSource]:
    tracker = MprisTracker()
    return tracker, MprisSource(tracker)


class DetailRuntime:
    """Holds the live detail-provider wiring and rebuilds it when the toggle config changes.

    The dashboard writes ``detail.json`` and the collector calls :meth:`apply` each interval with
    the desired providers/denylist; only an actual change rebuilds the registry, and enabling or
    disabling MPRIS connects or closes its D-Bus source on the fly (so the toggle takes effect
    without a restart). The site provider is always present. The MPRIS source factory is injected
    so this class is testable headlessly with a fake.
    """

    def __init__(
        self,
        site_tracker: object,
        caption_getter: object,
        *,
        mpris_factory: object = _default_mpris_factory,
    ) -> None:
        self._site_tracker = site_tracker
        self._caption_getter = caption_getter
        self._mpris_factory = mpris_factory
        self._mpris_tracker: object | None = None
        self._mpris_source: object | None = None
        self._enabled: frozenset[str] = frozenset()
        self._denylist: frozenset[str] = frozenset()
        self._hidden: frozenset[str] = frozenset()
        self.registry = DetailRegistry([SiteProvider(site_tracker)])

    @property
    def enabled(self) -> frozenset[str]:
        return self._enabled

    async def apply(self, providers: object, denylist: object, hidden: object = ()) -> bool:
        """Reconfigure to the desired providers/denylist/hidden; return whether anything changed."""
        want = frozenset(providers)
        deny = frozenset(denylist)
        hide = frozenset(hidden)
        if want == self._enabled and deny == self._denylist and hide == self._hidden:
            return False
        # MPRIS lifecycle: connect on enable, close on disable.
        if "mpris" in want and self._mpris_source is None:
            self._mpris_tracker, self._mpris_source = self._mpris_factory()
            await self._mpris_source.connect()
        elif "mpris" not in want and self._mpris_source is not None:
            await self._mpris_source.close()
            self._mpris_source = self._mpris_tracker = None
        # Rebuild the registry in priority order site -> mpris -> caption.
        built: list[object] = [SiteProvider(self._site_tracker)]
        if "mpris" in want and self._mpris_tracker is not None:
            built.append(MprisProvider(self._mpris_tracker))
        if "caption" in want:
            built.append(CaptionProvider(self._caption_getter))
        self.registry = DetailRegistry(built, denylist=deny, hidden=hide)
        self._enabled, self._denylist, self._hidden = want, deny, hide
        return True

    async def refresh(self) -> None:
        """Poll the MPRIS source (if enabled) so now-playing metadata stays fresh."""
        if self._mpris_source is not None:
            await self._mpris_source.refresh()

    async def close(self) -> None:
        if self._mpris_source is not None:
            await self._mpris_source.close()
            self._mpris_source = self._mpris_tracker = None


async def _run(args: argparse.Namespace) -> None:
    monitor = ActivityMonitor(
        threshold_seconds=args.threshold,
        resolution_seconds=args.resolution_ms / 1000,
    )
    reporter = FocusReporter(capture_titles=args.titles)

    # The live raw caption of the focused window, kept for the (opt-in) caption provider. KWin
    # sends the raw caption on every activation *and* in-window caption change; we stash it here
    # regardless of the title-privacy flag, because the caption provider is itself opt-in and
    # applies its own generalisation/denylist downstream.
    focus_state: dict[str, str | None] = {"caption": None}

    def on_focus(app_class: str, title: str) -> None:
        focus_state["caption"] = title or None
        reporter.update(app_class, title)

    store: Store | None = None
    timeline: Timeline | None = None
    store_path = _resolve_store(args)
    if store_path is not None:
        store = Store(store_path)
        # A heartbeat gap larger than this means a suspend/stall, not activity.
        timeline = store.bind(max_gap_seconds=max(args.interval * 3, 5.0))

    idle = WaylandIdleSource(
        resolution_ms=args.resolution_ms,
        on_idled=monitor.mark_idled,
        on_resumed=monitor.mark_resumed,
    )
    idle.connect()
    loop = asyncio.get_running_loop()
    loop.add_reader(idle.fileno(), lambda: idle.dispatch())

    focus = KWinFocusSource(on_focus=on_focus)
    await focus.connect()

    # Browser sub-identity: the loopback tab-ingest feeds a tracker the merge consults each
    # interval, so a focused browser's active-tab host rides along on its spans.
    tracker = BrowserTabTracker(browser_classes=load_browser_classes(default_browsers_path()))
    ingest: TabIngestServer | None = None
    if not args.no_ingest:
        try:
            ingest = TabIngestServer(tracker, port=args.ingest_port)
            ingest.start()
        except OSError as exc:
            # A busy/forbidden ingest port must NOT take the whole collector down: the tab-ingest
            # only feeds the (optional) browser-site sub-dimension. Log and carry on recording.
            print(f"[warn] tab-ingest disabled (port {args.ingest_port}: {exc}); continuing.")
            ingest = None

    # In-app detail providers (site -> mpris -> caption). The browser-site provider is always
    # present (gated by the tab-ingest, as before). caption/MPRIS are opt-in and default OFF; the
    # STARTUP default comes from --detail-providers/env, but the dashboard can flip them LIVE by
    # writing detail.json, which the collector re-reads each interval below (the file wins when
    # present). The denylist blocks detail for sensitive apps.
    detail_path = default_detail_path()
    startup = detail_config.DetailConfig(
        frozenset(_detail_providers(args)), frozenset(_detail_denylist(args))
    )
    runtime = DetailRuntime(tracker, lambda: focus_state["caption"])
    await runtime.apply(startup.providers, startup.denylist, startup.hidden)

    # Re-inject the focus script if KWin evicts it (fixes the focus-freeze). Cheap DBus check.
    reinject_every = max(1, round(15.0 / args.interval))

    where = f", store={store_path}" if store_path is not None else " (print-only)"
    tabs = f", tabs=127.0.0.1:{ingest.port}" if ingest is not None else " (no tab-ingest)"
    extra = sorted(runtime.enabled)
    detail = f", detail={'+'.join(extra)}" if extra else ""
    print(
        f"Live merge -- threshold={args.threshold:g}s, interval={args.interval:g}s, "
        f"titles={'on' if args.titles else 'off'}{detail}{where}{tabs}. Ctrl-C to stop."
    )
    try:
        tick = 0
        while True:
            await asyncio.sleep(args.interval)
            tick += 1
            # Live toggle: a dashboard-written detail.json overrides the startup default.
            runtime_cfg = detail_config.load(detail_path)
            desired = runtime_cfg if runtime_cfg is not None else startup
            if await runtime.apply(desired.providers, desired.denylist, desired.hidden):
                print(f"[detail] providers now: {'+'.join(sorted(runtime.enabled)) or 'off'}")
            if tick % reinject_every == 0:
                await focus.ensure_loaded()
            await runtime.refresh()
            now = time.time()
            state = monitor.state_at()
            current = reporter.current
            detail, detail_source = runtime.registry.resolve(current.app_class, now)
            sample = merge(state, current, detail, detail_source)
            print(f"[{time.strftime('%H:%M:%S')}] {sample.line}")
            if timeline is not None:
                if state is ActivityState.ACTIVE:
                    timeline.active(
                        now, sample.app_class, sample.title, sample.detail, sample.detail_source
                    )
                else:
                    # Close the active span at the real last-input instant (back-dated),
                    # in wall-clock terms -- the honesty rule from Phase 4.1.
                    timeline.idle(now - monitor.idle_seconds())
    finally:
        loop.remove_reader(idle.fileno())
        idle.close()
        await focus.close()
        await runtime.close()
        if ingest is not None:
            ingest.stop()
        if timeline is not None:
            timeline.stop(time.time())  # clean shutdown finalizes the open span
        if store is not None:
            store.close()


def _resolve_store(args: argparse.Namespace) -> str | None:
    """Where to persist, if anywhere. ``--no-store`` -> print-only (the Phase 3 demo mode);
    an explicit ``--store`` wins; otherwise the durable XDG default (Phase 9)."""
    if args.no_store:
        return None
    if args.store:
        return args.store
    return str(default_store_path())


# Detail providers that are opt-in (default OFF). ``site`` is not here: it is the pre-existing
# browser feature, gated by the tab-ingest rather than by this opt-in.
_OPTIN_PROVIDERS = ("caption", "mpris")


def _detail_providers(args: argparse.Namespace) -> set[str]:
    """The opt-in detail providers to enable (comma-separated).

    Source order: the ``--detail-providers`` flag, else ``KDENCE_DETAIL_PROVIDERS``, else empty
    (the privacy default -- caption/MPRIS OFF). ``site`` is always implicitly present (gated by
    the tab-ingest, not this opt-in) and cannot be enabled/disabled here; unknown names ignored.
    """
    raw = getattr(args, "detail_providers", None)
    if raw is None:
        raw = os.environ.get("KDENCE_DETAIL_PROVIDERS", "")
    names = {n.strip().lower() for n in raw.split(",") if n.strip()}
    return {n for n in names if n in _OPTIN_PROVIDERS}


def _detail_denylist(args: argparse.Namespace) -> list[str]:
    """App classes never to detail (comma-separated): the ``--detail-denylist`` flag, else
    ``KDENCE_DETAIL_DENYLIST``, else empty."""
    raw = getattr(args, "detail_denylist", None)
    if raw is None:
        raw = os.environ.get("KDENCE_DETAIL_DENYLIST", "")
    return [n.strip() for n in raw.split(",") if n.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live merged activity+focus line (Steps 3.1 / 4.3)"
    )
    parser.add_argument("--threshold", type=float, default=5.0, help="idle threshold seconds")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between lines")
    parser.add_argument("--resolution-ms", type=int, default=1000, help="idle notify timeout (ms)")
    parser.add_argument("--titles", action="store_true", help="capture window titles (sensitive)")
    parser.add_argument(
        "--detail-providers",
        metavar="LIST",
        default=None,
        help="comma-separated opt-in in-app detail providers (caption,mpris); default OFF. "
        "The browser-site provider is always on when the tab-ingest runs.",
    )
    parser.add_argument(
        "--detail-denylist",
        metavar="LIST",
        default=None,
        help="comma-separated app classes to never record detail for (e.g. password managers)",
    )
    parser.add_argument(
        "--store",
        metavar="PATH",
        help="persist spans to this SQLite file (default: the durable XDG store path)",
    )
    parser.add_argument(
        "--no-store", action="store_true", help="print-only, do not persist (Phase 3 demo mode)"
    )
    parser.add_argument(
        "--ingest-port",
        type=int,
        default=DEFAULT_INGEST_PORT,
        help="loopback port for the browser tab-ingest (127.0.0.1 only)",
    )
    parser.add_argument(
        "--no-ingest", action="store_true", help="do not run the browser tab-ingest listener"
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
