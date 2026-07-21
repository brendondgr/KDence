"""Pure site-identity policy tests (headless).

Proves the two rules that matter: local/private hostnames are never logged by name (they
collapse to the one generic bucket), and public hosts are normalised to a stable label.
"""

from __future__ import annotations

import pytest

from kdence.browser.site import LOCAL_APP, is_local_host, normalize_site


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "localhost.localdomain",
        "app.localhost",
        "127.0.0.1",
        "127.4.5.6",  # all of 127.0.0.0/8 is loopback
        "10.0.0.5",  # RFC1918
        "172.16.3.4",  # RFC1918 (172.16-31)
        "172.31.255.255",
        "192.168.1.9",  # RFC1918
        "169.254.10.10",  # link-local
        "[::1]",  # IPv6 loopback, bracketed as URL.hostname delivers it
        "[fe80::1]",  # IPv6 link-local
        "[fc00::1]",  # IPv6 unique-local (private)
        "printer.local",  # mDNS
        "nas",  # bare single label -> no public TLD
        "router",
    ],
)
def test_local_and_private_hosts_collapse_to_the_generic_bucket(host: str) -> None:
    assert is_local_host(host) is True
    assert normalize_site(host) == LOCAL_APP


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("youtube.com", "youtube.com"),
        ("www.youtube.com", "youtube.com"),  # leading www. dropped
        ("GitHub.com", "github.com"),  # lowercased
        ("mail.google.com", "mail.google.com"),  # other subdomains kept
        ("example.com.", "example.com"),  # trailing FQDN dot trimmed
        ("8.8.8.8", "8.8.8.8"),  # a public IP is a real, non-local host
        ("172.32.0.1", "172.32.0.1"),  # just outside RFC1918 -> public
    ],
)
def test_public_hosts_normalise(host: str, expected: str) -> None:
    assert is_local_host(host) is False
    assert normalize_site(host) == expected


@pytest.mark.parametrize("scheme", ["file", "about", "chrome", "moz-extension", "data"])
def test_non_web_schemes_have_no_site(scheme: str) -> None:
    assert normalize_site("example.com", scheme) is None


def test_web_schemes_are_accepted_with_or_without_trailing_colon() -> None:
    assert normalize_site("example.com", "https") == "example.com"
    assert normalize_site("example.com", "http:") == "example.com"


def test_empty_host_is_no_site() -> None:
    assert normalize_site("") is None
    assert normalize_site("   ") is None
    assert normalize_site("", "http") is None
