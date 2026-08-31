"""Junk categories: structure, scan, and clean behavior."""

from __future__ import annotations

import os

import pytest

import cpan_core as core


# ------------------------------------------------------------- structure

def test_real_categories_well_formed():
    cats = core.junk_categories()
    ids = [c["id"] for c in cats]
    assert len(ids) == len(set(ids)), "duplicate category ids"
    for c in cats:
        assert {"id", "name", "desc", "roots"} <= set(c)
        assert isinstance(c["roots"], list)
    assert "recycle_bin" in ids
    recycle = next(c for c in cats if c["id"] == "recycle_bin")
    assert recycle.get("special") == "recycle"


def test_thumbs_category_has_prefix_filter():
    cats = {c["id"]: c for c in core.junk_categories()}
    assert "thumbs" in cats
    # Explorer dir holds non-cache files; the filter must exist to protect them
    assert core._ROOT_FILE_FILTERS.get("thumbs"), \
        "thumbs cleanup without a filename filter would delete non-cache files"


def test_admin_flags_match_expert_doc():
    cats = {c["id"]: c for c in core.junk_categories()}
    for needs_admin in ("win_temp", "wu_cache", "wer", "windows_old"):
        assert cats[needs_admin]["needs_admin"] is True
    for plain_user in ("user_temp", "thumbs", "chrome_cache", "edge_cache",
                       "firefox_cache", "d3d_cache", "recycle_bin"):
        assert cats[plain_user]["needs_admin"] is False


# ---------------------------------------------------------------- scan

def test_scan_junk_sizes_and_admin_skip(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    monkeypatch.setattr(core, "is_admin", lambda: False)
    rows = {r["id"]: r for r in core.scan_junk()}
    assert rows["fake"]["size"] == 1500
    assert rows["fake"]["files"] == 2
    assert rows["fake"]["skipped"] == ""
    assert rows["adm"]["skipped"] != ""          # admin note present
    assert rows["adm"]["size"] == 250            # still measured for display


def test_scan_junk_admin_has_no_skip_note(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    monkeypatch.setattr(core, "is_admin", lambda: True)
    rows = {r["id"]: r for r in core.scan_junk()}
    assert rows["adm"]["skipped"] == ""


def test_scan_junk_recycle_special(monkeypatch, fake_junk_with_recycle):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk_with_recycle)
    monkeypatch.setattr(core, "is_admin", lambda: False)
    monkeypatch.setattr(core, "recycle_bin_stats", lambda: (7777, 9))
    rows = {r["id"]: r for r in core.scan_junk()}
    assert rows["recycle_bin"]["size"] == 7777
    assert rows["recycle_bin"]["files"] == 9


# ------------------------------------------------------------ _clean_root

def test_clean_root_deletes_and_removes_empty_dirs(tmp_path):
    root = tmp_path / "root"
    (root / "keep" / "deep").mkdir(parents=True)
    (root / "keep" / "deep" / "junk.tmp").write_bytes(b"a" * 10)
    report = {"bytes": 0, "deleted": 0, "skipped": 0}
    core._clean_root(str(root), "no_filter", report)
    assert report["deleted"] == 1 and report["bytes"] == 10
    assert root.is_dir()                          # root itself survives
    assert not (root / "keep").exists()           # emptied dirs removed


def test_clean_root_prefix_filter_keeps_other_files(tmp_path):
    root = tmp_path / "explorer"
    root.mkdir()
    (root / "thumbcache_1024.db").write_bytes(b"x" * 100)
    (root / "iconcache_idx.db").write_bytes(b"x" * 50)
    (root / "settings.ini").write_bytes(b"x" * 30)   # must survive
    report = {"bytes": 0, "deleted": 0, "skipped": 0}
    core._clean_root(str(root), "thumbs", report)
    assert report["deleted"] == 2
    assert (root / "settings.ini").exists()
    assert not (root / "thumbcache_1024.db").exists()


def test_clean_root_skips_busy_file(tmp_path):
    root = tmp_path / "busy"
    root.mkdir()
    busy = root / "locked.tmp"
    busy.write_bytes(b"x" * 10)
    report = {"bytes": 0, "deleted": 0, "skipped": 0}
    fh = open(busy, "w")          # held open -> os.remove fails on Windows
    try:
        core._clean_root(str(root), "no_filter", report)
    finally:
        fh.close()
    assert report["skipped"] == 1
    assert report["deleted"] == 0
    assert busy.exists()


def test_clean_root_leaves_symlinked_file_alone(tmp_path):
    root = tmp_path / "withlink"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"v" * 99)
    try:
        os.symlink(str(outside), str(root / "link.bin"))
    except OSError:
        pytest.skip("symlink creation not permitted on this system")
    report = {"bytes": 0, "deleted": 0, "skipped": 0}
    core._clean_root(str(root), "no_filter", report)
    assert outside.exists()       # link target untouched


