"""Cpan 命令行 — C盘安全清理。

破坏性操作默认 dry-run（只打印计划），加 --yes 才真正执行。

示例:
    python cpan.py scan
    python cpan.py clean --cats user_temp,chrome_cache --yes
    python cpan.py custom --path D:\\downloads --ext .tmp,.log --days 30
    python cpan.py custom --path D:\\downloads --ext .tmp --delete --yes
    python cpan.py move --src C:\\Users\\me\\Downloads --dst D:\\ --yes
    python cpan.py apps --cdrive                    # 只列装在 C 盘的软件
    python cpan.py appmove --name "某软件" --dst D:\\ --yes   # 联接方式搬出
    python cpan.py uninstall --name "某软件" --yes
    python cpan.py bigfiles --dir C:\\Users\\me --min-mb 300
"""

from __future__ import annotations

import argparse
import sys

# Git Bash (mintty) 终端按 UTF-8 显示
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cpan_core as core


def _hr(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 56 - len(title) * 2))


def _cli_progress(pct: int, label: str, done: int, total: int) -> None:
    """Single-line console progress bar (ASCII, works on any console)."""
    width = 24
    filled = width * pct // 100
    bar = "#" * filled + "-" * (width - filled)
    line = (f"\r  [{bar}] {pct:>3}%  "
            f"{core.fmt_size(done)}/{core.fmt_size(total)}  {label[:30]}")
    sys.stdout.write(line + " " * 4)
    if pct >= 100:
        sys.stdout.write("\n")
    sys.stdout.flush()


def cmd_scan(_args) -> int:
    _hr("垃圾扫描（仅预览，不删除）")
    rows = core.scan_junk()
    total = 0
    print(f"{'类别':<14}{'大小':>12}{'文件数':>10}  说明")
    for r in rows:
        total += r["size"]
        note = r["skipped"] or r["desc"]
        print(f"{r['name']:<14}{core.fmt_size(r['size']):>12}{r['files']:>10}  {note}")
    print(f"\n可回收合计: {core.fmt_size(total)}")
    print("执行: python cpan.py clean --cats <id列表> --yes")
    return 0


def cmd_clean(args) -> int:
    if args.cats in (None, "all"):
        ids = [c["id"] for c in core.junk_categories()]
    else:
        ids = [c.strip() for c in args.cats.split(",") if c.strip()]
    report = core.clean_junk(ids, confirm=args.yes,
                             progress=_cli_progress if args.yes else None)
    mode = "执行" if args.yes else "DRY-RUN（加 --yes 才真正执行）"
    _hr(f"清理计划 [{mode}]")
    for line in report["details"]:
        print("  " + line)
    if args.yes:
        print(f"\n已释放 {core.fmt_size(report['bytes'])} —— "
              f"删除 {report['deleted']} 个文件，"
              f"跳过 {report['skipped']} 个（正在使用中）")
    return 0


def cmd_custom(args) -> int:
    exts = [e.strip() for e in args.ext.split(",")] if args.ext else None
    hits = core.scan_custom(args.path, exts, args.min_mb, args.days)
    _hr(f"规则扫描: {args.path}  （命中 {len(hits)} 个）")
    for h in hits[:50]:
        print(f"{core.fmt_size(h['size']):>12}  {h['mtime']}  {h['path']}")
    if len(hits) > 50:
        print(f"... 另有 {len(hits) - 50} 个未显示")
    total = sum(h["size"] for h in hits)
    print(f"\n合计: {core.fmt_size(total)}")
    if args.delete:
        rep = core.delete_custom([h["path"] for h in hits], confirm=args.yes,
                                 progress=_cli_progress if args.yes else None)
        if args.yes:
            print(f"已移入回收站: {rep['ok']} 项，{core.fmt_size(rep['bytes'])}（可恢复）")
        else:
            print("DRY-RUN: 未删除。加 --yes 移入回收站。")
        for f in rep["failed"]:
            print("  ! " + f)
    else:
        print("加 --delete --yes 可把这些文件移入回收站。")
    return 0


def cmd_move(args) -> int:
    rep = core.move_path(args.src, args.dst, confirm=args.yes,
                         progress=_cli_progress if args.yes else None)
    _hr(f"文件搬家 [{'执行' if args.yes else 'DRY-RUN'}]")
    print(f"  源 : {rep['src']}  ({core.fmt_size(rep['size'])})")
    print(f"  到 : {rep['dst'] or '(未计算)'}")
    print(f"  结果: {rep['note']}")
    return 0 if rep["ok"] or not args.yes else 1


