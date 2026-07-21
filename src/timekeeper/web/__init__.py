"""Live view assets (build-plan Phase 6).

Static files (dashboard HTML/CSS/JS + vendored ECharts and JetBrains Mono) served by the
Phase 5 read-back API. Kept inside the package so the path resolves whether run from source
or installed, mirroring how ``focus/`` ships its KWin script asset.
"""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"

__all__ = ["STATIC_DIR"]
