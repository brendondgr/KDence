"""Focus detection: which application is focused right now.

Public surface (mirrors the activity package's pure/hardware seam):

- :class:`WindowIdentity` / :func:`make_identity` -- pure identity + privacy policy.
- :class:`FocusReporter` -- pure "current focused window" tracker (no hardware).
- :class:`KWinFocusSource` -- the KWin-script + DBus client (the hardware side).

See docs/plans/phase-2-focus-detection.md for the design and Step 2.1 platform proof.
"""

from kdence.focus.identity import NO_WINDOW, WindowIdentity, make_identity
from kdence.focus.kwin_source import KWinFocusSource
from kdence.focus.reporter import FocusReporter

__all__ = [
    "NO_WINDOW",
    "FocusReporter",
    "KWinFocusSource",
    "WindowIdentity",
    "make_identity",
]
