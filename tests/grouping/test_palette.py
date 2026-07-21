"""Palette + colour-variant tests (headless)."""

from __future__ import annotations

import colorsys

import pytest

from kdence.grouping.palette import (
    PALETTE,
    UNCATEGORIZED_COLOR,
    is_hex_color,
    normalize_color,
    variant,
)


def test_palette_has_twelve_distinct_colours() -> None:
    assert len(PALETTE) == 12
    assert len(set(PALETTE)) == 12
    assert all(is_hex_color(c) for c in PALETTE)
    assert UNCATEGORIZED_COLOR not in PALETTE  # the reserved gray is separate


def test_normalize_color_canonicalises_and_rejects() -> None:
    assert normalize_color("#ABCDEF") == "#abcdef"
    assert normalize_color("abcdef") == "#abcdef"
    with pytest.raises(ValueError):
        normalize_color("#xyz")
    with pytest.raises(ValueError):
        normalize_color("#12345")  # 5 digits


def test_single_member_is_the_base_unchanged() -> None:
    assert variant("#4c9aff", 0, 1) == "#4c9aff"


def _lightness(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[1]


def test_variants_step_from_lighter_to_darker_and_stay_valid() -> None:
    base = "#4c9aff"
    n = 5
    colors = [variant(base, i, n) for i in range(n)]
    assert all(is_hex_color(c) for c in colors)
    lightnesses = [_lightness(c) for c in colors]
    # First member is the lightest, last is the darkest, monotonically.
    assert lightnesses == sorted(lightnesses, reverse=True)
    assert lightnesses[0] > lightnesses[-1]


def test_variant_is_deterministic() -> None:
    assert variant("#db61a2", 2, 4) == variant("#db61a2", 2, 4)
