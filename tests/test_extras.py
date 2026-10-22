"""Coverage for the 2.0 helpers: drives, space analysis, process lookup,
recommended categories, system tools (dry-run only) and log reading."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

import cpan_core as core


def _make_junction(link, target):
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("mklink /J not available on this system")


# ---------------------------------------------------------- recommended

def test_recommended_ids_follow_default_and_admin(monkeypatch):
    monkeypatch.setattr(core, "junk_categories", lambda: [
        {"id": "a", "default": True, "needs_admin": False},
        {"id": "b", "default": True, "needs_admin": True},
        {"id": "c", "default": False, "needs_admin": False},
        {"id": "d"},  # legacy category without either flag
    ])
    assert core.recommended_junk_ids(admin=False) == ["a"]
    assert core.recommended_junk_ids(admin=True) == ["a", "b"]


def test_scan_junk_reports_progress(monkeypatch, fake_junk):
    monkeypatch.setattr(core, "junk_categories", lambda: fake_junk)
    monkeypatch.setattr(core, "is_admin", lambda: False)
    seen = []
    core.scan_junk(progress=lambda done, total, row:
                   seen.append((done, total, row["id"])))
    assert [s[0] for s in seen] == [1, 2]
    assert all(s[1] == 2 for s in seen)


# --------------------------------------------------------------- drives

def test_list_drives_smoke():
    drives = core.list_drives()
    assert drives, "no fixed drives detected"
    for d in drives:
        assert d["letter"].endswith(":")
        assert d["total"] > 0
        assert 0 <= d["pct"] <= 100
        assert d["used"] + d["free"] == d["total"]


# ------------------------------------------------------- space analysis

def test_scan_child_items_measures_and_sorts(tmp_path):
    (tmp_path / "small.bin").write_bytes(b"x" * 10)
    big = tmp_path / "big"
    big.mkdir()
    (big / "inner.bin").write_bytes(b"y" * 500)
    empty = tmp_path / "empty"
    empty.mkdir()

    begins, items = [], []
    out = core.scan_child_items(str(tmp_path),
                                on_begin=begins.append,
                                on_item=items.append)
    assert [b["name"] for b in begins] and len(begins) == len(out) == 3
    assert out[0]["name"] == "big"
    assert out[0]["size"] == 500 and out[0]["kind"] == "dir"
    by_name = {i["name"]: i for i in out}
    assert by_name["small.bin"]["size"] == 10
    assert by_name["small.bin"]["kind"] == "file"
    assert by_name["empty"]["size"] == 0


def test_scan_child_items_can_be_cancelled(tmp_path):
    for i in range(3):
        (tmp_path / f"d{i}").mkdir()
    out = core.scan_child_items(str(tmp_path), should_stop=lambda: True)
    assert out == []


def test_scan_child_items_missing_dir():
    with pytest.raises(FileNotFoundError):
        core.scan_child_items(r"C:\no\such\dir\for_cpan_test")


# --------------------------------------------------------------- log tail

def test_log_tail_returns_last_lines():
    core.oplog("CLEAN", "one", "OK")
    core.oplog("MOVE", "two", "OK")
    core.oplog("APP-MOVE", "three", "OK")
    tail = core.log_tail(2)
    assert len(tail) == 2
    assert "two" in tail[0] and "three" in tail[1]


def test_log_tail_missing_file_is_empty():
    assert core.log_tail(10) == []


# --------------------------------------------------------- system tools

def test_system_tools_refuse_without_admin(monkeypatch):
    monkeypatch.setattr(core, "is_admin", lambda: False)
    assert "管理员" in core.system_component_cleanup(confirm=True)["note"]
    assert "管理员" in core.set_hibernation(False, confirm=True)["note"]


def test_system_tools_dry_run_does_not_spawn(monkeypatch):
    monkeypatch.setattr(core, "is_admin", lambda: True)
    monkeypatch.setattr(core.subprocess, "run",
                        lambda *a, **k: pytest.fail("dry-run spawned a process"))
    assert core.system_component_cleanup(confirm=False)["dry_run"] is True
    assert core.set_hibernation(False, confirm=False)["dry_run"] is True


# ---------------------------------------------------- junction traversal

def test_dir_stats_does_not_follow_nested_junction(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "big.bin").write_bytes(b"x" * 5000)
    src = tmp_path / "src"
    src.mkdir()
    (src / "own.bin").write_bytes(b"y" * 10)
    _make_junction(src / "link", target)
    assert core._dir_stats(str(src)) == (10, 1)


def test_scan_custom_skips_junction_contents(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "hidden.tmp").write_bytes(b"x" * 20)
    root = tmp_path / "root"
    root.mkdir()
    _make_junction(root / "link", target)
    assert core.scan_custom(str(root), [".tmp"]) == []


def test_clean_root_preserves_junction_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    keep = target / "keep.txt"
    keep.write_bytes(b"keep me")
    root = tmp_path / "cache"
    root.mkdir()
    (root / "junk.tmp").write_bytes(b"x" * 7)
    _make_junction(root / "link", target)
    report = {"bytes": 0, "deleted": 0, "skipped": 0}
    core._clean_root(str(root), "no_filter", report)
    assert report["deleted"] == 1
    assert keep.exists()


def test_copy_tree_does_not_copy_junction_contents(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "data.bin").write_bytes(b"x" * 100)
    src = tmp_path / "src"
    src.mkdir()
    (src / "own.bin").write_bytes(b"y" * 5)
    _make_junction(src / "link", target)
    dst = tmp_path / "dst"
    dst.mkdir()
    rp = core.ProgressReporter(1, None)
    core._copy_tree(str(src), str(dst), rp, "copy")
    assert (dst / "own.bin").exists()
    assert not (dst / "link").exists()


def test_move_refuses_junction_source(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    _make_junction(link, target)
    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(PermissionError):
        core.move_path(str(link), str(dst), confirm=False)


# ------------------------------------------------------------- processes

def test_running_processes_under_detects_python():
    procs = core.running_processes_under(os.path.dirname(sys.executable))
    assert isinstance(procs, list)
    if not procs:
        pytest.skip("process path lookup unavailable in this environment")
    assert any(p["pid"] == os.getpid() for p in procs)
    assert all(p["exe"].lower().startswith(
        os.path.dirname(sys.executable).lower()) for p in procs)


# --------------------------------------------------------- move guardrails

def test_move_refuses_destination_inside_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.bin").write_bytes(b"x")
    nested = src / "nested"
    nested.mkdir()
    rep = core.move_path(str(src), str(nested), confirm=False)
    assert rep["ok"] is False
    assert "内部" in rep["note"]


def test_move_app_refuses_program_files_root_without_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "is_admin", lambda: False)
    rep = core.move_app(r"C:\Program Files", str(tmp_path), confirm=False)
    assert rep["ok"] is False
    assert "Program Files" in rep["note"]


def test_move_app_refuses_target_inside_source(monkeypatch, tmp_path):
    src = tmp_path / "app"
    src.mkdir()
    (src / "app.exe").write_bytes(b"x")
    nested = src / "nested"
    nested.mkdir()
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    rep = core.move_app(str(src), str(nested), confirm=False)
    assert rep["ok"] is False
    assert "内部" in rep["note"]
