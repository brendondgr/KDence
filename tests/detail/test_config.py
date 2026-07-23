"""Tests for the runtime detail-provider config (dashboard toggle state)."""

from __future__ import annotations

import json

import pytest

from kdence.detail.config import DetailConfig, load, parse, save, to_dict


def test_parse_keeps_known_providers_and_denylist() -> None:
    cfg = parse({"providers": ["caption", "mpris"], "denylist": ["org.keepassxc.KeePassXC"]})
    assert cfg.providers == frozenset({"caption", "mpris"})
    assert cfg.denylist == frozenset({"org.keepassxc.KeePassXC"})


def test_parse_lenient_drops_unknown_providers() -> None:
    assert parse({"providers": ["caption", "bogus"]}).providers == frozenset({"caption"})


def test_parse_strict_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        parse({"providers": ["telepathy"]}, strict=True)


@pytest.mark.parametrize("bad", [[], "caption", {"providers": "caption"}, {"denylist": 3}])
def test_parse_rejects_bad_shape(bad) -> None:
    with pytest.raises(ValueError):
        parse(bad, strict=True)


def test_empty_config_is_all_off() -> None:
    assert parse({}) == DetailConfig()


def test_load_missing_file_is_none(tmp_path) -> None:
    # None signals "no runtime override" -> the collector uses its startup default.
    assert load(tmp_path / "detail.json") is None


def test_load_corrupt_file_reads_as_off(tmp_path) -> None:
    p = tmp_path / "detail.json"
    p.write_text("{ not json")
    assert load(p) == DetailConfig()  # never wedges; safest = OFF


def test_save_load_round_trip(tmp_path) -> None:
    p = tmp_path / "sub" / "detail.json"  # parent created by save
    cfg = DetailConfig(frozenset({"mpris"}), frozenset({"a.b.C"}))
    save(p, cfg)
    assert load(p) == cfg
    # On-disk shape is stable/sorted.
    assert json.loads(p.read_text()) == {"providers": ["mpris"], "denylist": ["a.b.C"]}


def test_to_dict_is_sorted() -> None:
    cfg = DetailConfig(frozenset({"mpris", "caption"}), frozenset({"z", "a"}))
    assert to_dict(cfg) == {"providers": ["caption", "mpris"], "denylist": ["a", "z"]}
