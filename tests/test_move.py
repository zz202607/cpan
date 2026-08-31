"""File move (move_path) and app relocation via junction (move_app).

Includes regression tests for data-loss scenarios: a cross-drive move where
some files fail to copy must NEVER delete the source.
"""

from __future__ import annotations

import os
import subprocess

import pytest

import cpan_core as core


def _fake_splitdrive_cross(path):
    """Pretend the destination (anything under ...\dest...) lives on D: while
    the source stays on C:, so same-drive logic treats the pair as
    cross-drive."""
    if "\\dest" in path.lower():
        return ("d:", path[2:])
    return ("c:", path[2:])


# --------------------------------------------------------------- move_path

def test_move_path_dry_run_changes_nothing(tmp_path):
    src = tmp_path / "moveme"
    src.mkdir()
    (src / "f.bin").write_bytes(b"x" * 100)
    dst = tmp_path / "target"
    dst.mkdir()
    rep = core.move_path(str(src), str(dst), confirm=False)
    assert rep["dry_run"] is True
    assert "dry-run" in rep["note"]
    assert src.exists()


def test_move_path_missing_src_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        core.move_path(str(tmp_path / "ghost"), str(tmp_path))


def test_move_path_dst_not_a_dir_raises(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("x")
    with pytest.raises(NotADirectoryError):
        core.move_path(str(src), str(tmp_path / "f.txt"))


def test_move_path_refuses_protected_src():
    with pytest.raises(PermissionError):
        core.move_path(r"C:\Windows", r"D:\somewhere")


def test_move_path_refuses_protected_dst(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("x")
    with pytest.raises(PermissionError):
        core.move_path(str(src), r"C:\Windows")


def test_move_path_same_drive_rename(tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "inner.bin").write_bytes(b"q" * 222)
    dst = tmp_path / "dest"
    dst.mkdir()
    rep = core.move_path(str(src), str(dst), confirm=True)
    assert rep["ok"] is True
    assert not src.exists()
    assert (dst / "data" / "inner.bin").read_bytes() == b"q" * 222
    assert "校验一致" in rep["note"]


def test_move_path_free_space_check_skipped_for_same_drive(monkeypatch, tmp_path):
    """Same-drive move is a rename and needs no free space; a nearly-full
    target volume must not cause a false refusal."""
    src = tmp_path / "data"
    src.mkdir()
    (src / "f.bin").write_bytes(b"x" * 10)
    dst = tmp_path / "dest"
    dst.mkdir()

    Usage = lambda: type("U", (), {"free": 0})()           # pretend disk is full
    monkeypatch.setattr(core.shutil, "disk_usage", lambda _p: Usage())
    rep = core.move_path(str(src), str(dst), confirm=True)
    assert rep["ok"] is True, rep["note"]


def test_move_path_cross_drive_insufficient_space(tmp_path, monkeypatch):
    src = tmp_path / "data"
    src.mkdir()
    (src / "f.bin").write_bytes(b"x" * 1000)
    dst = tmp_path / "dest"
    dst.mkdir()
    monkeypatch.setattr(core.shutil, "disk_usage",
                        lambda _p: type("U", (), {"free": 1})())
    monkeypatch.setattr(core.os.path, "splitdrive", _fake_splitdrive_cross)
    rep = core.move_path(str(src), str(dst), confirm=True)
    assert rep["ok"] is False
    assert "空间不足" in rep["note"]
    assert src.exists()


def test_move_path_dst_name_conflict(tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    dst = tmp_path / "dest"
    (dst / "data").mkdir(parents=True)          # same name already there
    rep = core.move_path(str(src), str(dst), confirm=True)
    assert rep["ok"] is False
    assert "已存在" in rep["note"]
    assert src.exists()


def test_move_path_cross_drive_success(tmp_path, monkeypatch):
    src = tmp_path / "data"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "f.bin").write_bytes(b"z" * 500)
    dst = tmp_path / "dest"
    dst.mkdir()
    monkeypatch.setattr(core.os.path, "splitdrive", _fake_splitdrive_cross)
    rep = core.move_path(str(src), str(dst), confirm=True)
    assert rep["ok"] is True, rep["note"]
    assert not src.exists()
    assert (dst / "data" / "sub" / "f.bin").exists()


def test_move_path_cross_drive_copy_failure_must_keep_source(tmp_path, monkeypatch):
    """REGRESSION / data-loss guard: if the copy step skips files (locked,
    permission...), the source must NOT be deleted."""
    src = tmp_path / "data"
    src.mkdir()
    (src / "precious.bin").write_bytes(b"z" * 500)
    dst = tmp_path / "dest"
    dst.mkdir()
    monkeypatch.setattr(core.os.path, "splitdrive", _fake_splitdrive_cross)
    monkeypatch.setattr(core, "_copy_tree",
                        lambda src_, dst_, rp, label: 1)   # 1 file failed to copy
    rep = core.move_path(str(src), str(dst), confirm=True)
    assert src.exists(), "source was deleted although the copy was incomplete"
    assert (src / "precious.bin").exists()
    assert rep["ok"] is False


# ---------------------------------------------------------------- move_app

def _make_junction(link: str, target: str):
    subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                   check=True, capture_output=True)


def test_move_app_rejects_non_c_drive(tmp_path, monkeypatch):
    real_isdir = os.path.isdir
    monkeypatch.setattr(core.os.path, "isdir",
                        lambda p: True if p.lower().startswith("d:\\app")
                        else real_isdir(p))
    rep = core.move_app(r"D:\app", str(tmp_path), confirm=False)
    assert rep["ok"] is False and "C 盘" in rep["note"]


def test_move_app_rejects_missing_source(tmp_path):
    rep = core.move_app(r"C:\no\such\app", str(tmp_path), confirm=False)
    assert rep["ok"] is False
    assert "不是真实文件夹" in rep["note"]


def test_move_app_rejects_junction_source(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = str(tmp_path / "link")
    try:
        _make_junction(link, str(target))
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("mklink /J not available")
    rep = core.move_app(link, str(tmp_path), confirm=False)
    assert rep["ok"] is False
    assert "已经是联接" in rep["note"] or "不是真实文件夹" in rep["note"]


def test_move_app_rejects_windows_components(monkeypatch, tmp_path):
    real_isdir = os.path.isdir
    monkeypatch.setattr(core.os.path, "isdir",
                        lambda p: True if p.lower().startswith("c:\\windows\\comp")
                        else real_isdir(p))
    rep = core.move_app(r"C:\Windows\comp", str(tmp_path), confirm=False)
    assert rep["ok"] is False and "禁止" in rep["note"]


def test_move_app_rejects_user_profile_dir(tmp_path):
    # tmp_path lives under USERPROFILE -> must be routed to file-move instead
    d = tmp_path / "greenapp"
    d.mkdir()
    rep = core.move_app(str(d), str(tmp_path), confirm=False)
    assert rep["ok"] is False and "文件搬家" in rep["note"]


def test_move_app_profile_prefix_must_respect_separator(monkeypatch, tmp_path):
    """REGRESSION: C:\\Users\\alice2\\app must not be treated as inside
    C:\\Users\\alice (prefix compare needs the path separator)."""
    monkeypatch.setenv("USERPROFILE", r"C:\Users\alice")
    real_isdir = os.path.isdir
    monkeypatch.setattr(core.os.path, "isdir",
                        lambda p: True if p.lower().startswith("c:\\users\\alice2")
                        else real_isdir(p))
    rep = core.move_app(r"C:\Users\alice2\app", str(tmp_path), confirm=False)
    assert "用户目录" not in rep["note"], \
        "sibling profile dir was wrongly classified as inside the profile"
    assert rep["note"] == "dry-run: 未执行"


def test_move_app_missing_dst_root(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    src = tmp_path / "app"
    src.mkdir()
    rep = core.move_app(str(src), str(tmp_path / "no_such_root"), confirm=False)
    assert rep["ok"] is False and "不存在" in rep["note"]


def test_move_app_dst_conflict_and_insufficient_space(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    src = tmp_path / "app"
    src.mkdir()
    dst_root = tmp_path / "dstroot"
    (dst_root / "app").mkdir(parents=True)
    rep = core.move_app(str(src), str(dst_root), confirm=False)
    assert "已存在" in rep["note"]

    (dst_root / "app").rmdir()
    (src / "f.bin").write_bytes(b"x" * 10_000)
    monkeypatch.setattr(core.shutil, "disk_usage",
                        lambda _p: type("U", (), {"free": 1})())
    rep = core.move_app(str(src), str(dst_root), confirm=False)
    assert "空间不足" in rep["note"]


def test_move_app_full_success_flow(tmp_path, monkeypatch):
    """Copy + delete + junction + size verify, with the OS steps faked."""
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    src = tmp_path / "app"
    src.mkdir()
    (src / "f.bin").write_bytes(b"x" * 42)
    dst_root = tmp_path / "dstroot"
    dst_root.mkdir()

    copied = {}

    def fake_copy_tree(s, d, rp, label):
        # emulate a perfect copy
        os.makedirs(d, exist_ok=True)
        shutil_copy_marker = os.path.join(d, "f.bin")
        with open(shutil_copy_marker, "wb") as fh:
            fh.write(b"x" * 42)
        copied["done"] = True
        return 0

    # is_junction must be False at the entry guard and True only after the
    # (faked) mklink has run.
    state = {"linked": False}

    def fake_run(*_a, **_k):
        state["linked"] = True
        return type("R", (), {"returncode": 0, "stderr": b""})()

    monkeypatch.setattr(core, "_copy_tree", fake_copy_tree)
    monkeypatch.setattr(core, "is_junction",
                        lambda p: state["linked"] and p == str(src))
    monkeypatch.setattr(core, "dir_size", lambda p: 42)   # size verify passes
    monkeypatch.setattr(core.subprocess, "run", fake_run)
    rep = core.move_app(str(src), str(dst_root), confirm=True)
    assert copied.get("done")
    assert rep["ok"] is True, rep["note"]
    log = open(core.LOG_FILE, encoding="utf-8").read()
    assert "| APP-MOVE |" in log


def test_move_app_copy_failure_leaves_source_intact(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    src = tmp_path / "app"
    src.mkdir()
    (src / "f.bin").write_bytes(b"x" * 42)
    dst_root = tmp_path / "dstroot"
    dst_root.mkdir()
    monkeypatch.setattr(core, "_copy_tree",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk on fire")))
    rep = core.move_app(str(src), str(dst_root), confirm=True)
    assert rep["ok"] is False
    assert src.exists() and (src / "f.bin").exists()
    assert not os.path.exists(os.path.join(str(dst_root), "app"))  # partial cleaned


def test_move_app_skipped_files_must_not_delete_source(tmp_path, monkeypatch):
    """REGRESSION / data-loss guard: if _copy_tree skips files, the source
    folder must stay untouched instead of being rmtree'd."""
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    src = tmp_path / "app"
    src.mkdir()
    (src / "precious.dll").write_bytes(b"d" * 100)
    dst_root = tmp_path / "dstroot"
    dst_root.mkdir()
    monkeypatch.setattr(core, "_copy_tree", lambda *a, **k: 2)  # 2 files skipped
    rep = core.move_app(str(src), str(dst_root), confirm=True)
    assert src.exists(), "source deleted although copy skipped files"
    assert (src / "precious.dll").exists()
    assert rep["ok"] is False


def test_move_app_junction_failure_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\__nobody__")
    src = tmp_path / "app"
    src.mkdir()
    (src / "f.bin").write_bytes(b"x" * 7)
    dst_root = tmp_path / "dstroot"
    dst_root.mkdir()
    monkeypatch.setattr(core, "is_junction", lambda p: False)
    monkeypatch.setattr(core.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1,
                                                       "stderr": b"access denied"})())
    rep = core.move_app(str(src), str(dst_root), confirm=True)
    assert rep["ok"] is False
    assert src.exists() and (src / "f.bin").exists(), "rollback must restore src"
    assert "还原" in rep["note"]