# ------------------------------------------------------------- clean_junk

def test_clean_junk_dry_run_touches_nothing(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    monkeypatch.setattr(core, "is_admin", lambda: True)
    rep = core.clean_junk(["fake", "adm"], confirm=False)
    assert rep["dry_run"] is True
    assert rep["deleted"] == 0
    root = fake_junk[0]["roots"][0]
    assert os.path.exists(os.path.join(root, "a.tmp"))
    assert not os.path.exists(core.LOG_FILE)      # dry-run writes no log


def test_clean_junk_confirm_deletes_and_logs(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    monkeypatch.setattr(core, "is_admin", lambda: True)
    rep = core.clean_junk(["fake"], confirm=True)
    assert rep["dry_run"] is False
    assert rep["deleted"] == 2 and rep["bytes"] == 1500
    root = fake_junk[0]["roots"][0]
    assert not os.path.exists(os.path.join(root, "a.tmp"))
    log = open(core.LOG_FILE, encoding="utf-8").read()
    assert "| CLEAN |" in log


def test_clean_junk_non_admin_skips_admin_categories(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    monkeypatch.setattr(core, "is_admin", lambda: False)
    rep = core.clean_junk(["fake", "adm"], confirm=True)
    adminroot = fake_junk[1]["roots"][0]
    assert os.path.exists(os.path.join(adminroot, "c.dat"))   # untouched
    assert any("跳过" in d for d in rep["details"])


def test_clean_junk_recycle_confirm_calls_api(monkeypatch, fake_junk_with_recycle):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk_with_recycle)
    monkeypatch.setattr(core, "is_admin", lambda: False)
    monkeypatch.setattr(core, "recycle_bin_stats", lambda: (7777, 9))
    calls = []
    monkeypatch.setattr(core, "empty_recycle_bin",
                        lambda: (calls.append(1), (True, "ok"))[1])
    rep = core.clean_junk(["recycle_bin"], confirm=True)
    assert calls == [1]
    assert rep["bytes"] == 7777 and rep["deleted"] == 9


def test_clean_junk_recycle_dry_run_does_not_call_api(monkeypatch, fake_junk_with_recycle):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk_with_recycle)
    monkeypatch.setattr(core, "recycle_bin_stats", lambda: (7777, 9))
    monkeypatch.setattr(core, "empty_recycle_bin",
                        lambda: pytest.fail("dry-run must not empty the bin"))
    rep = core.clean_junk(["recycle_bin"], confirm=False)
    assert rep["deleted"] == 0


def test_clean_junk_unknown_category_ignored(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    rep = core.clean_junk(["no_such_category"], confirm=True)
    assert rep["deleted"] == 0


def test_clean_junk_progress_callback(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    monkeypatch.setattr(core, "is_admin", lambda: True)
    events = []
    core.clean_junk(["fake"], confirm=True,
                    progress=lambda pct, label, d, t: events.append(pct))
    assert events and events[-1] == 100
