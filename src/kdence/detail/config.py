"""Runtime detail-provider config -- the toggle state the dashboard writes and the collector reads.

The in-app detail providers (caption, MPRIS) are opt-in and default OFF (privacy). Phase 13 chose
them at collector *startup* via ``KDENCE_DETAIL_PROVIDERS`` / ``--detail-providers``. This adds a
small JSON file (``$XDG_CONFIG_HOME/kdence/detail.json``) so the choice can be flipped **live from
the dashboard** without editing ``.env`` or restarting: the API's ``POST /api/detail`` writes it
(validated + atomic, exactly like ``categories.json``), and the collector re-reads it each interval
and reconfigures its providers on the fly.

Precedence: when the file exists it is authoritative (the UI owns the live toggle); when it is
absent the collector falls back to its startup flags/env. So ``.env`` still sets the *initial*
default, and the dashboard overrides it at runtime. Kept off the span store, like all config, so
the store's single-writer isolation is untouched.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# The opt-in, toggleable providers. ``site`` is intentionally NOT here: it is the pre-existing
# browser feature, gated by the tab-ingest/extension rather than by this toggle, and always on.
PROVIDERS: tuple[str, ...] = ("caption", "mpris")

# Human-facing blurbs the dashboard shows next to each toggle (kept server-side so there is one
# source of truth for what each provider records).
PROVIDER_LABELS: dict[str, str] = {
    "caption": "Documents & files (window title)",
    "mpris": "Media (playing track, via MPRIS)",
}


@dataclass(frozen=True)
class DetailConfig:
    """Which opt-in providers are enabled + which app classes are never detailed."""

    providers: frozenset[str] = frozenset()
    denylist: frozenset[str] = frozenset()


def parse(raw: object, *, strict: bool = False) -> DetailConfig:
    """Validate a ``{"providers": [...], "denylist": [...]}`` mapping into a :class:`DetailConfig`.

    ``strict=True`` (the write path) raises :class:`ValueError` on a bad shape or an unknown
    provider name, so a bad POST becomes a 400 rather than a surprising silent drop. The lenient
    default (the read path) simply ignores unknown provider names so a hand-edited file never wedges.
    """
    if not isinstance(raw, dict):
        raise ValueError("detail config must be an object")
    provs_raw = raw.get("providers", [])
    deny_raw = raw.get("denylist", [])
    if not isinstance(provs_raw, list) or not isinstance(deny_raw, list):
        raise ValueError("'providers' and 'denylist' must be arrays")

    providers: set[str] = set()
    for item in provs_raw:
        name = str(item).strip().lower()
        if name in PROVIDERS:
            providers.add(name)
        elif name and strict:
            raise ValueError(f"unknown provider {name!r} (known: {', '.join(PROVIDERS)})")

    denylist = {str(item).strip() for item in deny_raw if str(item).strip()}
    return DetailConfig(frozenset(providers), frozenset(denylist))


def to_dict(config: DetailConfig) -> dict:
    """Serialise a :class:`DetailConfig` to plain JSON-able data (sorted for stable diffs)."""
    return {"providers": sorted(config.providers), "denylist": sorted(config.denylist)}


def load(path: str | Path) -> DetailConfig | None:
    """Read the config file. ``None`` when it does not exist (so the caller uses its startup
    default); a present-but-corrupt file reads as an empty (all-OFF) config -- never a crash."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return parse(json.loads(p.read_text()))
    except (ValueError, OSError, json.JSONDecodeError):
        return DetailConfig()


def save(path: str | Path, config: DetailConfig) -> None:
    """Atomically write the config as JSON (temp file + ``os.replace``), mirroring categories."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".detail-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(to_dict(config), fh, indent=2)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
