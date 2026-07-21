"""Single-writer SQLite storage under the pure time model (build-plan Phase 4.3).

See :mod:`kdence.storage.store`. ``sqlite3`` is stdlib -- no runtime dependency.
"""

from __future__ import annotations

from kdence.storage.reader import SpanReader
from kdence.storage.store import SpanRow, Store

__all__ = ["SpanReader", "SpanRow", "Store"]