def cmd_apps(args) -> int:
    _hr("已安装程序" + ("（仅 C 盘）" if args.cdrive else ""))
    items = core.c_drive_apps() if args.cdrive else core.list_installed()
    for it in items:
        size = core.fmt_size(it["size_kb"] * 1024) if it["size_kb"] else "  ?"
        loc = it.get("install_location") or ""
        print(f"{size:>12}  {it['name']}  [{it['publisher']}]  {loc}")
    print(f"\n共 {len(items)} 个。" +
          ("搬出 C 盘: python cpan.py appmove --name \"<名称>\" --dst D:\\ --yes"
           if args.cdrive else
           "卸载: python cpan.py uninstall --name \"<名称>\" --yes"))
    return 0


def cmd_appmove(args) -> int:
    items = core.c_drive_apps()
    needle = args.name.lower()
    match = [i for i in items if needle in i["name"].lower()]
    if not match:
        print(f"没有在 C 盘找到匹配 '{args.name}' 的程序。")
        return 1
    if len(match) > 1:
        print("匹配到多个，请写得更具体:")
        for m in match:
            print("  " + m["name"])
        return 1
    it = match[0]
    rep = core.move_app(it["install_location"], args.dst, confirm=args.yes,
                        progress=_cli_progress if args.yes else None)
    _hr(f"软件搬家 [{'执行' if args.yes else 'DRY-RUN'}]")
    print(f"  软件: {it['name']}")
    print(f"  源 : {rep['src']}  ({core.fmt_size(rep['size'])})")
    print(f"  到 : {rep['dst']}")
    print(f"  原理: 原位置保留目录联接(junction)，注册表/快捷方式不用改")
    print(f"  结果: {rep['note']}")
    if args.yes and not rep["ok"]:
        return 1
    return 0


def cmd_uninstall(args) -> int:
    items = core.list_installed()
    needle = args.name.lower()
    match = [i for i in items if needle in i["name"].lower()]
    if not match:
        print(f"没有找到匹配 '{args.name}' 的程序。")
        return 1
    if len(match) > 1:
        print("匹配到多个，请写得更具体:")
        for m in match:
            print("  " + m["name"])
        return 1
    rep = core.uninstall_program(match[0], confirm=args.yes)
    _hr(f"卸载 [{'执行' if args.yes else 'DRY-RUN'}]")
    print(f"  程序: {rep['name']}")
    print(f"  命令: {rep['cmd']}")
    print(f"  结果: {rep['note']}")
    return 0 if rep["ok"] or not args.yes else 1


def cmd_bigfiles(args) -> int:
    root = args.dir or core.expand("%USERPROFILE%")
    found = core.find_big_files(root, args.min_mb, args.top)
    _hr(f"大文件（≥{args.min_mb:.0f} MB）: {root}")
    if not found:
        print("  （没找到）")
    for f in found:
        print(f"{core.fmt_size(f['size']):>12}  {f['path']}")
    print("\n逐个决定: 搬走(cpan.py move) 或 送回收站(cpan.py custom --path <所在目录>)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cpan", description="C盘安全清理工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("scan", help="扫描垃圾类别（预览）").set_defaults(fn=cmd_scan)

    p = sub.add_parser("clean", help="清理选中的垃圾类别")
    p.add_argument("--cats", help="逗号分隔的 id，或 all（默认 all）")
    p.add_argument("--yes", action="store_true", help="真正执行")
    p.set_defaults(fn=cmd_clean)

    p = sub.add_parser("custom", help="按规则清理 -> 回收站")
    p.add_argument("--path", required=True)
    p.add_argument("--ext", help="如 .tmp,.log")
    p.add_argument("--min-mb", type=float, default=0)
    p.add_argument("--days", type=int, default=0, help="只找修改时间早于 N 天的")
    p.add_argument("--delete", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_custom)

    p = sub.add_parser("move", help="移动文件/目录")
    p.add_argument("--src", required=True)
    p.add_argument("--dst", required=True, help="目标文件夹")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_move)

    p = sub.add_parser("apps", help="列出已安装程序")
    p.add_argument("--cdrive", action="store_true", help="只列装在 C 盘的")
    p.set_defaults(fn=cmd_apps)

    p = sub.add_parser("appmove", help="把 C 盘程序搬到其他盘（联接方式，不影响使用）")
    p.add_argument("--name", required=True)
    p.add_argument("--dst", required=True, help="目标盘文件夹，如 D:\\")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_appmove)

    p = sub.add_parser("uninstall", help="按名称卸载程序")
    p.add_argument("--name", required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_uninstall)

    p = sub.add_parser("bigfiles", help="查找大文件")
    p.add_argument("--dir", default=None, help="扫描目录（默认用户目录）")
    p.add_argument("--min-mb", type=float, default=500)
    p.add_argument("--top", type=int, default=30)
    p.set_defaults(fn=cmd_bigfiles)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (PermissionError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
