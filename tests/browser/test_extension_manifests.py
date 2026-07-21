"""Guard the WebExtension manifests + reporter (headless, no browser needed).

These are the privacy invariants of the browser tab-reporter, asserted so a careless edit
can't quietly widen them: the extensions may talk to loopback and nothing else, and the
reporter script has exactly one network endpoint (127.0.0.1) and differs between builds only
by its engine tag.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

EXT_ROOT = Path(__file__).resolve().parents[2] / "browser-extension"
LOOPBACK = "http://127.0.0.1:5786/*"
BUILDS = ("gecko", "chromium")


def _manifest(build: str) -> dict:
    return json.loads((EXT_ROOT / build / "manifest.json").read_text())


@pytest.mark.parametrize("build", BUILDS)
def test_manifest_is_valid_json(build: str) -> None:
    m = _manifest(build)
    assert m["name"] == "KDence Tab Reporter"


def test_gecko_declares_loopback_host_only() -> None:
    perms = _manifest("gecko")["permissions"]
    hosts = [p for p in perms if "://" in p]
    assert hosts == [LOOPBACK]  # the only host it may reach
    assert "<all_urls>" not in perms


def test_chromium_declares_loopback_host_only() -> None:
    m = _manifest("chromium")
    assert m["host_permissions"] == [LOOPBACK]
    # No host globs smuggled into plain permissions.
    assert all("://" not in p for p in m["permissions"])
    assert "<all_urls>" not in m["host_permissions"]


@pytest.mark.parametrize("build", BUILDS)
def test_reporter_has_exactly_one_network_endpoint(build: str) -> None:
    src = (EXT_ROOT / build / "tab-reporter.js").read_text()
    urls = set(re.findall(r"https?://[^\"'\s]+", src))
    assert urls == {"http://127.0.0.1:5786/tab"}  # loopback, and only loopback


@pytest.mark.parametrize("build", BUILDS)
def test_reporter_prefers_the_callback_compatible_chrome_namespace(build: str) -> None:
    # Firefox's `browser.*` APIs are Promise-based and ignore callbacks, so the reporter must
    # prefer `chrome` (callback style in both browsers) or nothing ever gets reported.
    src = (EXT_ROOT / build / "tab-reporter.js").read_text()
    assert "typeof chrome" in src and "? chrome :" in src
    # And it must tolerate a Promise return too (belt-and-suspenders).
    assert ".then(" in src


def test_builds_differ_only_by_engine_tag() -> None:
    gecko = (EXT_ROOT / "gecko" / "tab-reporter.js").read_text()
    chromium = (EXT_ROOT / "chromium" / "tab-reporter.js").read_text()
    assert 'KDENCE_ENGINE = "gecko"' in gecko
    assert 'KDENCE_ENGINE = "chromium"' in chromium

    # Everything from the shared ENDPOINT constant onward must be byte-identical, so the two
    # builds can never drift in the logic that actually reads and sends tab data.
    def body(src: str) -> str:
        return src[src.index("const ENDPOINT") :]

    assert body(gecko) == body(chromium)
