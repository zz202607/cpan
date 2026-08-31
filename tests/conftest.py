"""Shared fixtures and safety nets for the Cpan test suite.

Design rules (lessons from auditing other cleaners' test code):
  * No test may touch the real Recycle Bin — the APIs are patched with
    tripwires in an autouse fixture; tests that exercise them must
    explicitly re-patch with a fake.
  * No test may scan or clean real system locations — junk categories
    are always replaced with tmp_path fixtures.
  * The ops log is redirected into the per-test tmp dir.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cpan_core as core  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Redirect the ops log and forbid real Recycle Bin calls."""
    monkeypatch.setattr(core, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(core, "LOG_FILE", str(tmp_path / "logs" / "cpan_ops.log"))

    def _tripwire(*_a, **_k):
        raise AssertionError("test touched the REAL Recycle Bin API — patch it")

    monkeypatch.setattr(core, "empty_recycle_bin", _tripwire)
    monkeypatch.setattr(core, "send_to_recycle", _tripwire)
    yield


@pytest.fixture
def fake_junk(tmp_path):
    """Two on-disk categories: a plain one and an admin-only one."""
    root = tmp_path / "fakecat"
    root.mkdir()
    (root / "a.tmp").write_bytes(b"x" * 1000)
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.log").write_bytes(b"y" * 500)
    adminroot = tmp_path / "adminroot"
    adminroot.mkdir()
    (adminroot / "c.dat").write_bytes(b"z" * 250)
    return [
        {"id": "fake", "name": "假缓存", "needs_admin": False,
         "desc": "测试用假类别", "roots": [str(root)]},
        {"id": "adm", "name": "仅管理员", "needs_admin": True,
         "desc": "需要管理员", "roots": [str(adminroot)]},
    ]


@pytest.fixture
def fake_junk_with_recycle(fake_junk):
    """Adds a recycle-bin special category to the fake set."""
    return fake_junk + [
        {"id": "recycle_bin", "name": "回收站", "needs_admin": False,
         "desc": "清空回收站", "roots": [], "special": "recycle"},
    ]
