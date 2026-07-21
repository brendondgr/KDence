"""Step 2.1/2.3 (live) -- smoke test for the KWin focus source.

Marked ``live``: needs a real KDE Plasma 6 / Wayland session with at least one window
focused, and is skipped headless (``uv run pytest -m "not live"``). It proves the read
path end to end: the KWin script loads and reports the currently focused window's class
out of the compositor into our DBus service. Confirming that a *switch* between two apps
changes the identity needs a human at the keyboard and stays a manual check (see the
Phase 2 handoff).
"""

from __future__ import annotations

import asyncio

import pytest

from timekeeper.focus.kwin_source import KWinFocusSource

pytestmark = pytest.mark.live


def test_reports_current_focused_window() -> None:
    async def run() -> list[tuple[str, str]]:
        got: list[tuple[str, str]] = []
        source = KWinFocusSource(on_focus=lambda cls, title: got.append((cls, title)))
        await source.connect()
        try:
            for _ in range(50):  # up to ~5s for the initial report to arrive
                if got:
                    break
                await asyncio.sleep(0.1)
        finally:
            await source.close()
        return got

    got = asyncio.run(run())
    assert got, "KWin did not report a focused window within 5s"
    assert got[0][0], "focused window reported with an empty app class"
