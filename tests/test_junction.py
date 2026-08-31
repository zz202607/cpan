"""Real NTFS junction detection (mklink /J needs no admin rights)."""

from __future__ import annotations

import os
import subprocess

import pytest

import cpan_core as core


def _make_junction(link: str, target: str):
    subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                   check=True, capture_output=True)


@pytest.fixture
def junction(tmp_path):
    target = tmp_path / "target"
    (target / "inner").mkdir(parents=True)
    (target / "inner" / "f.bin").write_bytes(b"x" * 10)
    link = str(tmp_path / "link")
    try:
        _make_junction(link, str(target))
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("mklink /J not available on this system")
    return link, target


def test_is_junction_true_for_junction(junction):
    link, _ = junction
    assert core.is_junction(link) is True


def test_is_junction_reads_through_junction(junction):
    link, _ = junction
    # size accounting through the junction must match the target
    assert core.dir_size(link) == core.dir_size(os.path.join(link, "..", "target"))


def test_is_junction_false_for_plain_dir(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert core.is_junction(str(d)) is False


def test_is_junction_false_for_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    assert core.is_junction(str(f)) is False


def test_is_junction_false_for_missing_path(tmp_path):
    assert core.is_junction(str(tmp_path / "ghost")) is False


def test_c_drive_apps_keeps_real_c_folder(monkeypatch, tmp_path):
    """Baseline: a real folder on C: outside Windows/profile IS a candidate."""
    loc = tmp_path / "install"
    loc.mkdir()
    fake_items = [{"name": "GoodApp", "publisher": "", "version": "",
                   "size_kb": 123, "install_date": "",
                   "install_location": str(loc), "uninstall": "x",
                   "quiet_uninstall": ""}]
    monkeypatch.setattr(core, "list_installed", lambda: fake_items)
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    out = core.c_drive_apps()
    assert len(out) == 1 and out[0]["name"] == "GoodApp"
    assert out[0]["install_location"] == os.path.abspath(str(loc))


def test_c_drive_apps_skips_junction_locations(monkeypatch, tmp_path):
    """An install location that is already a junction must not be offered
    as a move candidate (the app already lives elsewhere)."""
    loc = tmp_path / "linked_install"
    loc.mkdir()
    fake_items = [{"name": "JunctionApp", "publisher": "", "version": "",
                   "size_kb": 0, "install_date": "",
                   "install_location": str(loc), "uninstall": "x",
                   "quiet_uninstall": ""}]
    monkeypatch.setattr(core, "list_installed", lambda: fake_items)
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    monkeypatch.setattr(core, "is_junction", lambda p: True)
    assert core.c_drive_apps() == []
