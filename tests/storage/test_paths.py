"""Step 9.1 (headless) -- the durable default store path.

The archive must land somewhere that survives a reboot. These assert the XDG default is
honored, the parent dir is created (``Store`` won't make it), and that ``/tmp`` is never the
default -- the data-loss trap this step exists to close.
"""

from __future__ import annotations

from pathlib import Path

from timekeeper.storage import paths


def test_honors_xdg_data_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    got = paths.default_store_path()
    assert got == tmp_path / "xdg" / "timekeeper" / "tk.db"


def test_creates_the_parent_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    got = paths.default_store_path()
    assert got.parent.is_dir()  # Store opens the file directly and won't create this


def test_create_parent_can_be_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    got = paths.default_store_path(create_parent=False)
    assert not got.parent.exists()


def test_falls_back_to_local_share_when_xdg_unset(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    got = paths.default_store_path()
    assert got == tmp_path / "home" / ".local" / "share" / "timekeeper" / "tk.db"


def test_empty_xdg_data_home_falls_back(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "")  # set-but-empty -> spec fallback
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    got = paths.default_store_path()
    assert got == tmp_path / "home" / ".local" / "share" / "timekeeper" / "tk.db"


def test_default_lives_under_the_xdg_app_dir_not_a_hardcoded_tmp(tmp_path, monkeypatch) -> None:
    # The whole point of this step: the default follows XDG (durable), not a fixed /tmp path.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    got = paths.default_store_path()
    assert got.name == "tk.db"
    assert got.parent.name == "timekeeper"
    assert got.is_relative_to(tmp_path / "xdg")  # honors the configured data home
