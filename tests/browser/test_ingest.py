"""Loopback tab-ingest tests (headless localhost HTTP).

Proves the endpoint refuses non-loopback binds, normalises a tab report into the tracker via
both the direct seam and a real POST, and rejects malformed input without crashing.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from kdence.browser.ingest import TabIngestServer
from kdence.browser.site import LOCAL_APP
from kdence.browser.tracker import BrowserTabTracker


def test_refuses_non_loopback_bind() -> None:
    with pytest.raises(ValueError):
        TabIngestServer(BrowserTabTracker(), host="0.0.0.0")


def test_record_normalises_and_reports_public_host() -> None:
    tracker = BrowserTabTracker()
    now = [1000.0]
    server = TabIngestServer(tracker, port=0, clock=lambda: now[0])
    site = server.record({"browser": "gecko", "hostname": "www.youtube.com", "scheme": "https"})
    assert site == "youtube.com"
    assert tracker.site_for("librewolf", now=1000.0) == "youtube.com"


def test_record_generalises_local_host() -> None:
    tracker = BrowserTabTracker()
    server = TabIngestServer(tracker, port=0, clock=lambda: 5.0)
    site = server.record({"browser": "chromium", "hostname": "127.0.0.1", "scheme": "http"})
    assert site == LOCAL_APP
    assert tracker.site_for("chromium", now=5.0) == LOCAL_APP


def test_record_missing_fields_is_graceful() -> None:
    tracker = BrowserTabTracker()
    server = TabIngestServer(tracker, port=0, clock=lambda: 1.0)
    assert server.record({}) is None  # no browser, no host -> nothing useful, no crash


def _post(port: int, path: str, body: bytes) -> int:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_live_post_lands_in_the_tracker() -> None:
    tracker = BrowserTabTracker()
    now = [2000.0]
    with TabIngestServer(tracker, port=0, clock=lambda: now[0]) as server:
        status = _post(
            server.port,
            "/tab",
            json.dumps({"browser": "gecko", "hostname": "github.com", "scheme": "https"}).encode(),
        )
        assert status == 204
        assert tracker.site_for("firefox", now=2000.0) == "github.com"

        # A malformed body is rejected, not fatal.
        assert _post(server.port, "/tab", b"not json") == 400
        # An unknown path is a 404.
        assert _post(server.port, "/nope", b"{}") == 404


def test_a_busy_port_raises_oserror_for_the_collector_to_catch() -> None:
    # The collector treats this as non-fatal (logs + continues) so a busy ingest port never
    # crash-loops the whole daemon. Here we prove the failure mode it now guards: binding a
    # port already in use raises OSError rather than silently succeeding.
    first = TabIngestServer(BrowserTabTracker(), port=0)
    first.start()
    try:
        with pytest.raises(OSError):
            TabIngestServer(BrowserTabTracker(), port=first.port)
    finally:
        first.stop()
