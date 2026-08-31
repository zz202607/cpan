"""Directory size accounting: _dir_stats / dir_size."""

from __future__ import annotations

import os

import pytest

import cpan_core as core


def test_dir_stats_sums_files_and_counts(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"y" * 200)
    empty = tmp_path / "emptydir"
    empty.mkdir()
    total, count = core._dir_stats(str(tmp_path))
    assert total == 300
    assert count == 2


def test_dir_size_matches_dir_stats(tmp_path):
    (tmp_path / "f.dat").write_bytes(b"z" * 1234)
    assert core.dir_size(str(tmp_path)) == 1234


def test_dir_stats_empty_dir(tmp_path):
    assert core._dir_stats(str(tmp_path)) == (0, 0)


def test_dir_stats_missing_dir_is_zero():
    assert core._dir_stats(r"C:\no\such\dir\anywhere") == (0, 0)


def test_dir_stats_skips_symlinked_files(tmp_path):
    target = tmp_path / "target.bin"
    target.write_bytes(b"x" * 500)
    link = tmp_path / "link.bin"
    try:
        os.symlink(str(target), str(link))
    except OSError:
        pytest.skip("symlink creation not permitted on this system")
    total, count = core._dir_stats(str(tmp_path))
    assert (total, count) == (500, 1)  # link must not be double-counted
