"""Protection logic — the single most safety-critical surface of Cpan.

Behavior-level coverage (not just 'the constant exists'): case, separators,
normalization, drive roots, env expansion, and legitimate paths passing.
"""

from __future__ import annotations

import os

import pytest

import cpan_core as core


@pytest.mark.parametrize("path", [
    r"C:\Windows",
    r"C:\WINDOWS\System32",          # case-insensitive
    r"c:\windows\winsxs",
    r"C:/Windows/System32",          # forward slashes
    "C:\\Windows\\",                 # trailing separator
    r"C:\Windows\Temp\..\System32",  # dot segments
    r"C:\Program Files",
    r"C:\program files (x86)\Something",
    # Note: C:\ProgramData\Microsoft\Windows\WER is deliberately NOT here —
    # it is a whitelisted junk category (regenerable crash reports), cleaned
    # through the junk path, not a protected system area.
    r"C:\Users\Default",
    r"C:\$Recycle.Bin",
    r"C:\System Volume Information",
    r"C:\Boot",
    r"C:\PerfLogs",
    r"C:\Boot\BCD",                  # child of protected prefix
])
def test_protected_areas_are_refused(path):
    bad, why = core.is_protected(path)
    assert bad, f"should be protected: {path}"
    assert why


@pytest.mark.parametrize("drive", ["C:\\", "c:\\", "D:\\", "E:\\"])
def test_drive_roots_are_refused(drive):
    bad, why = core.is_protected(drive)
    assert bad and why == "drive root"


def test_traversal_to_drive_root_is_refused():
    bad, why = core.is_protected(r"C:\Windows\..")
    assert bad and why == "drive root"


@pytest.mark.parametrize("path", [
    r"C:\hiberfil.sys",
    r"C:\pagefile.sys",
    r"C:\swapfile.sys",
])
def test_protected_exact_files(path):
    bad, why = core.is_protected(path)
    assert bad and why == "protected system location"


def test_user_profile_root_itself_is_protected():
    profile = os.environ.get("USERPROFILE")
    if not profile:
        pytest.skip("no USERPROFILE")
    bad, why = core.is_protected(profile)
    assert bad and why == "protected system location"


def test_env_var_expansion_in_protection_check(monkeypatch):
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    bad, _ = core.is_protected("%SystemRoot%\\System32")
    assert bad


@pytest.mark.parametrize("path", [
    r"C:\Users\someone\Documents",     # user data: allowed (recycle route)
    r"C:\Users\someone\Downloads\big.zip",
    r"D:\Games\SomeGame",
    r"D:\downloads",
])
def test_legitimate_user_paths_pass(path):
    bad, why = core.is_protected(path)
    assert not bad, f"should NOT be protected: {path} ({why})"


def test_profile_sibling_prefix_is_not_confused():
    # C:\Users\bob must not protect C:\Users\bob2 (prefix must respect sep)
    bad, _ = core.is_protected(r"C:\Users\Default2")
    assert not bad


def test_tmp_path_is_operable(tmp_path):
    bad, _ = core.is_protected(str(tmp_path))
    assert not bad


def test_assert_deletable_raises_with_reason():
    with pytest.raises(PermissionError) as ei:
        core.assert_deletable(r"C:\Windows\System32")
    assert "protected" in str(ei.value)


def test_assert_deletable_passes_for_user_dir(tmp_path):
    core.assert_deletable(str(tmp_path))  # must not raise
