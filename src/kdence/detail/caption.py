"""Pure caption-identity policy -- a window title in, a storable detail label out.

This is the logic side of the caption seam (Tier 1). The hardware side (the KWin script +
:mod:`kdence.focus.kwin_source`) only forwards the focused window's raw ``caption``; deciding
*what a caption means to this system* -- the document/tab/track you were on, with the app's own
name stripped and any filesystem path generalised away -- happens here so it stays unit-testable,
exactly like :mod:`kdence.browser.site` does for hostnames.

Captions are unstructured and app-specific, so parsing is a heuristic:

1. **Strip the app-name suffix.** KDE/Qt/GTK apps render captions as ``"<subject> — <AppName>"``
   (em dash is the KDE convention) or ``"<subject> - <AppName>"``. Knowing the focused
   ``app_class`` we strip a trailing ``"<sep> <AppName>"``; failing that we strip after the last
   em/en dash (a strong app-suffix signal). What remains is the *subject* -- the document, tab,
   folder, or track.
2. **Generalise local files (privacy).** A subject that is a filesystem path (``/``, ``~``, a
   ``file://`` URL, a Windows-style ``\\``) never gets logged by name -- it collapses to the
   single :data:`LOCAL_FILE` sentinel, mirroring :data:`kdence.browser.site.LOCAL_APP`. A bare
   filename (``notes.md``) is kept: it is a label, not a path.

The **denylist** (never detail these app classes at all) is enforced one level up, in
:class:`kdence.collector.providers.DetailRegistry`, so it applies uniformly to every provider.
"""

from __future__ import annotations

# The one bucket every filesystem-path subject collapses into; compares equal across the app.
LOCAL_FILE = "(local file)"

# Separators an app-name suffix hangs off, longest/most-specific first. Em dash and en dash are
# the KDE/Qt convention; the spaced hyphen is common in GTK/Electron apps.
_SEPARATORS = (" — ", " – ", " - ")

# app_class substring (lowercased) -> the app-name token(s) that appear as a caption suffix.
# Matched by substring so both the reverse-DNS class ("org.kde.kate") and a bare class ("kate")
# resolve. Users can extend this; an unmatched app falls back to the generic em/en-dash strip.
_APP_NAMES: dict[str, tuple[str, ...]] = {
    "kate": ("Kate",),
    "okular": ("Okular",),
    "dolphin": ("Dolphin",),
    "konsole": ("Konsole",),
    "kdevelop": ("KDevelop",),
    "gwenview": ("Gwenview",),
    "elisa": ("Elisa",),
    "ark": ("Ark",),
    "kwrite": ("KWrite",),
    "libreoffice": (
        "LibreOffice Writer",
        "LibreOffice Calc",
        "LibreOffice Impress",
        "LibreOffice Draw",
        "LibreOffice",
    ),
    "gimp": ("GIMP",),
    "vlc": ("VLC media player", "VLC"),
    "mpv": ("mpv",),
    "dragonplayer": ("Dragon Player",),
    "firefox": ("Mozilla Firefox", "Firefox"),
    "librewolf": ("LibreWolf",),
    "code": ("Visual Studio Code",),
}


def _app_names_for(app_class: str | None) -> tuple[str, ...]:
    cls = (app_class or "").strip().lower()
    if not cls:
        return ()
    for key, names in _APP_NAMES.items():
        if key in cls:
            return names
    return ()


def _looks_like_path(subject: str) -> bool:
    """True when ``subject`` is a filesystem path we must not log by name.

    Covers POSIX paths (a ``/`` anywhere, or a leading ``~``), ``file://`` URLs, and
    Windows-style backslash paths. A bare filename with an extension (``notes.md``) has no
    separator and is kept -- it is a label, not a path.
    """
    s = subject.strip()
    if not s:
        return False
    lowered = s.lower()
    if lowered.startswith("file://") or lowered.startswith("~"):
        return True
    return "/" in s or "\\" in s


def _strip_app_suffix(app_class: str | None, caption: str) -> str:
    """Remove a trailing ``"<sep> <AppName>"`` from ``caption``; return the subject."""
    for name in _app_names_for(app_class):
        for sep in _SEPARATORS:
            suffix = f"{sep}{name}"
            if caption.lower().endswith(suffix.lower()):
                return caption[: -len(suffix)]
    # Fall back to the KDE em/en-dash convention: strip after the last such separator.
    for sep in _SEPARATORS[:2]:  # em dash, en dash only -- hyphen is too ambiguous generically
        idx = caption.rfind(sep)
        if idx > 0:
            return caption[:idx]
    return caption


def parse_caption(app_class: str | None, caption: str | None) -> str | None:
    """Reduce a raw window caption to the in-app detail label this system stores.

    Returns the subject (document / tab / folder / track) with the app name stripped, the
    :data:`LOCAL_FILE` sentinel when the subject is a filesystem path, or ``None`` when there is
    nothing loggable -- an empty caption, or one that was only the app's own name.
    """
    cap = " ".join((caption or "").split())  # collapse whitespace
    if not cap:
        return None
    subject = _strip_app_suffix(app_class, cap).strip()
    # A caption that was *only* the app name (nothing before the suffix) is not a document.
    if not subject or subject.lower() in {n.lower() for n in _app_names_for(app_class)}:
        return None
    if _looks_like_path(subject):
        return LOCAL_FILE
    return subject
