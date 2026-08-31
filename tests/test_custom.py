"""Custom cleanup: rule scanning and recycle-bin deletion."""

from __future__ import annotations

import os
import time

import pytest

import cpan_core as core


# ------------------------------------------------------------- scan_custom

def _mkfiles(root):
    (root / "old.tmp").write_bytes(b"a" * 100)
    (root / "new.tmp").write_bytes(b"b" * 100)
    (root / "big.log").write_bytes(b"c" * (3 * 1024 * 1024))
    (root / "keep.txt").write_bytes(b"d" * 10)
    old = time.time() - 40 * 86400
    os.utime(root / "old.tmp", (old, old))


def test_scan_custom_extension_filter_with_and_without_dot(tmp_path):
    _mkfiles(tmp_path)
    hits = core.scan_custom(str(tmp_path), exts=[".tmp"])
    assert {os.path.basename(h["path"]) for h in hits} == {"old.tmp", "new.tmp"}
    hits2 = core.scan_custom(str(tmp_path), exts=["tmp"])   # no dot accepted
    assert len(hits2) == 2


def test_scan_custom_extension_case_insensitive(tmp_path):
    (tmp_path / "UPPER.TMP").write_bytes(b"x")
    hits = core.scan_custom(str(tmp_path), exts=[".tmp"])
    assert len(hits) == 1


def test_scan_custom_min_size_filter(tmp_path):
    _mkfiles(tmp_path)
    hits = core.scan_custom(str(tmp_path), min_mb=1)
    assert [os.path.basename(h["path"]) for h in hits] == ["big.log"]


def test_scan_custom_older_days_filter(tmp_path):
    _mkfiles(tmp_path)
    hits = core.scan_custom(str(tmp_path), older_days=30)
    assert [os.path.basename(h["path"]) for h in hits] == ["old.tmp"]
    assert core.scan_custom(str(tmp_path), older_days=365) == []


def test_scan_custom_combined_filters_are_and(tmp_path):
    _mkfiles(tmp_path)
    hits = core.scan_custom(str(tmp_path), exts=[".tmp"], older_days=30, min_mb=1)
    assert hits == []                     # old.tmp is too small
    hits2 = core.scan_custom(str(tmp_path), exts=[".log"], min_mb=1)
    assert len(hits2) == 1


def test_scan_custom_sorted_by_size_desc(tmp_path):
    _mkfiles(tmp_path)
    hits = core.scan_custom(str(tmp_path))
    sizes = [h["size"] for h in hits]
    assert sizes == sorted(sizes, reverse=True)


def test_scan_custom_refuses_protected_root():
    with pytest.raises(PermissionError):
        core.scan_custom(r"C:\Windows", exts=[".tmp"])


def test_scan_custom_missing_root_raises():
    with pytest.raises(FileNotFoundError):
        core.scan_custom(r"Q:\no\such\dir")


def test_scan_custom_skips_symlinked_files(tmp_path):
    target = tmp_path / "t.log"
    target.write_bytes(b"x" * 50)
    try:
        os.symlink(str(target), str(tmp_path / "l.log"))
    except OSError:
        pytest.skip("symlink creation not permitted on this system")
    hits = core.scan_custom(str(tmp_path), exts=[".log"])
    assert [os.path.basename(h["path"]) for h in hits] == ["t.log"]


# ----------------------------------------------------------- delete_custom

def test_delete_custom_dry_run_sends_nothing(monkeypatch, tmp_path):
    f = tmp_path / "victim.tmp"
    f.write_bytes(b"x" * 10)
    rep = core.delete_custom([str(f)], confirm=False)
    assert rep["dry_run"] is True and rep["ok"] == 0
    assert f.exists()
    assert rep["bytes"] == 10


def test_delete_custom_confirm_uses_recycle(monkeypatch, tmp_path):
    f1 = tmp_path / "a.tmp"
    f2 = tmp_path / "b.tmp"
    f1.write_bytes(b"x" * 10)
    f2.write_bytes(b"y" * 20)
    sent = []
    monkeypatch.setattr(core, "send_to_recycle",
                        lambda paths: (sent.extend([list(paths)]), (True, "ok"))[1])
    rep = core.delete_custom([str(f1), str(f2)], confirm=True)
    assert rep["ok"] == 2 and not rep["failed"]
    assert rep["bytes"] == 30
    assert sorted(sent[0]) == sorted([str(f1), str(f2)])
    log = open(core.LOG_FILE, encoding="utf-8").read()
    assert log.count("| RECYCLE |") == 2


def test_delete_custom_reports_recycle_failure(monkeypatch, tmp_path):
    f = tmp_path / "a.tmp"
    f.write_bytes(b"x")
    monkeypatch.setattr(core, "send_to_recycle",
                        lambda paths: (False, "locked by explorer"))
    rep = core.delete_custom([str(f)], confirm=True)
    assert rep["ok"] == 0
    assert any("locked by explorer" in msg for msg in rep["failed"])


def test_delete_custom_refuses_protected_and_keeps_others(monkeypatch, tmp_path):
    good = tmp_path / "ok.tmp"
    good.write_bytes(b"x")
    sent = []
    monkeypatch.setattr(core, "send_to_recycle",
                        lambda paths: (sent.extend([list(paths)]), (True, "ok"))[1])
    rep = core.delete_custom([r"C:\Windows\System32\evil.dll", str(good)],
                             confirm=True)
    assert len(rep["failed"]) == 1
    assert "protected" in rep["failed"][0]
    assert rep["ok"] == 1
    assert sent[0] == [str(good)]


def test_delete_custom_directory_size_counted(monkeypatch, tmp_path):
    d = tmp_path / "folder"
    d.mkdir()
    (d / "inner.bin").write_bytes(b"z" * 4096)
    monkeypatch.setattr(core, "send_to_recycle", lambda paths: (True, "ok"))
    rep = core.delete_custom([str(d)], confirm=False)
    assert rep["bytes"] == 4096
