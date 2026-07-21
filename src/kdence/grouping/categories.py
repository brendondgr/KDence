"""Category configuration -- definitions + an ``app_class -> category`` map, and its policy.

This is *configuration*, not span-derived data: which categories exist, their colours, and
which application each belongs to. It is pure apart from reading/writing one JSON file, and it
lives entirely off the single-writer span store (so the store's reader/writer isolation is
untouched). The dashboard reads it to roll totals up by group and writes it back when the user
edits categories.

Two rules are baked in:

- **Uncategorized is reserved.** It always exists, can't be deleted, and catches every app that
  isn't assigned -- so group totals always reconcile with per-app totals.
- **Opinionated defaults.** :data:`DEFAULT_ASSIGNMENTS` seeds common apps into sensible
  categories; anything unknown resolves to Uncategorized until the user says otherwise.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

from kdence.grouping.palette import (
    PALETTE,
    UNCATEGORIZED_COLOR,
    is_hex_color,
    normalize_color,
)

# The reserved bucket for anything unassigned. Never deletable.
UNCATEGORIZED = "uncategorized"

# Guardrails for the write path (a user file, but validate anyway).
MAX_CATEGORIES = 24
MAX_NAME_LEN = 40
MAX_ID_LEN = 40


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    color: str


@dataclass(frozen=True)
class CategoryConfig:
    categories: tuple[Category, ...]
    assignments: dict[str, str]  # app_class -> category id
    site_assignments: dict[str, str] = field(default_factory=dict)  # host -> category id

    def by_id(self) -> dict[str, Category]:
        return {c.id: c for c in self.categories}


DEFAULT_CATEGORIES: tuple[Category, ...] = (
    Category("work", "Work", PALETTE[6]),  # blue
    Category("entertainment", "Entertainment", PALETTE[1]),  # orange
    Category("social", "Social", PALETTE[10]),  # magenta
    Category("games", "Games", PALETTE[3]),  # green
    Category(UNCATEGORIZED, "Uncategorized", UNCATEGORIZED_COLOR),
)

# Opinionated seed: app_class (lowercased) -> category id. Browsers are intentionally left out
# (browsing is ambiguous), so they start Uncategorized for the user to place.
DEFAULT_ASSIGNMENTS: dict[str, str] = {
    # Work
    "code": "work",
    "vscode": "work",
    "code-oss": "work",
    "codium": "work",
    "org.kde.konsole": "work",
    "konsole": "work",
    "org.kde.kate": "work",
    "kate": "work",
    "jetbrains-idea": "work",
    "jetbrains-pycharm": "work",
    "obsidian": "work",
    "thunderbird": "work",
    "slack": "work",
    "com.slack.slack": "work",
    "org.gnome.terminal": "work",
    "alacritty": "work",
    "kitty": "work",
    "foot": "work",
    "libreoffice": "work",
    "com.anthropic.claude": "work",
    # Games
    "steam": "games",
    "lutris": "games",
    "net.lutris.lutris": "games",
    "heroic": "games",
    "org.prismlauncher.prismlauncher": "games",
    # Social
    "discord": "social",
    "com.discordapp.discord": "social",
    "telegram": "social",
    "org.telegram.desktop": "social",
    "signal": "social",
    "org.signal.signal": "social",
    "element": "social",
    # Entertainment
    "spotify": "entertainment",
    "com.spotify.client": "entertainment",
    "vlc": "entertainment",
    "mpv": "entertainment",
    "io.mpv.mpv": "entertainment",
    "org.kde.elisa": "entertainment",
}

# Opinionated seed for browser **sites**: normalised host (lowercased, www. stripped -- as
# `browser.site.normalize_site` produces) -> category id. Powers "Auto-categorize" for sites.
DEFAULT_SITE_ASSIGNMENTS: dict[str, str] = {
    # Entertainment
    "youtube.com": "entertainment",
    "netflix.com": "entertainment",
    "twitch.tv": "entertainment",
    "spotify.com": "entertainment",
    "open.spotify.com": "entertainment",
    "hulu.com": "entertainment",
    "disneyplus.com": "entertainment",
    "soundcloud.com": "entertainment",
    # Work
    "github.com": "work",
    "gitlab.com": "work",
    "stackoverflow.com": "work",
    "docs.google.com": "work",
    "mail.google.com": "work",
    "notion.so": "work",
    "linear.app": "work",
    "figma.com": "work",
    "confluence.atlassian.net": "work",
    "jira.atlassian.net": "work",
    "overleaf.com": "work",
    # Social
    "reddit.com": "social",
    "twitter.com": "social",
    "x.com": "social",
    "facebook.com": "social",
    "instagram.com": "social",
    "linkedin.com": "social",
    "mastodon.social": "social",
    "bsky.app": "social",
    "discord.com": "social",
    # Games
    "steampowered.com": "games",
    "store.steampowered.com": "games",
    "chess.com": "games",
    "lichess.org": "games",
    "ign.com": "games",
}


def default_config() -> CategoryConfig:
    """The out-of-the-box configuration: default categories + the opinionated seed maps."""
    return CategoryConfig(
        DEFAULT_CATEGORIES, dict(DEFAULT_ASSIGNMENTS), dict(DEFAULT_SITE_ASSIGNMENTS)
    )


def resolve(app_class: str | None, config: CategoryConfig) -> str:
    """The category id an app belongs to -- its assignment, or :data:`UNCATEGORIZED`.

    A ``None`` app (the bare desktop) or an assignment pointing at a since-deleted category
    both resolve to Uncategorized, so nothing ever falls out of the totals.
    """
    if app_class is None:
        return UNCATEGORIZED
    cid = config.assignments.get(app_class)
    if cid is None or cid not in config.by_id():
        return UNCATEGORIZED
    return cid


def resolve_site(site: str | None, config: CategoryConfig) -> str | None:
    """The category id a browser **site** is explicitly assigned to, or ``None`` if unassigned.

    ``None`` means "no site-level opinion" -- the caller then falls back to the browser app's
    own category. An assignment pointing at a deleted category is treated as unassigned.
    """
    if not site:
        return None
    cid = config.site_assignments.get(site)
    if cid is None or cid not in config.by_id():
        return None
    return cid


def auto_assign(
    app_classes: list[str | None],
    config: CategoryConfig,
    sites: list[str] | None = None,
) -> CategoryConfig:
    """Fill in categories for the given apps (and optionally sites) from the seed maps.

    Non-destructive: only apps/sites *not already assigned* are touched, and only when the seed
    map knows them; unknown ones are left alone. Returns a new config.
    """
    merged = dict(config.assignments)
    for app in app_classes:
        if app is None or app in merged:
            continue
        seed = DEFAULT_ASSIGNMENTS.get(app.lower())
        if seed is not None:
            merged[app] = seed
    site_merged = dict(config.site_assignments)
    for site in sites or []:
        if not site or site in site_merged:
            continue
        seed = DEFAULT_SITE_ASSIGNMENTS.get(site.lower())
        if seed is not None:
            site_merged[site] = seed
    return replace(config, assignments=merged, site_assignments=site_merged)


# -- (de)serialisation + validation -------------------------------------------


def to_dict(config: CategoryConfig) -> dict:
    return {
        "categories": [{"id": c.id, "name": c.name, "color": c.color} for c in config.categories],
        "assignments": dict(config.assignments),
        "site_assignments": dict(config.site_assignments),
    }


def parse(raw: dict) -> CategoryConfig:
    """Validate a raw dict into a :class:`CategoryConfig`, raising ``ValueError`` on bad input.

    Strict enough for the write endpoint: ids/names non-empty and capped, colours real hex,
    ids unique, count capped. **Uncategorized is force-injected** if missing (it is reserved),
    and any assignment pointing at an unknown category is dropped rather than rejected.
    """
    if not isinstance(raw, dict):
        raise ValueError("config must be an object")
    cats_raw = raw.get("categories")
    if not isinstance(cats_raw, list) or not cats_raw:
        raise ValueError("categories must be a non-empty list")
    if len(cats_raw) > MAX_CATEGORIES:
        raise ValueError(f"too many categories (max {MAX_CATEGORIES})")

    seen: set[str] = set()
    categories: list[Category] = []
    for entry in cats_raw:
        if not isinstance(entry, dict):
            raise ValueError("each category must be an object")
        cid = str(entry.get("id", "")).strip()
        name = str(entry.get("name", "")).strip()
        color = entry.get("color", "")
        if not cid or len(cid) > MAX_ID_LEN:
            raise ValueError(f"bad category id: {cid!r}")
        if not name or len(name) > MAX_NAME_LEN:
            raise ValueError(f"bad category name: {name!r}")
        if not is_hex_color(color):
            raise ValueError(f"bad category color: {color!r}")
        if cid in seen:
            raise ValueError(f"duplicate category id: {cid!r}")
        seen.add(cid)
        categories.append(Category(cid, name, normalize_color(color)))

    if UNCATEGORIZED not in seen:
        categories.append(Category(UNCATEGORIZED, "Uncategorized", UNCATEGORIZED_COLOR))
        seen.add(UNCATEGORIZED)

    assigns_raw = raw.get("assignments", {})
    if not isinstance(assigns_raw, dict):
        raise ValueError("assignments must be an object")
    assignments: dict[str, str] = {}
    for app, cid in assigns_raw.items():
        app_s = str(app).strip()
        cid_s = str(cid).strip()
        if app_s and cid_s in seen and cid_s != UNCATEGORIZED:
            # Storing an explicit Uncategorized is redundant (it's the default), so drop it.
            assignments[app_s] = cid_s

    site_assigns_raw = raw.get("site_assignments", {})
    if not isinstance(site_assigns_raw, dict):
        raise ValueError("site_assignments must be an object")
    site_assignments: dict[str, str] = {}
    for site, cid in site_assigns_raw.items():
        site_s = str(site).strip().lower()  # hosts are matched case-insensitively
        cid_s = str(cid).strip()
        if site_s and cid_s in seen and cid_s != UNCATEGORIZED:
            site_assignments[site_s] = cid_s
    return CategoryConfig(tuple(categories), assignments, site_assignments)


def load(path: str | Path) -> CategoryConfig:
    """Read the config file, falling back to :func:`default_config` if missing or unreadable.

    Resilient by design: a missing or corrupt file must not wedge the dashboard. The strict
    :func:`parse` path is used by the write endpoint to reject bad *input* with a 400.
    """
    p = Path(path)
    if not p.exists():
        return default_config()
    try:
        return parse(json.loads(p.read_text()))
    except (ValueError, OSError, json.JSONDecodeError):
        return default_config()


def save(path: str | Path, config: CategoryConfig) -> None:
    """Atomically write the config as JSON (temp file + ``os.replace``)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".categories-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(to_dict(config), fh, indent=2)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
