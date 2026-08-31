"""Utilities: expand, fmt_size, oplog, ProgressReporter."""

from __future__ import annotations

import os

import cpan_core as core


# ---------------------------------------------------------------- expand

def test_expand_env_var(monkeypatch):
    monkeypatch.setenv("CPAN_TEST_DIR", r"C:\Some\Dir")
    assert core.expand(r"%CPAN_TEST_DIR%\sub") == r"C:\Some\Dir\sub"


def test_expand_normalizes_separators():
    out = core.expand(r"C:\a\b\..\c")
    assert out == r"C:\a\c"


# ---------------------------------------------------------------- fmt_size

def test_fmt_size_bytes():
    assert core.fmt_size(0) == "0 B"
    assert core.fmt_size(512) == "512 B"
    assert core.fmt_size(1023) == "1023 B"


def test_fmt_size_units():
    assert core.fmt_size(1024) == "1.0 KB"
    assert core.fmt_size(1536) == "1.5 KB"
    assert core.fmt_size(1024 * 1024) == "1.0 MB"
    assert core.fmt_size(5 * 1024**3) == "5.0 GB"
    assert core.fmt_size(3 * 1024**4) == "3.0 TB"


def test_fmt_size_overflow_past_tb_stays_tb():
    assert core.fmt_size(2048 * 1024**4).endswith("TB")


# ---------------------------------------------------------------- oplog

def test_oplog_creates_dir_and_appends():
    core.oplog("TEST", r"C:\x", "OK")
    core.oplog("TEST2", r"C:\y", "FAIL(z)")
    with open(core.LOG_FILE, encoding="utf-8") as fh:
        lines = fh.readlines()
    assert len(lines) == 2
    assert "| TEST |" in lines[0] and "OK" in lines[0]
    assert "| TEST2 |" in lines[1] and "FAIL(z)" in lines[1]
    # format: stamp | action | target | result
    assert len(lines[0].split(" | ")) == 4


def test_oplog_handles_unicode_targets():
    core.oplog("CLEAN", r"C:\用户\临时\文件", "OK")
    content = open(core.LOG_FILE, encoding="utf-8").read()
    assert "用户" in content


# ------------------------------------------------------- ProgressReporter

def test_progress_reporter_fires_on_label_change_and_completion():
    calls = []
    rp = core.ProgressReporter(100, lambda pct, label, d, t: calls.append((pct, label, d, t)))
    rp.add(10, "阶段一")          # label change -> fire
    rp.add(90)                    # reaches total -> fire
    assert calls[0][1] == "阶段一"
    assert calls[-1][0] == 100


def test_progress_reporter_never_exceeds_100_percent():
    seen = []
    rp = core.ProgressReporter(10, lambda pct, *_: seen.append(pct))
    rp.add(500)
    rp.finish()
    assert all(p <= 100 for p in seen)
    assert seen[-1] == 100


def test_progress_reporter_zero_total_does_not_crash():
    rp = core.ProgressReporter(0, lambda *a: None)
    rp.add(10)
    rp.finish()


def test_progress_reporter_swallows_callback_exceptions():
    def bad_cb(*_a):
        raise RuntimeError("ui is gone")
    rp = core.ProgressReporter(100, bad_cb)
    rp.add(50, "x")  # must not raise
    rp.finish()


def test_progress_reporter_none_callback_ok():
    rp = core.ProgressReporter(100, None)
    rp.add(10)
    rp.finish()


# ---------------------------------------------------------------- is_admin

def test_is_admin_returns_bool():
    assert isinstance(core.is_admin(), bool)
