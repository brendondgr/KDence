"""Phase 7 productionization: systemd user units + soak summary.

Pure, headless-testable pieces (unit-file rendering, resource-summary math) live here beside
the thin ops CLI (``python -m kdence.service``). Enabling units and the full-day soak run
are live gates -- see ``docs/plans/phase-7-productionization.md``.
"""

from __future__ import annotations

from kdence.service.soak import Sample, SoakSummary, summarize
from kdence.service.units import (
    API_SERVICE,
    COLLECTOR_SERVICE,
    DEFAULT_STORE,
    UnitContext,
    api_unit,
    collector_unit,
    render_all,
)

__all__ = [
    "API_SERVICE",
    "COLLECTOR_SERVICE",
    "DEFAULT_STORE",
    "Sample",
    "SoakSummary",
    "UnitContext",
    "api_unit",
    "collector_unit",
    "render_all",
    "summarize",
]
