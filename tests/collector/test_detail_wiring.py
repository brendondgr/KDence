"""Tests for the collector's detail opt-in wiring (Phase 13.6): default OFF + env fallback."""

from __future__ import annotations

import argparse

from kdence.collector.__main__ import _detail_denylist, _detail_providers


def _ns(**kw) -> argparse.Namespace:
    base = {"detail_providers": None, "detail_denylist": None}
    base.update(kw)
    return argparse.Namespace(**base)


def test_default_is_off(monkeypatch) -> None:
    monkeypatch.delenv("KDENCE_DETAIL_PROVIDERS", raising=False)
    monkeypatch.delenv("KDENCE_DETAIL_DENYLIST", raising=False)
    assert _detail_providers(_ns()) == set()
    assert _detail_denylist(_ns()) == []


def test_flag_enables_known_providers_and_ignores_unknown(monkeypatch) -> None:
    monkeypatch.delenv("KDENCE_DETAIL_PROVIDERS", raising=False)
    assert _detail_providers(_ns(detail_providers="caption, mpris, bogus")) == {"caption", "mpris"}
    # site is not an opt-in name (always implicit); it is filtered out here.
    assert _detail_providers(_ns(detail_providers="site")) == set()


def test_env_supplies_the_default_when_flag_absent(monkeypatch) -> None:
    monkeypatch.setenv("KDENCE_DETAIL_PROVIDERS", "caption")
    assert _detail_providers(_ns()) == {"caption"}


def test_flag_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv("KDENCE_DETAIL_PROVIDERS", "caption")
    assert _detail_providers(_ns(detail_providers="mpris")) == {"mpris"}
    # An explicit empty flag disables even when the env is set.
    assert _detail_providers(_ns(detail_providers="")) == set()


def test_denylist_from_flag_and_env(monkeypatch) -> None:
    monkeypatch.setenv("KDENCE_DETAIL_DENYLIST", "org.env.App")
    assert _detail_denylist(_ns()) == ["org.env.App"]
    assert _detail_denylist(_ns(detail_denylist="a, b ,c")) == ["a", "b", "c"]
