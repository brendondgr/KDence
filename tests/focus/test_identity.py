"""Step 2.2 (synthetic) -- pure tests for window identity + the title-privacy policy."""

from __future__ import annotations

from kdence.focus.identity import NO_WINDOW, WindowIdentity, make_identity


def test_app_class_is_kept_and_title_dropped_by_default() -> None:
    # Default privacy stance: keep the class, never the caption.
    ident = make_identity("firefox", "Secret Doc — Private", capture_titles=False)
    assert ident == WindowIdentity("firefox", None)
    assert ident.title is None
    assert ident.app_class == "firefox"


def test_title_kept_only_when_opted_in() -> None:
    ident = make_identity("firefox", "Inbox (3)", capture_titles=True)
    assert ident == WindowIdentity("firefox", "Inbox (3)")


def test_whitespace_is_normalised() -> None:
    assert make_identity("  konsole ", "  ", capture_titles=True) == WindowIdentity("konsole", None)
    assert make_identity("konsole", "  hi ", capture_titles=True) == WindowIdentity("konsole", "hi")


def test_empty_class_is_the_no_window_identity() -> None:
    # Focus on the desktop / nothing collapses to a single canonical value.
    assert make_identity("", "anything", capture_titles=True) is NO_WINDOW
    assert make_identity("   ", None, capture_titles=False) is NO_WINDOW
    assert NO_WINDOW.is_none is True


def test_three_windows_are_stable_and_distinguishable() -> None:
    # A browser, an editor, a terminal -> three distinct, hashable identities.
    browser = make_identity("firefox", None, capture_titles=False)
    editor = make_identity("code", None, capture_titles=False)
    terminal = make_identity("org.kde.konsole", None, capture_titles=False)
    idents = {browser, editor, terminal}
    assert len(idents) == 3
    # Same class twice -> identical identity (stable), so a re-activation is not "new".
    assert make_identity("firefox", None, capture_titles=False) == browser


def test_label_reflects_only_what_is_held() -> None:
    assert make_identity("konsole", "zsh", capture_titles=False).label == "konsole"
    assert make_identity("konsole", "zsh", capture_titles=True).label == "konsole — zsh"
    assert NO_WINDOW.label == "(no window)"
