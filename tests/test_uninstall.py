"""Program uninstall: command derivation, MSI conversion, dry-run."""

from __future__ import annotations

import pytest

import cpan_core as core


def _item(**kw):
    base = {"name": "某软件", "publisher": "", "version": "",
            "size_kb": 0, "install_date": "", "install_location": "",
            "uninstall": "", "quiet_uninstall": ""}
    base.update(kw)
    return base


def test_msi_install_string_converted_to_uninstall():
    it = _item(uninstall=r"MsiExec.exe /I{1234-ABCD}")
    rep = core.uninstall_program(it, confirm=False)
    assert rep["cmd"] == r"MsiExec.exe /X{1234-ABCD}"


def test_msi_conversion_case_insensitive():
    it = _item(uninstall=r"msiexec /i{AAAA}")
    rep = core.uninstall_program(it, confirm=False)
    assert rep["cmd"] == r"msiexec /X{AAAA}"


def test_non_msi_command_untouched():
    it = _item(uninstall=r'"C:\Program Files\App\unins000.exe" /SILENT')
    rep = core.uninstall_program(it, confirm=False)
    assert rep["cmd"] == r'"C:\Program Files\App\unins000.exe" /SILENT'


def test_quiet_string_preferred():
    it = _item(uninstall="loud.exe", quiet_uninstall="quiet.exe /S")
    rep = core.uninstall_program(it, confirm=False)
    assert rep["cmd"] == "quiet.exe /S"


def test_no_command_registered():
    rep = core.uninstall_program(_item(), confirm=True)
    assert rep["ok"] is False
    assert "未注册" in rep["note"]


def test_dry_run_does_not_launch(monkeypatch):
    monkeypatch.setattr(core.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("dry-run must not launch"))
    it = _item(uninstall="whatever.exe")
    rep = core.uninstall_program(it, confirm=False)
    assert rep["dry_run"] is True
    assert "dry-run" in rep["note"]


class _FakeProc:
    def __init__(self, rc):
        self._rc = rc

    def wait(self):
        return self._rc


@pytest.mark.parametrize("rc, ok", [(0, True), (3010, True), (1603, False), (1, False)])
def test_confirm_interprets_exit_codes(monkeypatch, rc, ok):
    monkeypatch.setattr(core.subprocess, "Popen", lambda cmd, **k: _FakeProc(rc))
    it = _item(uninstall="whatever.exe")
    rep = core.uninstall_program(it, confirm=True)
    assert rep["ok"] is ok
    assert str(rc) in rep["note"]
    if rc == 3010:
        assert "reboot" in rep["note"]


def test_confirm_launch_failure_reported(monkeypatch):
    def boom(cmd, **k):
        raise FileNotFoundError("no such exe")
    monkeypatch.setattr(core.subprocess, "Popen", boom)
    rep = core.uninstall_program(_item(uninstall="ghost.exe"), confirm=True)
    assert rep["ok"] is False and "failed to launch" in rep["note"]


def test_list_installed_smoke():
    """Read-only registry enumeration: must not raise and must yield
    well-formed rows (machine-specific content is not asserted)."""
    items = core.list_installed()
    assert isinstance(items, list)
    for it in items[:5]:
        assert {"name", "uninstall", "size_kb"} <= set(it)
        assert it["name"]
    names = [i["name"].lower() for i in items]
    assert names == sorted(names)


def test_c_drive_apps_excludes_userprofile_and_junctions(monkeypatch, tmp_path):
    loc = tmp_path / "somewhere"      # under USERPROFILE -> excluded
    loc.mkdir()
    monkeypatch.setattr(core, "list_installed", lambda: [
        _item(name="InProfile", install_location=str(loc)),
        _item(name="NoLocation", install_location=""),
    ])
    assert core.c_drive_apps() == []
