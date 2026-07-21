"""Application grouping -- roll per-application totals up into user-defined categories.

Pure, config-only (one JSON file off the span store): :mod:`palette` holds the 12-colour
starting palette + the member-colour ``variant`` maths, and :mod:`categories` holds the
category definitions, the ``app_class -> category`` map, opinionated defaults, and
validation/load/save. The rollup itself (``group_totals``) lives in
:mod:`kdence.api.queries` beside the per-app totals it aggregates.
"""

from __future__ import annotations

from kdence.grouping.categories import (
    DEFAULT_ASSIGNMENTS,
    DEFAULT_CATEGORIES,
    DEFAULT_SITE_ASSIGNMENTS,
    UNCATEGORIZED,
    Category,
    CategoryConfig,
    auto_assign,
    default_config,
    load,
    parse,
    resolve,
    resolve_site,
    save,
    to_dict,
)
from kdence.grouping.palette import (
    PALETTE,
    UNCATEGORIZED_COLOR,
    is_hex_color,
    normalize_color,
    variant,
)

__all__ = [
    "PALETTE",
    "UNCATEGORIZED_COLOR",
    "is_hex_color",
    "normalize_color",
    "variant",
    "UNCATEGORIZED",
    "Category",
    "CategoryConfig",
    "DEFAULT_CATEGORIES",
    "DEFAULT_ASSIGNMENTS",
    "DEFAULT_SITE_ASSIGNMENTS",
    "default_config",
    "resolve",
    "resolve_site",
    "auto_assign",
    "parse",
    "to_dict",
    "load",
    "save",
]
