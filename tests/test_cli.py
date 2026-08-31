"""CLI wiring: cpan.py argument handling and dry-run defaults.

Core behavior is covered elsewhere; here we verify that the command line
maps to the right engine calls and never executes without --yes.
"""

from __future__ import annotations

import pytest

import cpan
import cpan_core as core


def test_cli_scan_prints_rows(monkeypatch, capsys):
    monkeypatch.setattr(core, "scan_junk", lambda: [
        {"id": "user_temp", "name": "用户临时文件", "desc": "d",
         "needs_admin": False, "size": 1536, "files": 3, "skipped": ""},
    ])
    rc = cpan.main(["scan"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "用户临时文件" in out and "1.5 KB" in out


def test_cli_clean_without_yes_is_dry_run(monkeypatch, capsys):
    seen = {}

    def fake_clean(ids, confirm=False, progress=None):
        seen.update(ids=ids, confirm=confirm)
        return {"dry_run": not confirm, "bytes": 0, "deleted": 0,
                "skipped": 0, "details": ["x: y"]}

    monkeypatch.setattr(core, "clean_junk", fake_clean)
    rc = cpan.main(["clean", "--cats", "user_temp,thumbs"])
    assert rc == 0
    assert seen["ids"] == ["user_temp", "thumbs"]
    assert seen["confirm"] is False
    assert "DRY-RUN" in capsys.readouterr().out


def test_cli_clean_all_expands_ids(monkeypatch):
    seen = {}

    def fake_clean(ids, confirm=False, progress=None):
        seen["ids"] = ids
        return {"dry_run": True, "bytes": 0, "deleted": 0, "skipped": 0,
                "details": []}

    monkeypatch.setattr(core, "junk_categories", lambda: [
        {"id": "a"}, {"id": "b"}])
    monkeypatch.setattr(core, "clean_junk", fake_clean)
    cpan.main(["clean"])                       # --cats omitted -> all
    assert seen["ids"] == ["a", "b"]


def test_cli_move_dry_run_rc0(tmp_path, capsys):
    src = tmp_path / "f.bin"
    src.write_bytes(b"x")
    rc = cpan.main(["move", "--src", str(src), "--dst", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0 and "DRY-RUN" in out
    assert src.exists()


def test_cli_move_protected_src_rc1(tmp_path, capsys):
    rc = cpan.main(["move", "--src", r"C:\Windows", "--dst", str(tmp_path)])
    assert rc == 1
    assert "错误" in capsys.readouterr().err


def test_cli_bigfiles_finds_and_sorts(tmp_path, capsys):
    big = tmp_path / "big.iso"
    with open(big, "wb") as fh:
        fh.seek(2 * 1024 * 1024 - 1)
        fh.write(b"\0")
    (tmp_path / "small.txt").write_text("x")
    rc = cpan.main(["bigfiles", "--dir", str(tmp_path), "--min-mb", "1"])
    out = capsys.readouterr().out
    assert rc == 0 and "big.iso" in out and "small.txt" not in out


def test_cli_bigfiles_missing_dir_rc1(capsys):
    rc = cpan.main(["bigfiles", "--dir", r"Q:\no\such"])
    assert rc == 1


def test_cli_custom_scan_only(tmp_path, capsys):
    (tmp_path / "a.tmp").write_bytes(b"x" * 10)
    (tmp_path / "b.log").write_bytes(b"y" * 10)
    rc = cpan.main(["custom", "--path", str(tmp_path), "--ext", ".tmp"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "a.tmp" in out and "b.log" not in out


def test_cli_custom_delete_without_yes_keeps_files(monkeypatch, tmp_path, capsys):
    (tmp_path / "a.tmp").write_bytes(b"x")
    monkeypatch.setattr(core, "send_to_recycle",
                        lambda paths: pytest.fail("dry-run must not recycle"))
    rc = cpan.main(["custom", "--path", str(tmp_path), "--ext", ".tmp",
                    "--delete"])
    out = capsys.readouterr().out
    assert rc == 0 and "DRY-RUN" in out
    assert (tmp_path / "a.tmp").exists()


def test_cli_appmove_no_match_rc1(monkeypatch, capsys):
    monkeypatch.setattr(core, "c_drive_apps", lambda: [])
    rc = cpan.main(["appmove", "--name", "不存在的软件", "--dst", "D:\\"])
    assert rc == 1
    assert "没有在 C 盘找到" in capsys.readouterr().out


def test_cli_uninstall_no_match_rc1(monkeypatch, capsys):
    monkeypatch.setattr(core, "list_installed", lambda: [])
    rc = cpan.main(["uninstall", "--name", "ghost"])
    assert rc == 1


def test_cli_uninstall_dry_run_does_not_launch(monkeypatch, capsys):
    item = {"name": "某软件", "publisher": "", "version": "", "size_kb": 0,
            "install_date": "", "install_location": "",
            "uninstall": "whatever.exe", "quiet_uninstall": ""}
    monkeypatch.setattr(core, "list_installed", lambda: [item])
    monkeypatch.setattr(core.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("dry-run must not launch"))
    rc = cpan.main(["uninstall", "--name", "某软件"])
    out = capsys.readouterr().out
    assert rc == 0 and "DRY-RUN" in out


def test_cli_apps_listing(monkeypatch, capsys):
    monkeypatch.setattr(core, "list_installed", lambda: [
        {"name": "AppA", "publisher": "Pub", "version": "1.0", "size_kb": 2048,
         "install_date": "", "install_location": r"C:\AppA",
         "uninstall": "x", "quiet_uninstall": ""}])
    rc = cpan.main(["apps"])
    out = capsys.readouterr().out
    assert rc == 0 and "AppA" in out
