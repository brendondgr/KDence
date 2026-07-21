"""Category config tests (headless): defaults, auto-assign, validation, round-trip."""

from __future__ import annotations

import json

import pytest

from kdence.grouping.categories import (
    UNCATEGORIZED,
    Category,
    CategoryConfig,
    auto_assign,
    default_config,
    load,
    parse,
    resolve,
    save,
    to_dict,
)


def test_default_config_has_reserved_uncategorized() -> None:
    cfg = default_config()
    ids = {c.id for c in cfg.categories}
    assert UNCATEGORIZED in ids
    assert "work" in ids and "games" in ids
    # Seeded assignments resolve; browsers are intentionally unseeded.
    assert resolve("code", cfg) == "work"
    assert resolve("steam", cfg) == "games"
    assert resolve("librewolf", cfg) == UNCATEGORIZED
    assert resolve(None, cfg) == UNCATEGORIZED  # the bare desktop


def test_resolve_falls_back_when_category_deleted() -> None:
    cfg = CategoryConfig(
        categories=(Category(UNCATEGORIZED, "Uncategorized", "#6e7681"),),
        assignments={"code": "work"},  # 'work' no longer exists
    )
    assert resolve("code", cfg) == UNCATEGORIZED


def test_auto_assign_is_non_destructive_and_seed_only() -> None:
    cfg = CategoryConfig(default_config().categories, assignments={"code": "games"})
    out = auto_assign(["code", "steam", "some-unknown-app", None], cfg)
    assert out.assignments["code"] == "games"  # existing choice preserved
    assert out.assignments["steam"] == "games"  # seeded
    assert "some-unknown-app" not in out.assignments  # unknown left alone


def test_parse_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        parse({"categories": []})  # empty
    with pytest.raises(ValueError):
        parse({"categories": [{"id": "a", "name": "A", "color": "nothex"}]})
    with pytest.raises(ValueError):
        parse(
            {
                "categories": [
                    {"id": "a", "name": "A", "color": "#4c9aff"},
                    {"id": "a", "name": "B", "color": "#3fb950"},
                ]
            }
        )  # dup id


def test_parse_injects_uncategorized_and_drops_dangling_assignments() -> None:
    cfg = parse(
        {
            "categories": [{"id": "work", "name": "Work", "color": "#4C9AFF"}],
            "assignments": {"code": "work", "vlc": "ghost", "steam": "uncategorized"},
        }
    )
    ids = {c.id for c in cfg.categories}
    assert UNCATEGORIZED in ids  # force-injected
    assert cfg.assignments == {"code": "work"}  # 'ghost' dropped, explicit uncategorized dropped
    assert cfg.by_id()["work"].color == "#4c9aff"  # normalised


def test_save_load_round_trip(tmp_path) -> None:
    path = tmp_path / "sub" / "categories.json"  # parent doesn't exist yet
    cfg = CategoryConfig(
        default_config().categories, assignments={"code": "work", "steam": "games"}
    )
    save(path, cfg)
    assert path.exists()
    back = load(path)
    assert back.assignments == cfg.assignments
    assert {c.id for c in back.categories} == {c.id for c in cfg.categories}


def test_load_missing_or_corrupt_falls_back_to_default(tmp_path) -> None:
    missing = tmp_path / "nope.json"
    assert load(missing).categories == default_config().categories

    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{ not json")
    assert resolve("code", load(corrupt)) == "work"  # fell back to defaults


def test_to_dict_is_json_serialisable() -> None:
    json.dumps(to_dict(default_config()))  # must not raise


# -- site-level assignment (site categories) ----------------------------------


def test_resolve_site_and_defaults() -> None:
    from kdence.grouping.categories import resolve_site

    cfg = default_config()
    assert resolve_site("youtube.com", cfg) == "entertainment"
    assert resolve_site("github.com", cfg) == "work"
    assert resolve_site("reddit.com", cfg) == "social"
    assert resolve_site("some-unknown-host.example", cfg) is None  # unassigned
    assert resolve_site(None, cfg) is None


def test_auto_assign_fills_sites_non_destructively() -> None:
    cfg = CategoryConfig(
        default_config().categories, assignments={}, site_assignments={"youtube.com": "work"}
    )
    out = auto_assign([], cfg, sites=["youtube.com", "github.com", "weird.example"])
    assert out.site_assignments["youtube.com"] == "work"  # existing choice kept
    assert out.site_assignments["github.com"] == "work"  # seeded
    assert "weird.example" not in out.site_assignments  # unknown left alone


def test_parse_and_round_trip_site_assignments() -> None:
    cfg = parse(
        {
            "categories": [{"id": "fun", "name": "Fun", "color": "#f0883e"}],
            "assignments": {},
            "site_assignments": {
                "YouTube.com": "fun",
                "ghost.com": "nope",
                "x.com": "uncategorized",
            },
        }
    )
    # Host lowercased; dangling + explicit-uncategorized dropped.
    assert cfg.site_assignments == {"youtube.com": "fun"}
    back = parse(to_dict(cfg))
    assert back.site_assignments == cfg.site_assignments
