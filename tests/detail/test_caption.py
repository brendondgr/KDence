"""Pure tests for the caption -> detail policy (Phase 13.2)."""

from __future__ import annotations

import pytest

from kdence.detail.caption import LOCAL_FILE, parse_caption


@pytest.mark.parametrize(
    ("app_class", "caption", "expected"),
    [
        # KDE apps: "<subject> — <AppName>" (em dash) -> subject.
        ("org.kde.kate", "notes.md — Kate", "notes.md"),
        ("org.kde.okular", "report.pdf — Okular", "report.pdf"),
        ("org.kde.dolphin", "Documents — Dolphin", "Documents"),
        ("org.kde.kdevelop", "kdence — KDevelop", "kdence"),
        # A bare class (no reverse-DNS) still matches by substring.
        ("kate", "draft — Kate", "draft"),
        # GTK/Electron " - <AppName>" suffix, matched via the known app name.
        ("code", "timeline.py - Visual Studio Code", "timeline.py"),
        # LibreOffice has several product names; the specific one is stripped.
        ("libreoffice-writer", "letter.odt — LibreOffice Writer", "letter.odt"),
        # Unknown app, but the em-dash convention still yields the subject.
        ("some.random.app", "Chapter 3 — My Reader", "Chapter 3"),
    ],
)
def test_strips_app_suffix_to_the_subject(app_class, caption, expected) -> None:
    assert parse_caption(app_class, caption) == expected


def test_a_caption_that_is_only_the_app_name_is_not_a_document() -> None:
    assert parse_caption("org.kde.kate", "Kate") is None
    assert parse_caption("org.kde.dolphin", "Dolphin") is None


@pytest.mark.parametrize("caption", ["", "   ", None])
def test_empty_caption_is_none(caption) -> None:
    assert parse_caption("org.kde.kate", caption) is None


@pytest.mark.parametrize(
    "caption",
    [
        "/home/bdgr/secret/plan.md — Kate",
        "~/taxes/2025.ods — LibreOffice Calc",
        "file:///home/bdgr/notes.txt — Okular",
        r"C:\Users\me\report.docx — LibreOffice Writer",
    ],
)
def test_filesystem_paths_generalise_to_local_file(caption) -> None:
    # A path would leak directory structure -> collapse to the generic bucket.
    assert parse_caption("org.kde.kate", caption) == LOCAL_FILE


def test_bare_filename_is_kept_but_a_path_is_not() -> None:
    assert parse_caption("org.kde.kate", "notes.md — Kate") == "notes.md"
    assert parse_caption("org.kde.kate", "sub/notes.md — Kate") == LOCAL_FILE


def test_whitespace_is_collapsed() -> None:
    assert parse_caption("org.kde.kate", "  spaced   out  — Kate ") == "spaced out"


def test_no_suffix_passthrough() -> None:
    # A window with a title but no recognisable app suffix keeps the whole title.
    assert parse_caption("some.app", "Just A Title") == "Just A Title"
