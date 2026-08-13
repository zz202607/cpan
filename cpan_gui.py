"""Cpan 图形界面 — 中文、美化版（tkinter，纯标准库）。

六个标签页: 垃圾清理 / 软件搬家 / 文件搬家 / 自定义清理 / 软件卸载 / 大文件。
所有破坏性操作先确认再执行；用户文件走回收站；操作写入 logs/cpan_ops.log。
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import cpan_core as core

CHECK, EMPTY = "☑", "☐"

# ------------------------------------------------------------- theme
BG       = "#F2F5F9"   # page background
CARD     = "#FFFFFF"
PRIMARY  = "#2F6FED"
PRIMARYD = "#1F56C8"
DARK     = "#16233F"   # banner
TEXT     = "#1F2937"
MUTED    = "#6B7280"
DANGER   = "#D64550"
WARN     = "#B7791F"
OKGREEN  = "#1F9D61"
FONT     = "Microsoft YaHei UI"
MONO     = "Consolas"


class CpanApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.junk_rows: list[dict] = []
        self.cu_hits: list[dict] = []
        self.big_hits: list[dict] = []
        self.apps: list[dict] = []
        self.admin = core.is_admin()
        self.title("Cpan — C盘安全清理")
        self.geometry("980x700")
        self.minsize(860, 600)
        self.configure(bg=BG)
        self._setup_style()
        self._build_banner()
        self._build_tabs()
        self._build_progressbar()
        self._build_logcard()
        self.log("就绪。建议先从「垃圾清理」开始：扫描 → 勾选 → 确认清理。")
        if not self.admin:
            self.log("提示：以管理员身份运行本程序，可额外清理系统临时文件、"
                     "更新缓存、Windows.old 和错误报告。")

    # ------------------------------------------------------------- style
    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        # notebook
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                    padding=(16, 9), font=(FONT, 10, "bold"))
        s.map("TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", PRIMARY)],
              expand=[("selected", (0, 0, 0, 2))])
        # treeview
        s.configure("Treeview", background=CARD, fieldbackground=CARD,
                    foreground=TEXT, rowheight=30, borderwidth=0,
                    font=(FONT, 10))
        s.configure("Treeview.Heading", background="#E8EDF5",
                    foreground="#41506B", font=(FONT, 9, "bold"),
                    borderwidth=0, padding=4)
        s.map("Treeview",
              background=[("selected", "#DCE8FD")],
              foreground=[("selected", "#17376E")])
        # buttons
        s.configure("Accent.TButton", background=PRIMARY, foreground="white",
                    font=(FONT, 10, "bold"), padding=(16, 8), borderwidth=0,
                    focusthickness=0)
        s.map("Accent.TButton",
              background=[("active", PRIMARYD), ("disabled", "#A9BBDD")])
        s.configure("Soft.TButton", background="#E4EAF3", foreground="#33415E",
                    font=(FONT, 10), padding=(14, 8), borderwidth=0)
        s.map("Soft.TButton", background=[("active", "#D3DCEA")])
        s.configure("Danger.TButton", background=DANGER, foreground="white",
                    font=(FONT, 10, "bold"), padding=(16, 8), borderwidth=0)
        s.map("Danger.TButton", background=[("active", "#B93641")])
        # frames / labels
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED,
                    font=(FONT, 9))
        s.configure("Card.TLabel", background=CARD, foreground=TEXT)
        s.configure("CardMuted.TLabel", background=CARD, foreground=MUTED,
                    font=(FONT, 9))
        s.configure("Card.TLabelframe", background=CARD, foreground=TEXT,
                    bordercolor=CARD)
        s.configure("Card.TLabelframe.Label", background=BG,
                    foreground=PRIMARY, font=(FONT, 9, "bold"))
        s.configure("TEntry", padding=5, fieldbackground="white")
        s.configure("Cbar.Horizontal.TProgressbar", background=PRIMARY,
                    troughcolor="#2B3A5E", borderwidth=0, thickness=12)
        s.configure("UI.Horizontal.TProgressbar", background=OKGREEN,
                    troughcolor="#E1E7F0", borderwidth=0, thickness=10)

    # ------------------------------------------------------------ banner
    def _build_banner(self):
        banner = tk.Frame(self, bg=DARK)
        banner.pack(fill="x")
        left = tk.Frame(banner, bg=DARK)
        left.pack(side="left", padx=18, pady=12)
        tk.Label(left, text="C盘清理 · Cpan", bg=DARK, fg="white",
                 font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(left, text="白名单安全清理 · 回收站兜底 · 联接搬家 · 操作留痕",
                 bg=DARK, fg="#93A5C8", font=(FONT, 9)).pack(anchor="w", pady=(2, 0))
        right = tk.Frame(banner, bg=DARK)
        right.pack(side="right", padx=18, pady=12)
        try:
            du = shutil.disk_usage("C:\\")
            used = du.total - du.free
            pct = used / du.total * 100
        except OSError:
            used, pct = 0, 0
        tk.Label(right, text=f"C盘  已用 {core.fmt_size(used)} / "
                             f"共 {core.fmt_size(du.total)}   "
                             f"剩余 {core.fmt_size(du.free)}",
                 bg=DARK, fg="white", font=(FONT, 10)).pack(anchor="e")
        bar_row = tk.Frame(right, bg=DARK)
        bar_row.pack(anchor="e", pady=(6, 0))
        self.cbar = ttk.Progressbar(bar_row, length=260, maximum=100,
                                    value=pct,
                                    style="Cbar.Horizontal.TProgressbar")
        self.cbar.pack(side="left")
        color = "#FF8A8A" if pct > 90 else ("#FFD28A" if pct > 75 else "#9FE3BC")
        tk.Label(bar_row, text=f" {pct:.0f}%", bg=DARK, fg=color,
                 font=(FONT, 10, "bold")).pack(side="left", padx=(8, 0))
        mode = "管理员模式" if self.admin else "普通用户模式（部分功能受限）"
        tk.Label(right, text=mode, bg=DARK, fg="#7E90B5",
                 font=(FONT, 8)).pack(anchor="e", pady=(4, 0))

    # -------------------------------------------------------------- tabs
    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        self.tab_junk = ttk.Frame(nb)
        self.tab_appmove = ttk.Frame(nb)
        self.tab_move = ttk.Frame(nb)
        self.tab_custom = ttk.Frame(nb)
        self.tab_uninstall = ttk.Frame(nb)
        self.tab_big = ttk.Frame(nb)
        nb.add(self.tab_junk, text="  🗑 垃圾清理  ")
        nb.add(self.tab_appmove, text="  📦 软件搬家  ")
        nb.add(self.tab_move, text="  📂 文件搬家  ")
        nb.add(self.tab_custom, text="  🎯 自定义清理  ")
        nb.add(self.tab_uninstall, text="  🧩 软件卸载  ")
        nb.add(self.tab_big, text="  🔍 大文件  ")
        self._build_junk()
        self._build_appmove()
        self._build_move()
        self._build_custom()
        self._build_uninstall()
        self._build_big()

    def _tree(self, parent, cols, height=13):
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        tr = ttk.Treeview(wrap, columns=cols, show="headings", height=height)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tr.yview)
        tr.configure(yscrollcommand=sb.set)
        tr.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tr.tag_configure("odd", background="#F7FAFD")
        return tr

    def _toolbar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=10, pady=(10, 2))
        return bar

    # --------------------------------------------------------- 垃圾清理
    def _build_junk(self):
        bar = self._toolbar(self.tab_junk)
        ttk.Button(bar, text="🔍 扫描垃圾", style="Accent.TButton",
                   command=self.junk_scan).pack(side="left")
        ttk.Button(bar, text="🧹 清理选中", style="Danger.TButton",
                   command=self.junk_clean).pack(side="left", padx=8)
        ttk.Label(bar, text="点击行可切换 ☑ / ☐；删除的都是可再生的临时/缓存文件",
                  style="Muted.TLabel").pack(side="right")
        self.junk_tree = self._tree(self.tab_junk,
                                    ("sel", "name", "size", "files", "note"))
        for col, w, txt, anc in (("sel", 46, "", "center"),
                                 ("name", 170, "类别", "w"),
                                 ("size", 110, "大小", "e"),
                                 ("files", 80, "文件数", "e"),
                                 ("note", 480, "说明", "w")):
            self.junk_tree.column(col, width=w, anchor=anc)
            self.junk_tree.heading(col, text=txt)
        self.junk_tree.bind("<Button-1>", self._junk_toggle)

    def _junk_toggle(self, event):
        iid = self.junk_tree.identify_row(event.y)
        if not iid:
            return
        row = self.junk_rows[int(iid)]
        if row["skipped"]:
            return
        row["on"] = not row["on"]
        self.junk_tree.set(iid, "sel", CHECK if row["on"] else EMPTY)

    def junk_scan(self):
        self._run(core.scan_junk, self._junk_scanned)

    def _junk_scanned(self, rows):
        self.junk_rows = []
        self.junk_tree.delete(*self.junk_tree.get_children())
        total = 0
        for i, r in enumerate(rows):
            r["on"] = not r["skipped"]
            total += r["size"]
            self.junk_rows.append(r)
            self.junk_tree.insert("", "end", iid=str(i),
                                  tags=("odd",) if i % 2 else (),
                                  values=(CHECK if r["on"] else EMPTY,
                                          r["name"], core.fmt_size(r["size"]),
                                          r["files"], r["skipped"] or r["desc"]))
        self.log(f"扫描完成：共可回收 {core.fmt_size(total)}。")

    def junk_clean(self):
        chosen = [r for r in self.junk_rows if r.get("on")]
        if not chosen:
            messagebox.showinfo("Cpan", "请先扫描，再勾选要清理的类别。")
            return
        total = sum(r["size"] for r in chosen)
        if not messagebox.askyesno(
                "确认清理",
                f"将永久删除 {len(chosen)} 类垃圾（{core.fmt_size(total)}）。\n\n"
                f"这些都是可再生的临时/缓存文件，删除不影响任何软件使用。\n继续吗？"):
            return
        ids = [r["id"] for r in chosen]
        pcb = self._pcb()
        self._run(lambda: core.clean_junk(ids, confirm=True, progress=pcb),
                  self._junk_cleaned)

    def _junk_cleaned(self, rep):
        self.log(f"清理完成：释放 {core.fmt_size(rep['bytes'])}，"
                 f"删除 {rep['deleted']} 个文件，"
                 f"跳过 {rep['skipped']} 个（正在使用，属正常）。")
        self.junk_scan()

    # --------------------------------------------------------- 软件搬家
    def _build_appmove(self):
        bar = self._toolbar(self.tab_appmove)
        ttk.Button(bar, text="🔄 刷新列表", style="Soft.TButton",
                   command=self.appmove_refresh).pack(side="left")
        ttk.Button(bar, text="📦 搬出选中软件", style="Accent.TButton",
                   command=self.appmove_do).pack(side="left", padx=8)
        ttk.Button(bar, text="📂 打开安装位置", style="Soft.TButton",
                   command=self.appmove_open).pack(side="left")
        ttk.Label(bar, text="原位置保留目录联接，注册表/快捷方式不用改，软件照常使用",
                  style="Muted.TLabel").pack(side="right")
        self.am_tree = self._tree(self.tab_appmove,
                                  ("name", "loc", "size", "adv"))
        for col, w, txt, anc in (("name", 300, "软件名称", "w"),
                                 ("loc", 380, "安装位置（C盘）", "w"),
                                 ("size", 100, "占用", "e"),
                                 ("adv", 150, "建议", "w")):
            self.am_tree.column(col, width=w, anchor=anc)
            self.am_tree.heading(col, text=txt)

    def appmove_refresh(self):
        self._run(core.c_drive_apps, self._appmove_loaded)

    def _appmove_loaded(self, items):
        self.apps = items
        self.am_tree.delete(*self.am_tree.get_children())
        for i, it in enumerate(items):
            self.am_tree.insert("", "end", iid=str(i),
                                tags=("odd",) if i % 2 else (),
                                values=(it["name"], it["install_location"],
                                        "计算中…", ""))
        self.log(f"装在 C 盘的软件：{len(items)} 个，正在统计占用大小…")
        self._run(lambda: self._calc_app_sizes(items), self._appmove_sized)

    def _calc_app_sizes(self, items):
        result = []
        for i, it in enumerate(items):
            sz = core.dir_size(it["install_location"])
            result.append((i, sz))
            self.q.put(("ui", lambda i=i, s=sz: self._set_app_size(i, s)))
        return result

    def _set_app_size(self, iid, size):
        if not self.am_tree.exists(str(iid)):
            return
        adv = ("体积较小，收益不大" if size < 100 * 1024 * 1024
               else "★ 建议搬出" if size > 500 * 1024 * 1024
               else "可以搬出")
        self.am_tree.set(str(iid), "size", core.fmt_size(size))
        self.am_tree.set(str(iid), "adv", adv)

    def _appmove_sized(self, result):
        total = sum(s for _, s in result)
        self.log(f"大小统计完成：合计 {core.fmt_size(total)} 可搬出 C 盘。")

    def appmove_open(self):
        sel = self.am_tree.selection()
        if not sel:
            messagebox.showinfo("Cpan", "先选中一个软件。")
            return
        os.startfile(self.apps[int(sel[0])]["install_location"])

    def appmove_do(self):
        sel = self.am_tree.selection()
        if len(sel) != 1:
            messagebox.showinfo("Cpan", "请选中一个软件再搬。")
            return
        it = self.apps[int(sel[0])]
        if not messagebox.askokcancel(
                "搬之前",
                f"即将搬出：{it['name']}\n\n"
                f"① 请先关闭该软件（包括托盘图标）。\n"
                f"② 搬到目标盘后，原位置保留目录联接，软件照常使用。\n"
                f"③ 极少数软件（带驱动/自校验）可能不适配，如遇异常可联系客服还原。\n\n"
                f"确认该软件已经关闭？"):
            return
        dst = filedialog.askdirectory(title="搬到哪个盘的哪个文件夹？",
                                      initialdir="D:\\")
        if not dst:
            return
        src = it["install_location"]
        if not messagebox.askyesno(
                "最后确认",
                f"{src}\n  ↓ 搬到\n{dst}\\{os.path.basename(src)}\n\n"
                f"原位置自动建立联接，开始吗？"):
            return
        pcb = self._pcb()
        self._run(lambda: core.move_app(src, dst, confirm=True, progress=pcb),
                  self._appmove_done)

    def _appmove_done(self, rep):
        if rep["ok"]:
            self.log(f"软件搬家成功：{rep['src']} → {rep['dst']}"
                     f"（{core.fmt_size(rep['size'])}）")
            messagebox.showinfo("Cpan", f"搬移成功！\n\n{rep['note']}")
        else:
            self.log(f"软件搬家未完成：{rep['note']}")
            messagebox.showwarning("Cpan", rep["note"])
        self.appmove_refresh()

    # --------------------------------------------------------- 文件搬家
    def _build_move(self):
        card = ttk.LabelFrame(self.tab_move, text="把文件/文件夹搬到别的的位置（如 C盘 → D盘）",
                              style="Card.TLabelframe")
        card.pack(fill="x", padx=10, pady=10)
        ttk.Label(card, text="源：", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=6, pady=5)
        self.mv_src = ttk.Entry(card, width=58)
        self.mv_src.grid(row=0, column=1, sticky="we", padx=4, pady=5)
        ttk.Button(card, text="选文件夹", style="Soft.TButton",
                   command=lambda: self._pick_dir(self.mv_src)).grid(row=0, column=2, padx=3)
        ttk.Button(card, text="选文件", style="Soft.TButton",
                   command=lambda: self._pick_file(self.mv_src)).grid(row=0, column=3, padx=3)
        ttk.Label(card, text="目标文件夹：", style="Card.TLabel").grid(row=1, column=0, sticky="e", padx=6, pady=5)
        self.mv_dst = ttk.Entry(card, width=58)
        self.mv_dst.grid(row=1, column=1, sticky="we", padx=4, pady=5)
        self.mv_dst.insert(0, "D:\\")
        ttk.Button(card, text="选文件夹", style="Soft.TButton",
                   command=lambda: self._pick_dir(self.mv_dst)).grid(row=1, column=2, padx=3)
        ttk.Button(card, text="🚀 开始搬移", style="Accent.TButton",
                   command=self.move_now).grid(row=2, column=1, pady=(6, 8), sticky="w")
        card.columnconfigure(1, weight=1)
        tip = ttk.Label(self.tab_move, style="Muted.TLabel", justify="left", text=(
            "说明：跨盘搬移 = 复制 + 删除，完成后自动校验大小；系统目录禁止搬移。\n"
            "微信 / QQ 的文件目录搬走后，请到软件自身的 设置 → 文件管理 里指向新位置。"))
        tip.pack(anchor="w", padx=14, pady=4)

    def move_now(self):
        src, dst = self.mv_src.get().strip(), self.mv_dst.get().strip()
        if not src or not dst:
            messagebox.showinfo("Cpan", "请先填写源和目标文件夹。")
            return
        if not messagebox.askyesno("确认搬移", f"把\n{src}\n搬到\n{dst}\n\n开始吗？"):
            return
        pcb = self._pcb()
        self._run(lambda: core.move_path(src, dst, confirm=True, progress=pcb),
                  self._moved)

    def _moved(self, rep):
        if rep["ok"]:
            self.log(f"文件搬家成功：{rep['src']} → {rep['dst']}（已校验）")
            messagebox.showinfo("Cpan", f"搬移完成并已校验：\n{rep['dst']}")
        else:
            self.log(f"文件搬家未完成：{rep['note']}")
            messagebox.showwarning("Cpan", rep["note"])

    # -------------------------------------------------------- 自定义清理
    def _build_custom(self):
        card = ttk.LabelFrame(self.tab_custom, text="按规则找出不要的文件（移入回收站，可恢复）",
                              style="Card.TLabelframe")
        card.pack(fill="x", padx=10, pady=10)
        ttk.Label(card, text="目录：", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self.cu_path = ttk.Entry(card, width=52)
        self.cu_path.grid(row=0, column=1, sticky="we", padx=4, pady=4)
        self.cu_path.insert(0, core.expand(r"%USERPROFILE%\Downloads"))
        ttk.Button(card, text="浏览", style="Soft.TButton",
                   command=lambda: self._pick_dir(self.cu_path)).grid(row=0, column=2, padx=3)
        ttk.Label(card, text="扩展名：", style="Card.TLabel").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        self.cu_ext = ttk.Entry(card, width=24)
        self.cu_ext.grid(row=1, column=1, sticky="w", padx=4, pady=4)
        self.cu_ext.insert(0, ".tmp, .log, .bak")
        ttk.Label(card, text="最小体积(MB)：", style="Card.TLabel").grid(row=2, column=0, sticky="e", padx=6, pady=4)
        self.cu_min = ttk.Entry(card, width=8)
        self.cu_min.grid(row=2, column=1, sticky="w", padx=4, pady=4)
        self.cu_min.insert(0, "0")
        ttk.Label(card, text="超过天数：", style="Card.TLabel").grid(row=3, column=0, sticky="e", padx=6, pady=4)
        self.cu_days = ttk.Entry(card, width=8)
        self.cu_days.grid(row=3, column=1, sticky="w", padx=4, pady=4)
        self.cu_days.insert(0, "0")
        ttk.Button(card, text="🔍 扫描", style="Accent.TButton",
                   command=self.custom_scan).grid(row=1, column=2, rowspan=3, padx=6, pady=4)
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text="条件可组合，只命中同时满足所有条件的文件；留空表示不限。",
                  style="CardMuted.TLabel").grid(row=4, column=1, sticky="w", padx=4, pady=(0, 6))
        bar = ttk.Frame(self.tab_custom)
        bar.pack(fill="x", padx=10)
        ttk.Button(bar, text="♻ 选中项移入回收站", style="Danger.TButton",
                   command=self.custom_delete).pack(side="left")
        ttk.Label(bar, text="不选中 = 处理全部列出的文件",
                  style="Muted.TLabel").pack(side="left", padx=8)
        self.cu_tree = self._tree(self.tab_custom, ("path", "size", "mtime"))
        self.cu_tree.column("path", width=600, anchor="w")
        self.cu_tree.column("size", width=110, anchor="e")
        self.cu_tree.column("mtime", width=110, anchor="center")
        self.cu_tree.heading("path", text="文件")
        self.cu_tree.heading("size", text="大小")
        self.cu_tree.heading("mtime", text="修改时间")

    def custom_scan(self):
        exts = [e.strip() for e in self.cu_ext.get().split(",") if e.strip()]
        try:
            min_mb = float(self.cu_min.get() or 0)
            days = int(self.cu_days.get() or 0)
            path = self.cu_path.get().strip()
        except ValueError:
            messagebox.showerror("Cpan", "最小体积 / 天数必须是数字。")
            return
        self._run(lambda: core.scan_custom(path, exts, min_mb, days),
                  self._custom_scanned)

    def _custom_scanned(self, hits):
        self.cu_hits = hits
        self.cu_tree.delete(*self.cu_tree.get_children())
        for i, h in enumerate(hits):
            self.cu_tree.insert("", "end", iid=str(i),
                                tags=("odd",) if i % 2 else (),
                                values=(h["path"], core.fmt_size(h["size"]),
                                        h["mtime"]))
        total = sum(h["size"] for h in hits)
        self.log(f"规则扫描：命中 {len(hits)} 个文件，合计 {core.fmt_size(total)}。")

    def custom_delete(self):
        sel = self.cu_tree.selection()
        hits = ([self.cu_hits[int(i)] for i in sel] if sel else self.cu_hits)
        if not hits:
            messagebox.showinfo("Cpan", "请先扫描。")
            return
        total = sum(h["size"] for h in hits)
        if not messagebox.askyesno(
                "确认删除",
                f"把 {len(hits)} 个文件（{core.fmt_size(total)}）移入回收站？\n"
                f"之后随时可以从回收站恢复。"):
            return
        paths = [h["path"] for h in hits]
        pcb = self._pcb()
        self._run(lambda: core.delete_custom(paths, confirm=True, progress=pcb),
                  self._custom_deleted)

    def _custom_deleted(self, rep):
        self.log(f"已移入回收站：{rep['ok']} 项，{core.fmt_size(rep['bytes'])}。")
        for f in rep["failed"]:
            self.log("  ！ " + f)
        self.custom_scan()

    # --------------------------------------------------------- 软件卸载
    def _build_uninstall(self):
        bar = self._toolbar(self.tab_uninstall)
        ttk.Button(bar, text="🔄 刷新列表", style="Soft.TButton",
                   command=self.apps_refresh).pack(side="left")
        ttk.Button(bar, text="🧩 卸载选中", style="Danger.TButton",
                   command=self.app_uninstall).pack(side="left", padx=8)
        ttk.Label(bar, text="调用软件自带的官方卸载器，不碰注册表",
                  style="Muted.TLabel").pack(side="right")
        self.app_tree = self._tree(self.tab_uninstall,
                                   ("name", "publisher", "size", "date"))
        for col, w, txt, anc in (("name", 360, "软件名称", "w"),
                                 ("publisher", 240, "发布者", "w"),
                                 ("size", 100, "大小", "e"),
                                 ("date", 110, "安装日期", "center")):
            self.app_tree.column(col, width=w, anchor=anc)
            self.app_tree.heading(col, text=txt)

    def apps_refresh(self):
        self._run(core.list_installed, self._apps_loaded)

    def _apps_loaded(self, items):
        self.apps_all = items
        self.app_tree.delete(*self.app_tree.get_children())
        for i, it in enumerate(items):
            size = core.fmt_size(it["size_kb"] * 1024) if it["size_kb"] else "?"
            d = it["install_date"]
            if len(d) == 8:
                d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            self.app_tree.insert("", "end", iid=str(i),
                                 tags=("odd",) if i % 2 else (),
                                 values=(it["name"], it["publisher"], size, d))
        self.log(f"已安装软件：{len(items)} 个。")

    def app_uninstall(self):
        sel = self.app_tree.selection()
        if not sel:
            messagebox.showinfo("Cpan", "请先选中要卸载的软件。")
            return
        item = self.apps_all[int(sel[0])]
        if not messagebox.askyesno(
                "确认卸载",
                f"卸载「{item['name']}」？\n将启动它的官方卸载器（可能弹出卸载界面）。"):
            return
        self._run(lambda: core.uninstall_program(item, confirm=True),
                  self._uninstalled)

    def _uninstalled(self, rep):
        self.log(f"卸载「{rep['name']}」：{rep['note']}")
        self.apps_refresh()

    # ---------------------------------------------------------- 大文件
    def _build_big(self):
        card = ttk.LabelFrame(self.tab_big, text="找出占地方最大的文件",
                              style="Card.TLabelframe")
        card.pack(fill="x", padx=10, pady=10)
        ttk.Label(card, text="目录：", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=6, pady=5)
        self.bf_dir = ttk.Entry(card, width=50)
        self.bf_dir.grid(row=0, column=1, sticky="we", padx=4, pady=5)
        self.bf_dir.insert(0, core.expand("%USERPROFILE%"))
        ttk.Button(card, text="浏览", style="Soft.TButton",
                   command=lambda: self._pick_dir(self.bf_dir)).grid(row=0, column=2, padx=3)
        ttk.Label(card, text="最小体积(MB)：", style="Card.TLabel").grid(row=0, column=3, sticky="e", padx=6)
        self.bf_min = ttk.Entry(card, width=7)
        self.bf_min.grid(row=0, column=4, padx=4)
        self.bf_min.insert(0, "500")
        ttk.Button(card, text="🔍 扫描", style="Accent.TButton",
                   command=self.big_scan).grid(row=0, column=5, padx=8)
        card.columnconfigure(1, weight=1)
        bar = ttk.Frame(self.tab_big)
        bar.pack(fill="x", padx=10)
        ttk.Button(bar, text="📂 搬走选中的…", style="Soft.TButton",
                   command=self.big_move).pack(side="left")
        ttk.Button(bar, text="♻ 选中项移入回收站", style="Danger.TButton",
                   command=self.big_recycle).pack(side="left", padx=8)
        self.bf_tree = self._tree(self.tab_big, ("path", "size"))
        self.bf_tree.column("path", width=720, anchor="w")
        self.bf_tree.column("size", width=110, anchor="e")
        self.bf_tree.heading("path", text="文件")
        self.bf_tree.heading("size", text="大小")

    def big_scan(self):
        try:
            min_mb = float(self.bf_min.get() or 500)
        except ValueError:
            messagebox.showerror("Cpan", "最小体积必须是数字。")
            return
        path = self.bf_dir.get().strip()
        self._run(lambda: core.find_big_files(path, min_mb, 50), self._big_scanned)

    def _big_scanned(self, hits):
        self.big_hits = hits
        self.bf_tree.delete(*self.bf_tree.get_children())
        for i, h in enumerate(hits):
            self.bf_tree.insert("", "end", iid=str(i),
                                tags=("odd",) if i % 2 else (),
                                values=(h["path"], core.fmt_size(h["size"])))
        self.log(f"大文件：找到 {len(hits)} 个（仅列出，不会自动删）。")

    def big_move(self):
        sel = self.bf_tree.selection()
        if len(sel) != 1:
            messagebox.showinfo("Cpan", "请选中一个文件/文件夹。")
            return
        src = self.big_hits[int(sel[0])]["path"]
        dst = filedialog.askdirectory(title="搬到哪个文件夹？", initialdir="D:\\")
        if not dst:
            return
        self.mv_src.delete(0, "end")
        self.mv_src.insert(0, src)
        self.mv_dst.delete(0, "end")
        self.mv_dst.insert(0, dst)
        self.move_now()

    def big_recycle(self):
        sel = self.bf_tree.selection()
        paths = [self.big_hits[int(i)]["path"] for i in sel] if sel else []
        if not paths:
            messagebox.showinfo("Cpan", "请先选中文件。")
            return
        if not messagebox.askyesno("确认", f"把 {len(paths)} 项移入回收站？"):
            return
        pcb = self._pcb()
        self._run(lambda: core.delete_custom(paths, confirm=True, progress=pcb),
                  self._custom_deleted)

    # ------------------------------------------------------------ shared
    def _pick_dir(self, entry):
        d = filedialog.askdirectory(initialdir=entry.get() or "C:\\")
        if d:
            entry.delete(0, "end")
            entry.insert(0, d)

    def _pick_file(self, entry):
        f = filedialog.askopenfilename(initialdir=entry.get() or "C:\\")
        if f:
            entry.delete(0, "end")
            entry.insert(0, f)

    def _build_logcard(self):
        card = ttk.LabelFrame(self, text="操作记录", style="Card.TLabelframe")
        card.pack(fill="x", padx=10, pady=(4, 10))
        self.logbox = ScrolledText(card, height=7, state="disabled",
                                   font=(MONO, 9), bg="#FBFCFE",
                                   relief="flat", borderwidth=0)
        self.logbox.pack(fill="x", padx=6, pady=(0, 6))

    def _build_progressbar(self):
        wrap = ttk.Frame(self)
        wrap.pack(fill="x", padx=12, pady=(6, 2))
        self.plabel = ttk.Label(wrap, text="就绪", style="Muted.TLabel")
        self.plabel.pack(side="left")
        self.pbar = ttk.Progressbar(wrap, length=320, maximum=100, value=0,
                                    style="UI.Horizontal.TProgressbar")
        self.pbar.pack(side="right")

    def _pcb(self):
        """Progress callback handed to core; runs in the worker thread,
        so it only enqueues UI messages."""
        def cb(pct, label, done, total):
            text = f"{label}　{core.fmt_size(done)} / {core.fmt_size(total)}"
            self.q.put(("progress", pct, text))
        return cb

    def log(self, msg: str):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    # ------------------------------------------------------------ worker
    def _run(self, fn, on_done):
        if self.busy:
            self.log("上一个任务还在进行，请稍候…")
            return
        self.busy = True
        self.log("处理中…")

        def worker():
            try:
                result = fn()
                self.q.put(("done", on_done, result, None))
            except Exception as exc:
                self.q.put(("done", on_done, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll()

    def _poll(self):
        # drain the queue in batches, otherwise hundreds of progress
        # messages pile up and the bar appears frozen
        try:
            while True:
                kind, *payload = self.q.get_nowait()
                if kind == "log":
                    self.log(payload[0])
                elif kind == "ui":
                    payload[0]()
                elif kind == "progress":
                    pct, text = payload
                    self.pbar["value"] = pct
                    self.plabel.configure(text=text)
                elif kind == "done":
                    on_done, result, err = payload
                    self.busy = False
                    if self.pbar["value"] > 0:
                        # keep "100% 完成" visible briefly, then reset
                        self.plabel.configure(text="完成")
                        self.after(1500, self._reset_progress)
                    if err:
                        self.log(f"出错：{err}")
                    elif on_done:
                        on_done(result)
        except queue.Empty:
            pass
        if self.busy:
            self.after(80, self._poll)

    def _reset_progress(self):
        self.pbar["value"] = 0
        self.plabel.configure(text="就绪")


def main():
    app = CpanApp()
    app.mainloop()


if __name__ == "__main__":
    main()
