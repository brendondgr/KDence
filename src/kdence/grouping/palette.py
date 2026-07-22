"""Category colors -- the 12-color starting palette + a pure tint/shade variant function.

No I/O, no hardware. Categories pick a base color from :data:`PALETTE` (or a custom hex); the
apps *inside* a category are painted as lightness-stepped **variants** of that base, so the
visual relationship between a group and its members is obvious. :func:`variant` is the single,
tested source of those member colors -- the server computes them and the view just paints what
it is given, so there is no duplicate colour maths in JS.
"""

from __future__ import annotations

import colorsys
import re

# Twelve maximally-distinct swatches, tuned for the dark terminal theme. Eight well-separated
# hues span the wheel (no near-duplicate pairs), then earth/neutral tones -- brown plus two
# grays -- give categories that read clearly apart instead of like a rainbow gradient.
PALETTE: tuple[str, ...] = (
    "#ff7b72",  # red
    "#f0883e",  # orange
    "#e3b341",  # amber
    "#a5cd3a",  # lime
    "#3fb950",  # green
    "#2dd4bf",  # teal
    "#4c9aff",  # blue
    "#a78bfa",  # purple
    "#f472b6",  # pink
    "#a56b3a",  # brown
    "#8b96a5",  # slate gray
    "#cbd3dc",  # light gray
)

# The reserved "Uncategorized" bucket's colour: a neutral gray, deliberately not in PALETTE.
UNCATEGORIZED_COLOR = "#6e7681"

_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def is_hex_color(value: str) -> bool:
    """True for a 6-digit hex colour, with or without a leading ``#``."""
    return isinstance(value, str) and bool(_HEX_RE.match(value.strip()))


def normalize_color(value: str) -> str:
    """Canonicalise a hex colour to lowercase ``#rrggbb``. Raises ``ValueError`` if invalid."""
    if not is_hex_color(value):
        raise ValueError(f"not a 6-digit hex colour: {value!r}")
    return "#" + value.strip().lstrip("#").lower()


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = normalize_color(hex_color).lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        round(max(0.0, min(1.0, r)) * 255),
        round(max(0.0, min(1.0, g)) * 255),
        round(max(0.0, min(1.0, b)) * 255),
    )


def variant(base_hex: str, index: int, count: int) -> str:
    """A lightness-stepped tint/shade of ``base_hex`` for member ``index`` of ``count``.

    ``count <= 1`` (or a single member) returns the base unchanged. Otherwise members are spread
    across a lightness band around the base -- lighter for the first, darker for the last -- so
    every member is distinct yet clearly related to its category. Hue and saturation are kept.
    """
    base = normalize_color(base_hex)
    if count <= 1:
        return base
    r, g, b = _hex_to_rgb(base)
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    span = 0.22
    # t: -1 for the first member (lighter), +1 for the last (darker).
    t = (index / (count - 1)) * 2 - 1
    new_l = min(0.80, max(0.32, lightness - t * span))
    nr, ng, nb = colorsys.hls_to_rgb(h, new_l, s)
    return _rgb_to_hex(nr, ng, nb)
