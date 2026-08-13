"""Cpan core engine — safe C-drive cleanup for Windows.

Rules enforced here (see EXPERT.md):
  1. Whitelist-only auto delete (regenerable caches / temp files).
  2. User files always go to the Recycle Bin (SHFileOperation + FOF_ALLOWUNDO).
  3. Scan -> confirm -> execute; sizes shown before anything is removed.
  4. Destructive actions are dry-run unless the caller passes confirm=True.
  5. Every executed action is appended to logs/cpan_ops.log.
"""

from __future__ import annotations

import ctypes
import glob
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime

if os.name != "nt":
    raise SystemExit("Cpan only runs on Windows.")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "cpan_ops.log")

# ---------------------------------------------------------------- utilities

def expand(path: str) -> str:
    return os.path.normpath(os.path.expandvars(path))


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def oplog(action: str, target: str, result: str) -> None:
    """Append one executed action to the ops log (never called in dry-run)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"{stamp} | {action} | {target} | {result}\n")


def _dir_stats(root: str):
    """Return (bytes, file_count) under root; permission errors are skipped."""
    total, count = 0, 0
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda e: None):
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                if os.path.islink(fp):
                    continue
                total += os.path.getsize(fp)
                count += 1
            except OSError:
                continue
    return total, count


class ProgressReporter:
    """Throttled progress callback: cb(percent, label, done_bytes, total_bytes).

    Fires at most once per ~1% of total (plus once per label change), so
    per-file callbacks do not flood the UI queue.
    """

    def __init__(self, total: int, cb):
        self.total = max(1, int(total))
        self.cb = cb
        self.done = 0
        self.step = max(1, self.total // 100)
        self._next = self.step
        self.label = None

    def add(self, n: int, label: str | None = None):
        if label is not None and label != self.label:
            self.label = label
            self._fire()
        self.done += n
        if self.done >= self._next or self.done >= self.total:
            self._next = self.done + self.step
            self._fire()

    def finish(self, label: str = "完成"):
        self.done = self.total
        self.label = label
        self._fire()

    def _fire(self):
        if not self.cb:
            return
        pct = min(100, self.done * 100 // self.total)
        try:
            self.cb(pct, self.label or "", self.done, self.total)
        except Exception:
            pass

# ------------------------------------------------------------- protection

# Never delete / move these. Compared on lowercased, normalized paths.
_PROTECTED_PREFIXES = [
    r"c:\windows",
    r"c:\program files",
    r"c:\program files (x86)",
    r"c:\users\default",
    r"c:\$recycle.bin",
    r"c:\system volume information",
    r"c:\boot",
    r"c:\perflogs",
]
_PROTECTED_EXACT = [
    r"c:\hiberfil.sys", r"c:\pagefile.sys", r"c:\swapfile.sys",
    os.environ.get("USERPROFILE", r"c:\users\public"),
]


def is_protected(path: str) -> tuple[bool, str]:
    """Return (protected?, reason). Whitelisted category roots are exempt."""
    p = os.path.normpath(os.path.abspath(expand(path))).lower()
    if len(p) <= 3:  # drive root like C:\
        return True, "drive root"
    for exact in _PROTECTED_EXACT:
        if p == os.path.normpath(exact).lower():
            return True, "protected system location"
    for prefix in _PROTECTED_PREFIXES:
        if p == prefix or p.startswith(prefix + os.sep):
            # Category roots under ProgramData etc. are handled by junk clean,
            # never by the user-facing custom/move APIs, so no exemption here.
            return True, f"inside protected system area ({prefix})"
    return False, ""


def assert_deletable(path: str) -> None:
    bad, why = is_protected(path)
    if bad:
        raise PermissionError(f"refused: '{path}' is protected ({why})")

# -------------------------------------------------------- recycle bin APIs

class _SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("i64Size", ctypes.c_longlong),
                ("i64NumItems", ctypes.c_longlong)]


def recycle_bin_stats() -> tuple[int, int]:
    """Return (bytes, items) currently in the Recycle Bin (all drives)."""
    info = _SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
    try:
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if hr == 0:
            return info.i64Size, info.i64NumItems
    except Exception:
        pass
    return 0, 0


def empty_recycle_bin() -> tuple[bool, str]:
    SHERB_NOCONFIRMATION, SHERB_NOPROGRESSUI, SHERB_NOSOUND = 0x1, 0x2, 0x4
    try:
        hr = ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
        if hr in (0, 1):  # S_OK, or S_FALSE when already empty
            return True, "ok"
        return False, f"HRESULT {hr}"
    except Exception as exc:
        return False, str(exc)


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR)]

_FO_DELETE = 3
_FOF_ALLOWUNDO = 0x0040      # move to Recycle Bin instead of permanent delete
_FOF_NOCONFIRMATION = 0x0010
_FOF_SILENT = 0x0004
_FOF_NOERRORUI = 0x0400


def send_to_recycle(paths: list[str]) -> tuple[bool, str]:
    """Move files/folders to the Recycle Bin (recoverable)."""
    if not paths:
        return True, "nothing to do"
    multi = "\0".join(os.path.abspath(expand(p)) for p in paths) + "\0\0"
    op = _SHFILEOPSTRUCTW()
    op.wFunc = _FO_DELETE
    op.pFrom = multi
    op.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI
    try:
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if rc == 0 and not op.fAnyOperationsAborted:
            return True, "ok"
        return False, f"SHFileOperation rc={rc} aborted={op.fAnyOperationsAborted}"
    except Exception as exc:
        return False, str(exc)

# ------------------------------------------------------ junk categories

def _localappdata() -> str:
    return os.environ.get("LOCALAPPDATA", "")


def junk_categories() -> list[dict]:
    """Each category: id, name, desc, roots (expanded, may not exist),
    needs_admin. All roots are regenerable data — safe to delete directly."""
    lad = _localappdata()
    return [
        {"id": "user_temp", "name": "用户临时文件", "needs_admin": False,
         "desc": "用户 TEMP 目录中的应用临时文件",
         "roots": [expand("%TEMP%")]},
        {"id": "win_temp", "name": "系统临时文件", "needs_admin": True,
         "desc": "C:\\Windows\\Temp",
         "roots": [r"C:\Windows\Temp"]},
        {"id": "wu_cache", "name": "更新缓存", "needs_admin": True,
         "desc": "Windows Update 下载缓存",
         "roots": [r"C:\Windows\SoftwareDistribution\Download"]},
        {"id": "recycle_bin", "name": "回收站", "needs_admin": False,
         "desc": "清空回收站（所有盘符）",
         "roots": [], "special": "recycle"},
        {"id": "thumbs", "name": "缩略图缓存", "needs_admin": False,
         "desc": "资源管理器缩略图（自动重建）",
         "roots": [os.path.join(lad, r"Microsoft\Windows\Explorer")]},
        {"id": "chrome_cache", "name": "Chrome 缓存", "needs_admin": False,
         "desc": "仅网页缓存（不碰书签/密码/历史记录）",
         "roots": glob.glob(os.path.join(lad, r"Google\Chrome\User Data\*\Cache")) +
                  glob.glob(os.path.join(lad, r"Google\Chrome\User Data\*\Code Cache"))},
        {"id": "edge_cache", "name": "Edge 缓存", "needs_admin": False,
         "desc": "仅网页缓存（不碰书签/密码）",
         "roots": glob.glob(os.path.join(lad, r"Microsoft\Edge\User Data\*\Cache")) +
                  glob.glob(os.path.join(lad, r"Microsoft\Edge\User Data\*\Code Cache"))},
        {"id": "firefox_cache", "name": "Firefox 缓存", "needs_admin": False,
         "desc": "仅网页缓存",
         "roots": glob.glob(os.path.join(lad, r"Mozilla\Firefox\Profiles\*\cache2"))},
        {"id": "d3d_cache", "name": "着色器缓存", "needs_admin": False,
         "desc": "DirectX 着色器缓存（自动重建）",
         "roots": [os.path.join(lad, "D3DSCache")]},
        {"id": "wer", "name": "错误报告", "needs_admin": True,
         "desc": "Windows 错误报告/崩溃转储",
         "roots": [r"C:\ProgramData\Microsoft\Windows\WER"]},
        {"id": "windows_old", "name": "旧系统 Windows.old", "needs_admin": True,
         "desc": "升级前的旧系统（确认不再回滚再删）",
         "roots": [r"C:\Windows.old"]},
    ]


# Thumbnail cache dir holds other files too; only these patterns are deleted.
_ROOT_FILE_FILTERS = {
    "thumbs": ("thumbcache_", "iconcache_"),
}


def scan_junk() -> list[dict]:
    """Scan all junk categories; returns rows with real sizes for display."""
    admin = is_admin()
    rows = []
    for cat in junk_categories():
        row = {"id": cat["id"], "name": cat["name"], "desc": cat["desc"],
               "needs_admin": cat.get("needs_admin", False),
               "size": 0, "files": 0, "skipped": ""}
        if cat.get("special") == "recycle":
            size, items = recycle_bin_stats()
            row["size"], row["files"] = size, items
            rows.append(row)
            continue
        if row["needs_admin"] and not admin:
            row["skipped"] = "需管理员权限 - 以管理员身份运行本程序可清理"
        existing = [r for r in cat["roots"] if os.path.isdir(r)]
        for root in existing:
            size, count = _dir_stats(root)
            row["size"] += size
            row["files"] += count
        rows.append(row)
    return rows


def _clean_root(root: str, cat_id: str, report: dict,
                rp: "ProgressReporter | None" = None, label: str = "") -> None:
    """Delete files under one category root; occupied files are skipped."""
    prefixes = _ROOT_FILE_FILTERS.get(cat_id)
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        for name in filenames:
            if prefixes and not any(name.lower().startswith(p) for p in prefixes):
                continue
            fp = os.path.join(dirpath, name)
            try:
                if os.path.islink(fp):
                    continue
                sz = os.path.getsize(fp)
                os.remove(fp)
                report["bytes"] += sz
                report["deleted"] += 1
                if rp:
                    rp.add(sz, label)
            except OSError:
                report["skipped"] += 1  # in use or no access — normal
    # remove emptied directories bottom-up
    for dirpath, dirnames, filenames in os.walk(root, topdown=False, onerror=lambda e: None):
        if dirpath == root:
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            pass


def clean_junk(cat_ids: list[str], confirm: bool = False,
               progress=None) -> dict:
    """Clean the selected categories. Dry-run unless confirm=True.

    progress(percent, label, done_bytes, total_bytes) is called while
    executing (never during dry-run).
    """
    selected = {c["id"]: c for c in junk_categories() if c["id"] in cat_ids}
    plan = scan_junk()
    admin = is_admin()
    report = {"dry_run": not confirm, "bytes": 0, "deleted": 0,
              "skipped": 0, "details": []}
    total = sum(r["size"] for r in plan
                if r["id"] in selected and not (r["needs_admin"] and not admin))
    rp = ProgressReporter(total, progress)
    for row in plan:
        if row["id"] not in selected:
            continue
        cat = selected[row["id"]]
        if cat.get("special") == "recycle":
            if confirm:
                ok, msg = empty_recycle_bin()
                oplog("CLEAN", "回收站", "OK" if ok else f"FAIL({msg})")
                if ok:
                    report["bytes"] += row["size"]
                    report["deleted"] += row["files"]
                rp.add(row["size"], "清空回收站")
            report["details"].append(f"回收站: {row['desc']}")
            continue
        if row["needs_admin"] and not admin:
            report["details"].append(f"{row['name']}: 跳过（需管理员权限）")
            continue
        for root in [r for r in cat["roots"] if os.path.isdir(r)]:
            if confirm:
                _clean_root(root, cat["id"], report, rp, row["name"])
                oplog("CLEAN", root, "OK")
            report["details"].append(f"{row['name']}: {root}")
    rp.finish("清理完成")
    return report

# ------------------------------------------------------ custom cleanup

def scan_custom(root: str, exts: list[str] | None = None,
                min_mb: float = 0, older_days: int = 0) -> list[dict]:
    """Find files matching ALL given filters under root (recursion included)."""
    assert_deletable(root)
    root = expand(root)
    if not os.path.isdir(root):
        raise FileNotFoundError(root)
    ext_set = {e.lower() if e.startswith(".") else "." + e.lower()
               for e in (exts or [])}
    cutoff = time.time() - older_days * 86400 if older_days > 0 else 0
    hits = []
    for dirpath, _dirs, files in os.walk(root, onerror=lambda e: None):
        for name in files:
            fp = os.path.join(dirpath, name)
            try:
                if os.path.islink(fp):
                    continue
                st = os.stat(fp)
            except OSError:
                continue
            if ext_set and os.path.splitext(name)[1].lower() not in ext_set:
                continue
            if min_mb and st.st_size < min_mb * 1024 * 1024:
                continue
            if cutoff and st.st_mtime > cutoff:
                continue
            hits.append({"path": fp, "size": st.st_size,
                         "mtime": datetime.fromtimestamp(st.st_mtime)
                         .strftime("%Y-%m-%d")})
    hits.sort(key=lambda h: h["size"], reverse=True)
    return hits


def delete_custom(paths: list[str], confirm: bool = False,
                  progress=None) -> dict:
    """Send user files to the Recycle Bin. Dry-run unless confirm=True."""
    report = {"dry_run": not confirm, "requested": len(paths),
              "ok": 0, "failed": [], "bytes": 0}
    allowed = []
    for p in paths:
        try:
            assert_deletable(p)
            allowed.append(p)
        except PermissionError as exc:
            report["failed"].append(f"{p}: {exc}")
    sizes = {}
    for p in allowed:
        try:
            sizes[p] = _dir_stats(p)[0] if os.path.isdir(p) else os.path.getsize(p)
        except OSError:
            sizes[p] = 0
        report["bytes"] += sizes[p]
    rp = ProgressReporter(report["bytes"], progress)
    if confirm and allowed:
        chunk_n = 50  # one SHFileOperation per chunk -> reportable progress
        for i in range(0, len(allowed), chunk_n):
            chunk = allowed[i:i + chunk_n]
            ok, msg = send_to_recycle(chunk)
            for p in chunk:
                oplog("RECYCLE", p, "OK" if ok else f"FAIL({msg})")
            if ok:
                report["ok"] += len(chunk)
            else:
                report["failed"].append(f"{len(chunk)} 项移入回收站失败: {msg}")
            rp.add(sum(sizes[p] for p in chunk), "移入回收站")
    rp.finish("删除完成")
    return report

# ------------------------------------------------------------ move files

def _copy_tree(src: str, dst: str, rp: "ProgressReporter", label: str) -> int:
    """Copy a directory tree with progress reporting; returns skipped count."""
    skipped = 0
    for dirpath, _dirs, filenames in os.walk(src, onerror=lambda e: None):
        rel = os.path.relpath(dirpath, src)
        ddir = dst if rel == "." else os.path.join(dst, rel)
        try:
            os.makedirs(ddir, exist_ok=True)
        except OSError:
            pass
        for name in filenames:
            s = os.path.join(dirpath, name)
            t = os.path.join(ddir, name)
            try:
                shutil.copy2(s, t, follow_symlinks=True)
                rp.add(os.path.getsize(t), f"{label}: {name[:24]}")
            except OSError:
                skipped += 1
    return skipped


def move_path(src: str, dst_dir: str, confirm: bool = False,
              progress=None) -> dict:
    """Move src into dst_dir; verifies size after the move."""
    assert_deletable(src)  # refuse to move system areas
    src = os.path.abspath(expand(src))
    dst_dir = os.path.abspath(expand(dst_dir))
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    if not os.path.isdir(dst_dir):
        raise NotADirectoryError(f"destination is not a folder: {dst_dir}")
    bad, why = is_protected(dst_dir)
    if bad:
        raise PermissionError(f"refused: destination protected ({why})")

    src_size = _dir_stats(src)[0] if os.path.isdir(src) else os.path.getsize(src)
    report = {"dry_run": not confirm, "src": src, "size": src_size,
              "dst": "", "ok": False, "note": ""}

    free = shutil.disk_usage(dst_dir).free
    if free < src_size * 1.05:  # small margin for metadata
        report["note"] = (f"目标盘空间不足"
                          f"（剩余 {fmt_size(free)}，需要 {fmt_size(src_size)}）")
        return report

    final_dst = os.path.join(dst_dir, os.path.basename(src))
    if os.path.exists(final_dst):
        report["note"] = f"目标位置已存在同名: {final_dst}"
        return report
    report["dst"] = final_dst
    if not confirm:
        report["note"] = "dry-run: 未执行"
        return report

    rp = ProgressReporter(src_size, progress)
    same_drive = (os.path.splitdrive(src)[0].lower()
                  == os.path.splitdrive(final_dst)[0].lower())
    try:
        if os.path.isdir(src) and not same_drive:
            # cross-drive: manual copy with progress, then delete source
            os.makedirs(final_dst, exist_ok=True)
            _copy_tree(src, final_dst, rp, "搬移中")
            shutil.rmtree(src, ignore_errors=True)
            if os.path.exists(src):
                report["note"] = ("复制完成，但源目录有被占用的文件没删掉。"
                                  "请关闭相关程序后手动删除残留。")
                oplog("MOVE", f"{src} -> {final_dst}", "WARN(src-leftover)")
                return report
        else:
            shutil.move(src, final_dst)  # same drive = instant rename
            rp.add(src_size, "搬移中")
    except Exception as exc:
        oplog("MOVE", f"{src} -> {final_dst}", f"FAIL({exc})")
        report["note"] = f"搬移失败: {exc}"
        return report
    rp.finish("搬移完成")

    dst_size = (_dir_stats(final_dst)[0] if os.path.isdir(final_dst)
                else os.path.getsize(final_dst))
    if dst_size == src_size:
        report["ok"] = True
        report["note"] = "搬移完成，大小校验一致"
        oplog("MOVE", f"{src} -> {final_dst}", "OK")
    else:
        report["note"] = (f"警告：搬移后大小不一致"
                          f"（源 {src_size} vs 目标 {dst_size}），请手动检查")
        oplog("MOVE", f"{src} -> {final_dst}",
              f"WARN(size {src_size}!={dst_size})")
    return report

# ------------------------------------------------------------- uninstall

_UNINSTALL_KEYS = [
    (0x80000002, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),        # HKLM
    (0x80000002, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (0x80000001, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),        # HKCU
]


def list_installed() -> list[dict]:
    """Enumerate installed programs from the registry (read-only)."""
    import winreg
    seen, items = set(), []
    for hive, sub in _UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(hive, sub) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as app:
                            def _q(field, default=""):
                                try:
                                    return winreg.QueryValueEx(app, field)[0]
                                except OSError:
                                    return default
                            display = _q("DisplayName")
                            if not display:
                                continue
                            if _q("SystemComponent") == 1:
                                continue  # OS component
                            if _q("ParentKeyName"):
                                continue  # update/hotfix entry
                            uninstall = _q("UninstallString")
                            if not uninstall:
                                continue
                            key_norm = display.lower()
                            if key_norm in seen:
                                continue
                            seen.add(key_norm)
                            items.append({
                                "name": display,
                                "publisher": _q("Publisher"),
                                "version": _q("DisplayVersion"),
                                "size_kb": int(_q("EstimatedSize", 0) or 0),
                                "install_date": _q("InstallDate"),
                                "install_location": _q("InstallLocation"),
                                "uninstall": uninstall,
                                "quiet_uninstall": _q("QuietUninstallString"),
                            })
                    except OSError:
                        continue
        except OSError:
            continue
    items.sort(key=lambda x: x["name"].lower())
    return items


def uninstall_program(item: dict, confirm: bool = False) -> dict:
    """Run the official uninstaller (quiet string first). Dry-run unless confirm."""
    cmd = item.get("quiet_uninstall") or item.get("uninstall")
    if not cmd:
        return {"ok": False, "note": "未注册卸载命令"}
    # MSI install-style string: convert /I{code} to /X{code}
    if cmd.lower().startswith("msiexec") and "/i{" in cmd.lower():
        idx = cmd.lower().index("/i{")
        cmd = cmd[:idx] + "/X{" + cmd[idx + 3:]
    report = {"dry_run": not confirm, "name": item["name"], "cmd": cmd,
              "ok": False, "note": ""}
    if not confirm:
        report["note"] = "dry-run: 未启动卸载器"
        return report
    try:
        proc = subprocess.Popen(cmd, shell=True)
        rc = proc.wait()
        report["ok"] = rc in (0, 3010)  # 3010 = success, reboot required
        report["note"] = f"exit code {rc}" + (" (reboot required)" if rc == 3010 else "")
        oplog("UNINSTALL", item["name"], f"rc={rc}")
    except Exception as exc:
        report["note"] = f"failed to launch: {exc}"
        oplog("UNINSTALL", item["name"], f"FAIL({exc})")
    return report

# ------------------------------------------------- app relocation (junction)

def dir_size(path: str) -> int:
    """Total byte size under a folder (errors skipped)."""
    return _dir_stats(path)[0]


def is_junction(path: str) -> bool:
    """True for NTFS junctions (mount points). Note: os.path.islink()
    returns False for junctions on Windows, so the reparse tag is read
    directly via FindFirstFileW."""
    try:
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003

        class _WIN32_FIND_DATAW(ctypes.Structure):
            _fields_ = [("dwFileAttributes", wintypes.DWORD),
                        ("ftCreationTime", wintypes.FILETIME),
                        ("ftLastAccessTime", wintypes.FILETIME),
                        ("ftLastWriteTime", wintypes.FILETIME),
                        ("nFileSizeHigh", wintypes.DWORD),
                        ("nFileSizeLow", wintypes.DWORD),
                        ("dwReserved0", wintypes.DWORD),
                        ("dwReserved1", wintypes.DWORD),
                        ("cFileName", wintypes.WCHAR * 260),
                        ("cAlternateFileName", wintypes.WCHAR * 14)]

        fd = _WIN32_FIND_DATAW()
        h = ctypes.windll.kernel32.FindFirstFileW(path, ctypes.byref(fd))
        if h == -1:
            return False
        ctypes.windll.kernel32.FindClose(h)
        return bool(fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT
                    and fd.dwReserved0 == IO_REPARSE_TAG_MOUNT_POINT)
    except Exception:
        return False


def c_drive_apps() -> list[dict]:
    """Installed programs whose real folder lives on C: (move candidates).

    Program Files locations ARE candidates (that is the whole point);
    only C:\\Windows and the user profile tree are excluded.
    """
    out = []
    up = os.environ.get("USERPROFILE", "").lower()
    for it in list_installed():
        loc = expand(it.get("install_location") or "")
        if not loc or not os.path.isdir(loc) or is_junction(loc):
            continue
        low = os.path.abspath(loc).lower()
        if not low.startswith("c:\\"):
            continue
        if low.startswith("c:\\windows"):
            continue
        if up and (low == up or low.startswith(up + os.sep)):
            continue
        it["install_location"] = os.path.abspath(loc)
        out.append(it)
    out.sort(key=lambda x: x["name"].lower())
    return out


def move_app(src: str, dst_root: str, confirm: bool = False,
             progress=None) -> dict:
    """Move a program folder off C: and leave a directory junction behind.

    All registry entries, shortcuts and services keep pointing at the old
    path, which now transparently resolves to the new location — the app
    keeps working without reinstallation. Junctions need no admin rights.
    """
    src = os.path.abspath(expand(src))
    dst_root = os.path.abspath(expand(dst_root))
    report = {"dry_run": not confirm, "src": src, "dst": "",
              "size": 0, "ok": False, "note": ""}
    low = src.lower()
    if not os.path.isdir(src) or is_junction(src):
        report["note"] = "源不是真实文件夹（或已经是联接）"
        return report
    if not low.startswith("c:\\"):
        report["note"] = "只搬 C 盘上的程序目录"
        return report
    if low.startswith("c:\\windows"):
        report["note"] = "C:\\Windows 内的组件禁止搬动"
        return report
    if low.startswith(os.environ.get("USERPROFILE", "").lower()) :
        report["note"] = "用户目录内的程序请用『文件搬家』，不要走联接"
        return report
    if not os.path.isdir(dst_root):
        report["note"] = f"目标盘文件夹不存在: {dst_root}"
        return report

    final = os.path.join(dst_root, os.path.basename(src))
    report["dst"] = final
    size = dir_size(src)
    report["size"] = size
    if os.path.exists(final):
        report["note"] = f"目标已存在: {final}"
        return report
    if shutil.disk_usage(dst_root).free < size * 1.05:
        report["note"] = "目标盘剩余空间不足（需多留 5% 余量）"
        return report
    if not confirm:
        report["note"] = "dry-run: 未执行"
        return report

    rp = ProgressReporter(size, progress)
    try:
        os.makedirs(final, exist_ok=True)
        skipped = _copy_tree(src, final, rp, "搬移中")
    except Exception as exc:
        shutil.rmtree(final, ignore_errors=True)  # drop partial copy
        report["note"] = f"复制失败（源未动）: {exc}"
        oplog("APP-MOVE", f"{src} -> {final}", f"FAIL({exc})")
        return report
    shutil.rmtree(src, ignore_errors=True)
    if os.path.exists(src):
        report["note"] = ("复制已完成，但源目录有文件被占用没删掉（软件没关干净？）。\n"
                          "请关闭该软件及后台进程后，手动删除源目录残留即可生效。\n"
                          f"源残留: {src}\n完整副本: {final}")
        oplog("APP-MOVE", f"{src} -> {final}", "FAIL(src-locked)")
        return report
    if skipped:
        report["skipped_files"] = skipped
    rp.finish("建立联接")

    mk = subprocess.run(["cmd", "/c", "mklink", "/J", src, final],
                        capture_output=True, text=True)
    if mk.returncode != 0 or not is_junction(src):
        try:  # clear any half-made link before rolling back
            if is_junction(src):
                os.rmdir(src)  # removes the junction itself only
            elif os.path.isdir(src) and not os.listdir(src):
                os.rmdir(src)
        except OSError:
            pass
        try:  # rollback: put the folder back where it was
            shutil.move(final, src)
            report["note"] = f"建联接失败，已自动还原: {mk.stderr.strip()}"
        except Exception as exc:
            report["note"] = (f"!! 联接失败且还原失败: {exc} "
                              f"文件在 {final}，请手动移回 {src}")
        oplog("APP-MOVE", f"{src} -> {final}", "FAIL(junction)")
        return report

    if dir_size(src) == size:  # reads through the junction
        report["ok"] = True
        report["note"] = "搬移成功，原路径联接已生效，软件照常使用"
        oplog("APP-MOVE", f"{src} -> {final}", "OK")
    else:
        report["note"] = "联接已建，但校验大小不一致，请手动检查"
        oplog("APP-MOVE", f"{src} -> {final}", "WARN(size)")
    return report

# ------------------------------------------------------------- big files

def find_big_files(root: str, min_mb: float = 500, top: int = 30) -> list[dict]:
    """List the biggest files under root (>= min_mb). Read-only scan."""
    root = expand(root)
    if not os.path.isdir(root):
        raise FileNotFoundError(root)
    threshold = min_mb * 1024 * 1024
    found = []
    for dirpath, _dirs, files in os.walk(root, onerror=lambda e: None):
        for name in files:
            fp = os.path.join(dirpath, name)
            try:
                if os.path.islink(fp):
                    continue
                sz = os.path.getsize(fp)
            except OSError:
                continue
            if sz >= threshold:
                found.append({"path": fp, "size": sz})
    found.sort(key=lambda h: h["size"], reverse=True)
    return found[:top]
