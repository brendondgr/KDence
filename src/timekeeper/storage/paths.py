"""Default on-disk location for the span store (Phase 9, Step 1).

The archive must survive reboots, so the default lives under the XDG **data** dir
(``$XDG_DATA_HOME/timekeeper/tk.db``, fallback ``~/.local/share/timekeeper/tk.db``) -- never
``/tmp``, which is ``tmpfs`` (RAM) on this machine and erased on reboot, making a months/years
record impossible. The collector and the API both default here; the Phase 7 systemd units pass
the same path explicitly, so a service and a hand-run process share one durable archive.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "timekeeper"
STORE_FILENAME = "tk.db"


def data_home() -> Path:
    """The app's XDG data directory (``$XDG_DATA_HOME/timekeeper`` or the spec fallback).

    An unset *or empty* ``XDG_DATA_HOME`` falls back to ``~/.local/share`` per the XDG spec.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def default_store_path(create_parent: bool = True) -> Path:
    """The durable default store file. Creates its parent dir unless ``create_parent=False``.

    ``Store`` opens the SQLite file directly and does not create intermediate dirs, so the
    parent must exist first; creating it here keeps the entry points a one-liner.
    """
    path = data_home() / STORE_FILENAME
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path
