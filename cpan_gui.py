"""Cpan 图形界面 — 现代侧边栏布局（tkinter，纯标准库）。

页面：概览 / 垃圾清理 / 空间分析 / 软件搬家 / 文件搬家 /
      自定义清理 / 软件卸载 / 大文件 / 操作日志。

安全约束不变：白名单自动清理、用户文件走回收站、先预览后确认、
危险路径拒绝、操作写日志。所有耗时任务在后台线程运行，UI 不冻结。
"""

from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import cpan_core as core

# ---------------------------------------------------------------- theme

FONT = "Microsoft YaHei UI"
MONO = "Consolas"

BG = "#F3F6FB"
CARD = "#FFFFFF"
BORDER = "#E2E8F2"
TEXT = "#1A2333"
MUTED = "#7B879B"
MUTED2 = "#A7B0BF"
PRIMARY = "#3B6FF5"
PRIMARY_HOVER = "#2C5BD8"
PRIMARY_SOFT = "#EAF0FF"
DANGER = "#E24C54"
DANGER_HOVER = "#C93B43"
DANGER_SOFT = "#FDEDEE"
OK = "#18A56C"
OK_SOFT = "#E9F8F1"
WARN = "#C98A16"
WARN_SOFT = "#FFF5E0"
SIDEBAR = "#0F1A2E"
SIDEBAR_HOVER = "#17243D"
SIDEBAR_ACTIVE = "#1C2D4C"
SIDEBAR_TEXT = "#A6B6D1"
SIDEBAR_MUTED = "#6F7F9C"
WHITE = "#FFFFFF"
CHECK, EMPTY, BLOCKED = "☑", "☐", "—"

SCALE = 1.0


def px(n: float) -> int:
    """Scale a design pixel value for the current screen."""
    return int(round(n * SCALE))


def resource_path(*parts) -> str:
    """Resolve a bundled asset both in the source tree and a PyInstaller EXE."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kw):
    """Draw a smooth rounded rectangle on a Canvas (with fallback)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    if r <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **kw)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kw)


def draw_nav_icon(canvas: tk.Canvas, kind: str, color: str) -> None:
    """Small line icons, drawn with primitives so no emoji font is needed."""
    c = canvas
    c.delete("all")
    w = 1.6
    def line(*coords, **kw):
        c.create_line(*coords, fill=color, width=w, capstyle=tk.ROUND,
                      joinstyle=tk.ROUND, **kw)
    if kind == "overview":
        for x, y in ((3, 3), (11, 3), (3, 11), (11, 11)):
            c.create_rectangle(x, y, x + 6, y + 6, outline=color, width=w)
    elif kind == "junk":
        line(3, 6, 17, 6)
        line(7, 3, 13, 3)
        line(6, 6, 7, 17, 13, 17, 14, 6)
        line(9, 9, 9, 14)
        line(11, 9, 11, 14)
    elif kind == "analysis":
        c.create_oval(3, 3, 17, 17, outline=color, width=w)
        line(10, 10, 10, 3)
        line(10, 10, 16, 13)
    elif kind == "custom":
        c.create_oval(3, 3, 12, 12, outline=color, width=w)
        line(11, 11, 17, 17)
    elif kind == "appmove":
        line(3, 7, 15, 7)
        line(12, 4, 15, 7, 12, 10)
        line(17, 13, 5, 13)
        line(8, 10, 5, 13, 8, 16)
    elif kind == "filemove":
        line(3, 10, 16, 10)
        line(12, 6, 16, 10, 12, 14)
        line(3, 4, 3, 16)
    elif kind == "big":
        c.create_polygon(5, 3, 12, 3, 15, 6, 15, 17, 5, 17,
                         outline=color, fill="", width=w)
        line(12, 3, 12, 6, 15, 6)
    elif kind == "uninstall":
        c.create_rectangle(3, 6, 17, 17, outline=color, width=w)
        line(7, 3, 13, 3)
        line(8, 11.5, 12, 11.5)
    elif kind == "log":
        line(4, 5, 16, 5)
        line(4, 10, 16, 10)
        line(4, 15, 12, 15)
    else:
        c.create_oval(4, 4, 16, 16, outline=color, width=w)


class PillButton(tk.Canvas):
    """Flat pill-shaped button with hover / pressed / disabled states."""

    PALETTES = {
        "primary": (PRIMARY, WHITE, PRIMARY_HOVER, ""),
        "soft": (PRIMARY_SOFT, PRIMARY, "#DCE7FF", ""),
        "ghost": ("#F2F5FA", "#3B475A", "#E6ECF5", "#E2E8F2"),
        "danger": (DANGER, WHITE, DANGER_HOVER, ""),
        "danger_soft": (DANGER_SOFT, DANGER, "#FADADD", ""),
        "success": (OK, WHITE, "#128F5E", ""),
        "dark": (SIDEBAR_ACTIVE, "#E9F0FF", "#253A60", ""),
    }

    def __init__(self, parent, text, command=None, kind="primary", size=10,
                 height=32, padx=16, width=None):
        try:
            bg = parent.cget("background")
        except tk.TclError:
            bg = CARD
        bold = kind in ("primary", "danger", "success")
        self._font = tkfont.Font(family=FONT, size=size,
                                 weight="bold" if bold else "normal")
        self._height = px(height)
        self._auto_width = width is None
        self._req_w = px(width) if width is not None else \
            self._font.measure(text) + px(padx) * 2
        super().__init__(parent, width=self._req_w, height=self._height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2",
                         takefocus=1)
        self.text = text
        self.command = command
        self.kind = kind
        self.enabled = True
        self._hover = False
        self._pressed = False
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Return>", lambda _e: self._invoke())
        self.bind("<space>", lambda _e: self._invoke())
        self._draw()

    def _draw(self):
        if not self.winfo_exists():
            return
        w = max(self.winfo_width(), self._req_w)
        h = self._height
        fill, fg, hover, outline = self.PALETTES.get(
            self.kind, self.PALETTES["primary"])
        if not self.enabled:
            fill, fg, outline = "#EDF0F6", MUTED2, ""
        elif self._pressed:
            fill = hover
        elif self._hover:
            fill = hover
        self.delete("all")
        rounded_rect(self, 0, 0, w, h, h / 2, fill=fill,
                     outline=outline or "", width=1 if outline else 0)
        self.create_text(w / 2, h / 2, text=self.text, fill=fg,
                         font=self._font)

    def _enter(self, _e):
        self._hover = True
        self._draw()

    def _leave(self, _e):
        self._hover = False
        self._pressed = False
        self._draw()

    def _press(self, _e):
        if not self.enabled:
            return
        self._pressed = True
        self._draw()
        self.focus_set()

    def _release(self, e):
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if self.enabled and was_pressed and 0 <= e.x <= self.winfo_width():
            self._invoke()

    def _invoke(self):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self._draw()

    def set_text(self, text: str):
        self.text = text
        if self._auto_width:
            self._req_w = self._font.measure(text) + px(32)
            self.configure(width=self._req_w)
        self._draw()


class NavItem(tk.Frame):
    """Sidebar navigation row with a drawn icon and active marker."""

    def __init__(self, parent, key, label, icon, command):
        super().__init__(parent, bg=SIDEBAR, cursor="hand2",
                         height=px(36))
        self.pack_propagate(False)
        self.key = key
        self.icon_kind = icon
        self.active = False
        self.command = command
        self.icon = tk.Canvas(self, width=px(20), height=px(20), bg=SIDEBAR,
                              highlightthickness=0)
        self.icon.pack(side="left", padx=(px(19), px(11)))
        self.label = tk.Label(self, text=label, bg=SIDEBAR, fg=SIDEBAR_TEXT,
                              font=(FONT, 10), anchor="w")
        self.label.pack(side="left", fill="x", expand=True)
        self.marker = tk.Frame(self, bg=SIDEBAR, width=px(3))
        self.marker.place(x=0, y=px(8), relheight=1.0, height=-px(16))
        for w in (self, self.icon, self.label):
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            w.bind("<Button-1>", lambda _e: self.command(self.key))

    def _paint(self, bg, fg, active=False):
        self.configure(bg=bg)
        self.icon.configure(bg=bg)
        self.label.configure(bg=bg, fg=fg,
                             font=(FONT, 10, "bold" if active else "normal"))
        self.marker.configure(bg=PRIMARY if active else bg)
        draw_nav_icon(self.icon, self.icon_kind,
                      PRIMARY if active else fg)

    def _enter(self, _e):
        if not self.active:
            self._paint(SIDEBAR_HOVER, "#D9E4F7")

    def _leave(self, _e):
        if not self.active:
            self._paint(SIDEBAR, SIDEBAR_TEXT)

    def set_active(self, active: bool):
        self.active = active
        if active:
            self._paint(SIDEBAR_ACTIVE, WHITE, True)
        else:
            self._paint(SIDEBAR, SIDEBAR_TEXT)


class Meter(tk.Canvas):
    """Thin rounded progress meter, supporting determinate + indeterminate."""

    def __init__(self, parent, width=200, height=7, color=PRIMARY, bg=None):
        if bg is None:
            try:
                bg = parent.cget("background")
            except tk.TclError:
                bg = CARD
        super().__init__(parent, width=px(width), height=px(height), bg=bg,
                         highlightthickness=0, bd=0)
        self._height = px(height)
        self.color = color
        self.pct = 0.0
        self._job = None
        self._ind_pos = 0.0
        self.bind("<Configure>", lambda _e: self._draw())

    def _draw(self):
        if not self.winfo_exists():
            return
        w = max(self.winfo_width(), 2)
        h = self._height
        self.delete("all")
        rounded_rect(self, 0, 0, w, h, h / 2, fill="#E8EDF5", outline="")
        if self.pct > 0:
            fw = max(h, w * min(100.0, self.pct) / 100.0)
            rounded_rect(self, 0, 0, fw, h, h / 2, fill=self.color,
                         outline="")

    def set(self, pct: float, color: str | None = None):
        self._stop_indeterminate()
        self.pct = max(0.0, min(100.0, float(pct)))
        if color:
            self.color = color
        self._draw()

    def indeterminate(self):
        self._stop_indeterminate()
        self.pct = 0
        self._ind_pos = 0.0
        self._tick()

    def _tick(self):
        if not self.winfo_exists():
            return
        w = max(self.winfo_width(), 2)
        h = self._height
        seg = max(w * 0.22, h * 3)
        x = (w + seg) * (self._ind_pos / 100.0) - seg
        self.delete("all")
        rounded_rect(self, 0, 0, w, h, h / 2, fill="#E8EDF5", outline="")
        rounded_rect(self, x, 0, x + seg, h, h / 2, fill=self.color,
                     outline="")
        self._ind_pos = (self._ind_pos + 4) % 100
        self._job = self.after(45, self._tick)

    def _stop_indeterminate(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None


# ------------------------------------------------------------- page meta

PAGE_META = {
    "overview": ("概览", "C 盘状态、空间占用与一键整理"),
    "junk": ("垃圾清理", "只删除可再生的临时文件与缓存，白名单之外不碰"),
    "analysis": ("空间分析", "按文件夹找出到底是谁占满了磁盘"),
    "custom": ("自定义清理", "按扩展名、体积、时间筛选，删除走回收站"),
    "appmove": ("软件搬家", "把程序移出 C 盘，原路径用目录联接保持可用"),
    "move": ("文件搬家", "把大文件夹搬到其他盘，完成后自动校验"),
    "big": ("大文件", "揪出单个体积最大的文件，再决定去留"),
    "uninstall": ("软件卸载", "调用软件官方卸载器，全程可控"),
    "log": ("操作日志", "每一次实际执行的清理、搬移与卸载都有记录"),
}

NAV_GROUPS = [
    ("空间", [
        ("overview", "概览", "overview"),
        ("junk", "垃圾清理", "junk"),
        ("analysis", "空间分析", "analysis"),
        ("custom", "自定义清理", "custom"),
    ]),
    ("搬家", [
        ("appmove", "软件搬家", "appmove"),
        ("move", "文件搬家", "filemove"),
        ("big", "大文件", "big"),
    ]),
    ("管理", [
        ("uninstall", "软件卸载", "uninstall"),
        ("log", "操作日志", "log"),
    ]),
]


class CpanApp(tk.Tk):
    def __init__(self):
        _enable_dpi_awareness()
        super().__init__()

        global SCALE
        dpi_ratio = 1.0
        try:
            self.tk.call("tk", "scaling", self.winfo_fpixels("1i") / 72.0)
            dpi_ratio = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except Exception:
            pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        # Geometry is scaled a little more conservatively than fonts so a
        # 1080p screen at 150% still fits a full page without clipping.
        SCALE = min(dpi_ratio, max(1.0, sh * 0.9 / 820.0))

        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self._cancel_ev: threading.Event | None = None
        self.junk_rows: list[dict] = []
        self.admin = core.is_admin()
        self.pages: dict[str, tk.Frame] = {}
        self.nav_items: dict[str, NavItem] = {}
        self.current_page = ""
        self._dot = None
        self._am_gen = 0
        self._am_loaded = False
        self._un_loaded = False
        self._am_items: list[dict] = []
        self._am_sizes: dict[int, int] = {}
        self._un_items: list[dict] = []
        self._un_sort_col = "name"
        self._un_sort_rev = False
        self.cu_hits: list[dict] = []
        self.big_hits: list[dict] = []
        self._sa_items: list[dict] = []
        self._sa_paths: dict[str, dict] = {}

        self.title("Cpan — C 盘空间管家")
        w = max(px(980), min(px(1200), sw - px(60)))
        h = max(px(660), min(px(820), sh - px(60)))
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - px(10))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(min(px(1000), sw - px(40)),
                     min(px(660), sh - px(40)))
        self.configure(bg=BG)
        self._set_window_icon()
        self._setup_style()
        self._build_shell()
        self._show_page("overview")
        self._refresh_overview()
        self._refresh_drives()
        self._poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(350, self.junk_scan)

    def _set_window_icon(self):
        ico = resource_path("assets", "cpan.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(default=ico)
                return
            except Exception:
                pass
        # Fallback: a small drawn mark if the asset is missing.
        try:
            img = tk.PhotoImage(width=32, height=32)
            img.put(PRIMARY, to=(0, 0, 32, 32))
            img.put("#FFFFFF", to=(10, 7, 23, 10))
            img.put("#FFFFFF", to=(7, 7, 10, 25))
            img.put("#FFFFFF", to=(10, 22, 23, 25))
            self.iconphoto(True, img)
            self._icon_img = img
        except Exception:
            pass

    # ------------------------------------------------------------- style
    def _setup_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
        s.configure("Treeview", background=CARD, fieldbackground=CARD,
                    foreground=TEXT, borderwidth=0, relief="flat",
                    rowheight=px(32), font=(FONT, 10))
        s.configure("Treeview.Heading", background="#F7F9FD",
                    foreground="#5F6D83", font=(FONT, 9, "bold"),
                    borderwidth=0, relief="flat",
                    padding=(px(8), px(7)))
        s.map("Treeview.Heading",
              background=[("active", "#EEF3FA")])
        s.map("Treeview",
              background=[("selected", PRIMARY_SOFT)],
              foreground=[("selected", TEXT)])
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Vertical.TScrollbar", background="#D7DFEC",
                    troughcolor=CARD, bordercolor=CARD, arrowcolor=MUTED,
                    width=px(10), arrowsize=px(10), relief="flat",
                    borderwidth=0)
        s.map("Vertical.TScrollbar",
              background=[("active", "#C4CFDF")])

    # ------------------------------------------------------------- shell
    def _build_shell(self):
        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=px(224))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        self.main = tk.Frame(self, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        self._build_topbar()
        self._build_statusbar()
        self.page_host = tk.Frame(self.main, bg=BG)
        self.page_host.pack(fill="both", expand=True)
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)
        self._build_overview()
        self._build_junk()
        self._build_analysis()
        self._build_custom()
        self._build_appmove()
        self._build_move()
        self._build_big()
        self._build_uninstall()
        self._build_log()

    def _build_sidebar(self):
        brand = tk.Frame(self.sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=px(18), pady=(px(18), px(12)))
        logo = tk.Canvas(brand, width=px(38), height=px(38), bg=SIDEBAR,
                         highlightthickness=0)
        logo.pack(side="left")
        rounded_rect(logo, 0, 0, px(38), px(38), px(11),
                     fill=PRIMARY, outline="")
        logo.create_text(px(19), px(19), text="C", fill="white",
                         font=(FONT, 16, "bold"))
        txt = tk.Frame(brand, bg=SIDEBAR)
        txt.pack(side="left", padx=(px(10), 0))
        tk.Label(txt, text="Cpan", bg=SIDEBAR, fg="white",
                 font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(txt, text="C 盘空间管家 · v2.0", bg=SIDEBAR,
                 fg=SIDEBAR_MUTED, font=(FONT, 8)).pack(anchor="w")

        for group, items in NAV_GROUPS:
            gl = tk.Frame(self.sidebar, bg=SIDEBAR)
            gl.pack(fill="x", padx=px(22), pady=(px(7), px(2)))
            tk.Label(gl, text=group, bg=SIDEBAR, fg=SIDEBAR_MUTED,
                     font=(FONT, 8, "bold")).pack(anchor="w")
            for key, label, icon in items:
                item = NavItem(self.sidebar, key, label, icon, self._show_page)
                item.pack(fill="x")
                self.nav_items[key] = item

        spacer = tk.Frame(self.sidebar, bg=SIDEBAR)
        spacer.pack(fill="both", expand=True)
        bottom = tk.Frame(self.sidebar, bg=SIDEBAR)
        bottom.pack(fill="x", padx=px(13), pady=(0, px(10)))
        mode = tk.Frame(bottom, bg=SIDEBAR_ACTIVE)
        mode.pack(fill="x", padx=px(3), pady=(0, px(10)))
        inner = tk.Frame(mode, bg=SIDEBAR_ACTIVE)
        inner.pack(fill="x", padx=px(12), pady=px(8))
        tk.Label(inner, text="管理员模式" if self.admin else "普通用户模式",
                 bg=SIDEBAR_ACTIVE, fg="#7EE3B1" if self.admin else "#F4C35E",
                 font=(FONT, 9, "bold")).pack(anchor="w")
        tk.Label(inner,
                 text="系统缓存与组件清理已解锁" if self.admin
                 else "系统级清理需管理员权限",
                 bg=SIDEBAR_ACTIVE, fg=SIDEBAR_MUTED, font=(FONT, 8),
                 wraplength=px(165), justify="left").pack(anchor="w",
                                                          pady=(px(3), 0))
        if not self.admin:
            PillButton(inner, "以管理员重启", self._elevate,
                       kind="primary", size=9, height=28,
                       padx=12).pack(anchor="w", pady=(px(8), 0))

    def _build_topbar(self):
        bar = tk.Frame(self.main, bg=BG)
        bar.pack(fill="x", padx=px(26), pady=(px(18), px(4)))
        left = tk.Frame(bar, bg=BG)
        left.pack(side="left", anchor="w")
        self.page_title = tk.Label(left, text="", bg=BG, fg=TEXT,
                                   font=(FONT, 17, "bold"))
        self.page_title.pack(anchor="w")
        self.page_sub = tk.Label(left, text="", bg=BG, fg=MUTED,
                                 font=(FONT, 9))
        self.page_sub.pack(anchor="w", pady=(px(2), 0))

        right = tk.Frame(bar, bg=BG)
        right.pack(side="right", anchor="e")
        badge_bg = PRIMARY_SOFT if self.admin else WARN_SOFT
        badge_fg = PRIMARY if self.admin else "#9A6A00"
        self.admin_badge = tk.Label(
            right, text="管理员模式" if self.admin else "普通模式",
            bg=badge_bg, fg=badge_fg, font=(FONT, 8, "bold"),
            padx=px(10), pady=px(5), cursor="arrow" if self.admin else "hand2")
        self.admin_badge.pack(side="right", padx=(px(10), 0))
        if not self.admin:
            self.admin_badge.bind("<Button-1>",
                                  lambda _e: self._elevate())

        chip = tk.Frame(right, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        chip.pack(side="right")
        chip_inner = tk.Frame(chip, bg=CARD)
        chip_inner.pack(padx=px(12), pady=px(7))
        row = tk.Frame(chip_inner, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="C 盘", bg=CARD, fg=TEXT,
                 font=(FONT, 9, "bold")).pack(side="left")
        self.top_disk_text = tk.Label(row, text="读取中…", bg=CARD, fg=MUTED,
                                      font=(FONT, 8))
        self.top_disk_text.pack(side="right")
        self.top_disk_meter = Meter(chip_inner, width=210, height=5, bg=CARD)
        self.top_disk_meter.pack(fill="x", pady=(px(4), 0))

    def _build_statusbar(self):
        bar = tk.Frame(self.main, bg=CARD, height=px(38))
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        tk.Frame(self.main, bg=BORDER, height=1).pack(side="bottom", fill="x")
        left = tk.Frame(bar, bg=CARD)
        left.pack(side="left", padx=px(26))
        self.status_dot = tk.Canvas(bar, width=px(9), height=px(9), bg=CARD,
                                    highlightthickness=0)
        self.status_dot.pack(side="left")
        self._dot = self.status_dot.create_oval(1, 1, px(8), px(8),
                                                fill=PRIMARY, outline="")
        self.status_lbl = tk.Label(bar, text="就绪", bg=CARD, fg=MUTED,
                                   font=(FONT, 9))
        self.status_lbl.pack(side="left", padx=(px(7), 0))
        self.task_meter = Meter(bar, width=180, height=5, bg=CARD)
        self.task_meter.pack(side="right", padx=px(26))

    # ------------------------------------------------------------ helpers
    def _make_page(self, key):
        page = tk.Frame(self.page_host, bg=BG)
        page.grid(row=0, column=0, sticky="nsew")
        self.pages[key] = page
        return page

    def _card(self, parent, padx=16, pady=14):
        outer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER,
                         highlightthickness=1, bd=0)
        body = tk.Frame(outer, bg=CARD)
        body.pack(fill="both", expand=True, padx=px(padx), pady=px(pady))
        return outer, body

    def _label(self, parent, text="", size=10, bold=False, fg=TEXT, bg=None,
               **kw):
        if bg is None:
            try:
                bg = parent.cget("background")
            except tk.TclError:
                bg = CARD
        return tk.Label(parent, text=text, bg=bg, fg=fg,
                        font=(FONT, size, "bold" if bold else "normal"), **kw)

    def _entry(self, parent, var=None, width=30):
        return tk.Entry(parent, textvariable=var, width=width,
                        font=(FONT, 10), bg="#FBFCFE", fg=TEXT, relief="flat",
                        bd=0, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=PRIMARY,
                        insertbackground=TEXT, selectbackground=PRIMARY_SOFT,
                        selectforeground=TEXT)

    def _table(self, parent, columns, height=9, selectmode="browse"):
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=px(2), pady=px(2))
        tree = ttk.Treeview(inner, columns=[c[0] for c in columns],
                            show="headings", height=height,
                            selectmode=selectmode)
        for key, title, width, anchor, stretch in columns:
            tree.heading(key, text=title, anchor=anchor)
            tree.column(key, width=px(width), minwidth=px(40),
                        anchor=anchor, stretch=stretch)
        sb = ttk.Scrollbar(inner, orient="vertical", command=tree.yview,
                           style="Vertical.TScrollbar")
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.tag_configure("odd", background="#F9FBFE")
        tree.tag_configure("muted", foreground=MUTED2)
        tree.tag_configure("warn", foreground=WARN)
        tree.tag_configure("ok", foreground=OK)
        tree.tag_configure("danger", foreground=DANGER)
        return card, tree

    def _placeholder(self, tree, text):
        tree.delete(*tree.get_children())
        cols = tree["columns"]
        values = [""] * len(cols)
        if len(values) > 1:
            values[1] = text
        elif values:
            values[0] = text
        tree.insert("", "end", iid="__placeholder__", values=values,
                    tags=("muted",))

    def _show_page(self, key):
        if key not in self.pages:
            return
        title, sub = PAGE_META[key]
        self.page_title.configure(text=title)
        self.page_sub.configure(text=sub)
        for k, item in self.nav_items.items():
            item.set_active(k == key)
        self.pages[key].tkraise()
        self.current_page = key
        if key == "overview":
            self._refresh_overview()
            self._refresh_drives()
        elif key == "log":
            self.log_refresh()
        elif key == "appmove" and not self._am_loaded and not self.busy:
            self.am_refresh()
        elif key == "uninstall" and not self._un_loaded and not self.busy:
            self.un_load()

    def _set_status(self, text, level="info"):
        colors = {"info": PRIMARY, "ok": OK, "warn": WARN,
                  "error": DANGER, "muted": MUTED}
        self.status_dot.itemconfig(self._dot,
                                   fill=colors.get(level, PRIMARY))
        self.status_lbl.configure(text=text)

    def _default_dest(self):
        for d in core.list_drives():
            if d["letter"].upper() != "C:":
                return d["root"]
        return "C:\\"

    def _pick_dir(self, entry):
        start = entry.get().strip() or "C:\\"
        if not os.path.isdir(start):
            start = "C:\\"
        chosen = filedialog.askdirectory(initialdir=start)
        if chosen:
            entry.delete(0, "end")
            entry.insert(0, chosen)

    def _pick_file(self, entry):
        start = entry.get().strip() or "C:\\"
        if not os.path.isdir(os.path.dirname(start)):
            start = "C:\\"
        chosen = filedialog.askopenfilename(initialdir=start)
        if chosen:
            entry.delete(0, "end")
            entry.insert(0, chosen)

    def _choose_folder(self, title, initial=None):
        start = initial or self._default_dest()
        if not os.path.isdir(start):
            start = "C:\\"
        return filedialog.askdirectory(title=title, initialdir=start)

    def _open_path(self, path):
        try:
            if path and os.path.isdir(path):
                os.startfile(path)
            elif path and os.path.exists(path):
                os.startfile(os.path.dirname(path))
        except Exception as exc:
            messagebox.showwarning("Cpan", f"无法打开：{exc}")

    def _open_select(self, path):
        try:
            if os.path.isdir(path):
                os.startfile(path)
            elif os.path.exists(path):
                subprocess.Popen(["explorer", "/select,",
                                  os.path.normpath(path)])
            else:
                messagebox.showinfo("Cpan", "文件已不存在。")
        except Exception as exc:
            messagebox.showwarning("Cpan", f"无法打开：{exc}")

    def _elevate(self):
        if self.admin:
            return
        if not messagebox.askyesno(
                "需要管理员权限",
                "系统级清理（Windows 临时文件、更新缓存、DISM、关闭休眠）"
                "需要管理员权限。\n\n是否以管理员身份重新启动 Cpan？\n"
                "（当前窗口会关闭）"):
            return
        ok, msg = core.relaunch_as_admin()
        if ok:
            self.destroy()
        else:
            messagebox.showerror("Cpan", msg)

    def _require_admin(self, what: str) -> bool:
        if self.admin:
            return True
        if messagebox.askyesno(
                "需要管理员权限",
                f"「{what}」需要管理员权限。\n\n"
                "是否以管理员身份重新启动 Cpan？当前窗口会关闭。"):
            ok, msg = core.relaunch_as_admin()
            if ok:
                self.destroy()
            else:
                messagebox.showerror("Cpan", msg)
        return False

    def _progress_cb(self):
        def cb(pct, label, done, total):
            self.q.put(("progress", pct,
                        f"{label}  {core.fmt_size(done)} / "
                        f"{core.fmt_size(total)}"))
        return cb

    def _run_task(self, fn, on_done=None, label="处理中…",
                  progress="indeterminate", on_error=None):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return False
        self.busy = True
        self._set_status(label, "info")
        if progress == "indeterminate":
            self.task_meter.indeterminate()
        else:
            self.task_meter.set(0)

        def worker():
            try:
                result = fn()
                self.q.put(("done", on_done, result, None, on_error))
            except Exception as exc:  # surfaced in the UI thread
                self.q.put(("done", on_done, None, exc, on_error))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                try:
                    if kind == "ui":
                        msg[1]()
                    elif kind == "progress":
                        self.task_meter.set(msg[1])
                        self._set_status(msg[2], "info")
                    elif kind == "status":
                        self._set_status(msg[1],
                                         msg[2] if len(msg) > 2 else "info")
                    elif kind == "done":
                        _, on_done, result, err, on_error = msg
                        self.busy = False
                        self.task_meter._stop_indeterminate()
                        if err is not None:
                            self.task_meter.set(0)
                            self._set_status(f"出错：{err}", "error")
                            if on_error:
                                on_error(err)
                            else:
                                messagebox.showerror("Cpan 出错了", str(err))
                        else:
                            self.task_meter.set(100)
                            self._set_status("完成", "ok")
                            self.after(1400, self._reset_meter)
                            if on_done:
                                on_done(result)
                except Exception as exc:
                    self._set_status(f"界面刷新出错：{exc}", "error")
        except queue.Empty:
            pass
        self.after(60, self._poll)

    def _reset_meter(self):
        if not self.busy:
            self.task_meter.set(0)

    def _on_close(self):
        if self.busy and not messagebox.askyesno(
                "任务正在进行",
                "当前有任务正在执行，退出可能中断操作。\n"
                "搬移类操作若已开始，源数据不会被提前删除。\n\n确定退出吗？"):
            return
        self.destroy()

    # ----------------------------------------------------------- overview
    def _build_overview(self):
        page = self._make_page("overview")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        wrap.grid_columnconfigure(0, weight=3)
        wrap.grid_columnconfigure(1, weight=2)
        wrap.grid_rowconfigure(0, weight=3, minsize=px(188))
        wrap.grid_rowconfigure(1, weight=3, minsize=px(175))
        wrap.grid_rowconfigure(2, weight=2, minsize=px(105))

        hero_outer, hero = self._card(wrap, px(22), px(16))
        hero_outer.grid(row=0, column=0, sticky="nsew",
                        padx=(0, px(14)))
        hero_inner = tk.Frame(hero, bg=CARD)
        hero_inner.pack(fill="x", expand=True)
        self._label(hero_inner, "C 盘空间", 11, True).pack(anchor="w")
        free_row = tk.Frame(hero_inner, bg=CARD)
        free_row.pack(anchor="w", pady=(px(4), 0))
        self.ov_free = tk.Label(free_row, text="—", bg=CARD, fg=TEXT,
                                font=(FONT, 28, "bold"))
        self.ov_free.pack(side="left")
        tk.Label(free_row, text="GB 可用", bg=CARD, fg=MUTED,
                 font=(FONT, 10)).pack(side="left", padx=(px(8), 0),
                                       pady=(px(9), 0))
        self.ov_sub = tk.Label(hero_inner, text="正在读取磁盘信息…", bg=CARD,
                               fg=MUTED, font=(FONT, 9))
        self.ov_sub.pack(anchor="w", pady=(0, px(10)))
        self.hero_meter = Meter(hero_inner, width=420, height=8, bg=CARD)
        self.hero_meter.pack(fill="x")
        btns = tk.Frame(hero_inner, bg=CARD)
        btns.pack(anchor="w", pady=(px(12), 0))
        PillButton(btns, "一键智能清理", self.smart_clean,
                   kind="primary").pack(side="left")
        PillButton(btns, "重新扫描", self.junk_scan,
                   kind="soft").pack(side="left", padx=(px(8), 0))
        self._label(hero_inner,
                    "推荐项只包含可再生缓存；回收站与 Windows.old 默认不选。",
                    9, fg=MUTED).pack(anchor="w", pady=(px(8), 0))
        self.ov_hint = tk.Label(hero_inner, text="", bg=CARD, fg=PRIMARY,
                                font=(FONT, 9), cursor="hand2")
        self.ov_hint.pack(anchor="w", pady=(px(5), 0))
        self.ov_hint.bind("<Button-1>", lambda _e: self._show_page("junk"))

        tiles = tk.Frame(wrap, bg=BG)
        tiles.grid(row=0, column=1, sticky="nsew")
        tiles.grid_columnconfigure(0, weight=1)
        tiles.grid_columnconfigure(1, weight=1)
        tiles.grid_rowconfigure(0, weight=1)
        junk_tile, junk_body = self._card(tiles, px(15), px(13))
        junk_tile.grid(row=0, column=0, sticky="nsew",
                       padx=(0, px(9)))
        junk_inner = tk.Frame(junk_body, bg=CARD)
        junk_inner.pack(fill="x", expand=True)
        self._label(junk_inner, "可清理垃圾", 9, fg=MUTED).pack(anchor="w")
        self.ov_junk_val = tk.Label(junk_inner, text="—", bg=CARD, fg=TEXT,
                                    font=(FONT, 18, "bold"))
        self.ov_junk_val.pack(anchor="w", pady=(px(5), 0))
        self.ov_junk_note = self._label(junk_inner, "扫描后显示", 8,
                                        fg=MUTED, justify="left",
                                        wraplength=px(130))
        self.ov_junk_note.pack(anchor="w", pady=(px(4), 0))

        rec_tile, rec_body = self._card(tiles, px(15), px(13))
        rec_tile.grid(row=0, column=1, sticky="nsew")
        rec_inner = tk.Frame(rec_body, bg=CARD)
        rec_inner.pack(fill="x", expand=True)
        self._label(rec_inner, "回收站", 9, fg=MUTED).pack(anchor="w")
        self.ov_recycle_val = tk.Label(rec_inner, text="—", bg=CARD,
                                       fg=TEXT, font=(FONT, 18, "bold"))
        self.ov_recycle_val.pack(anchor="w", pady=(px(5), 0))
        self._label(rec_inner, "点击进入垃圾清理\n可手动清空", 8,
                    fg=MUTED, justify="left").pack(anchor="w",
                                                   pady=(px(4), 0))
        self._bind_click(junk_tile, lambda: self._show_page("junk"))
        self._bind_click(rec_tile, lambda: self._show_page("junk"))

        drives_outer, drives_body = self._card(wrap, px(18), px(13))
        drives_outer.grid(row=1, column=0, sticky="nsew",
                          padx=(0, px(14)), pady=(px(14), 0))
        head = tk.Frame(drives_body, bg=CARD)
        head.pack(fill="x", pady=(0, px(6)))
        self._label(head, "磁盘使用", 11, True).pack(side="left")
        PillButton(head, "刷新", self._refresh_disks, kind="ghost",
                   size=8, height=24, padx=10).pack(side="right")
        self.drive_box = tk.Frame(drives_body, bg=CARD)
        self.drive_box.pack(fill="both", expand=True)

        quick_outer, quick_body = self._card(wrap, px(18), px(13))
        quick_outer.grid(row=1, column=1, sticky="nsew",
                         pady=(px(14), 0))
        self._label(quick_body, "快捷操作", 11, True).pack(anchor="w",
                                                          pady=(0, px(8)))
        grid = tk.Frame(quick_body, bg=CARD)
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_rowconfigure(0, weight=1)
        grid.grid_rowconfigure(1, weight=1)
        acts = [
            ("空间分析", lambda: self._show_page("analysis"), "soft"),
            ("软件搬家", lambda: self._show_page("appmove"), "ghost"),
            ("清空回收站", self.empty_recycle, "danger_soft"),
            ("操作日志", lambda: self._show_page("log"), "ghost"),
        ]
        for i, (text, cmd, kind) in enumerate(acts):
            b = PillButton(grid, text, cmd, kind=kind, size=9, height=32)
            b.grid(row=i // 2, column=i % 2, sticky="ew",
                   padx=(0, px(6)) if i % 2 == 0 else (0, 0),
                   pady=(0, px(6)) if i < 2 else (0, 0))

        recent_outer, recent = self._card(wrap, px(18), px(11))
        recent_outer.grid(row=2, column=0, columnspan=2, sticky="nsew",
                          pady=(px(14), 0))
        head = tk.Frame(recent, bg=CARD)
        head.pack(fill="x")
        self._label(head, "最近操作", 10, True).pack(side="left")
        PillButton(head, "查看全部", lambda: self._show_page("log"),
                   kind="ghost", size=8, height=24, padx=10).pack(
            side="right")
        self.recent_box = tk.Frame(recent, bg=CARD)
        self.recent_box.pack(fill="both", expand=True, pady=(px(5), 0))

    def _bind_click(self, widget, fn):
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        widget.bind("<Button-1>", lambda _e: fn())
        for child in widget.winfo_children():
            self._bind_click(child, fn)

    def _refresh_drives(self):
        if not hasattr(self, "drive_box"):
            return
        for w in self.drive_box.winfo_children():
            w.destroy()
        drives = core.list_drives()
        if not drives:
            self._label(self.drive_box, "未读取到本地磁盘。", 9,
                        fg=MUTED).pack(anchor="w")
            return
        sys_root = os.path.splitdrive(os.environ.get("SystemRoot", "C:\\"))[0]
        for d in drives:
            row = tk.Frame(self.drive_box, bg=CARD)
            row.pack(fill="x", pady=(0, px(7)))
            top = tk.Frame(row, bg=CARD)
            top.pack(fill="x")
            tk.Label(top, text=d["letter"], bg=CARD, fg=TEXT,
                     font=(FONT, 9, "bold")).pack(side="left")
            if d["letter"].upper() == sys_root.upper():
                tk.Label(top, text="系统盘", bg=CARD, fg=MUTED,
                         font=(FONT, 8)).pack(side="left", padx=(px(6), 0))
            tk.Label(top,
                     text=f"剩余 {core.fmt_size(d['free'])} / "
                          f"共 {core.fmt_size(d['total'])}",
                     bg=CARD, fg=MUTED, font=(FONT, 8)).pack(side="right")
            color = DANGER if d["pct"] >= 90 else (
                WARN if d["pct"] >= 75 else OK)
            m = Meter(row, width=300, height=5, bg=CARD)
            m.pack(fill="x", pady=(px(3), 0))
            m.set(d["pct"], color)

    def _refresh_disks(self):
        self._refresh_overview()
        self._refresh_drives()

    def _refresh_overview(self):
        drives = core.list_drives()
        cdrive = next((d for d in drives if d["letter"].upper() == "C:"),
                      drives[0] if drives else None)
        if cdrive:
            free = cdrive["free"]
            self.ov_free.configure(text=f"{free / (1024 ** 3):.1f}")
            self.ov_sub.configure(
                text=f"已用 {core.fmt_size(cdrive['used'])} / 共 "
                     f"{core.fmt_size(cdrive['total'])} · 使用率 "
                     f"{cdrive['pct']:.0f}%")
            color = DANGER if cdrive["pct"] >= 90 else (
                WARN if cdrive["pct"] >= 75 else OK)
            self.hero_meter.set(cdrive["pct"], color)
            self.top_disk_text.configure(
                text=f"剩余 {core.fmt_size(free)} / "
                     f"共 {core.fmt_size(cdrive['total'])}")
            self.top_disk_meter.set(cdrive["pct"], color)
        if self.junk_rows:
            junk = sum(r["size"] for r in self.junk_rows
                       if r["id"] != "recycle_bin" and not r["skipped"])
            admin_extra = sum(r["size"] for r in self.junk_rows
                              if r["id"] != "recycle_bin" and r["skipped"])
            recycle = next((r for r in self.junk_rows
                            if r["id"] == "recycle_bin"), None)
            self.ov_junk_val.configure(text=core.fmt_size(junk))
            if admin_extra:
                note = f"另有 {core.fmt_size(admin_extra)} 需管理员"
            else:
                note = "可再生缓存 / 临时文件"
            self.ov_junk_note.configure(text=note)
            self.ov_recycle_val.configure(
                text=core.fmt_size(recycle["size"]) if recycle else "0 B")
        else:
            self.ov_junk_val.configure(text="—")
            self.ov_recycle_val.configure(text="—")
        self._update_overview_hint(cdrive)
        self._refresh_recent()

    def _update_overview_hint(self, cdrive):
        if not hasattr(self, "ov_hint"):
            return
        try:
            hiber = core.hiberfil_size()
        except Exception:
            hiber = 0
        recycle = next((r for r in self.junk_rows
                        if r["id"] == "recycle_bin"), None)
        winold = next((r for r in self.junk_rows
                       if r["id"] == "windows_old"), None)
        admin_extra = sum(r["size"] for r in self.junk_rows
                          if r["id"] != "recycle_bin" and r["skipped"])
        available = sum(r["size"] for r in self.junk_rows
                        if r["id"] != "recycle_bin" and not r["skipped"])
        if cdrive and cdrive["pct"] >= 75 and hiber >= 1024 ** 3:
            text = f"关闭休眠可释放约 {core.fmt_size(hiber)}（系统工具）→"
        elif winold and winold["size"] > 0:
            text = f"旧系统 Windows.old 占用 {core.fmt_size(winold['size'])}，"                    "确认不回滚后可清理 →"
        elif recycle and recycle["size"] >= 100 * 1024 ** 2:
            text = f"回收站有 {core.fmt_size(recycle['size'])}，"                    "可手动清空（不可恢复）→"
        elif admin_extra > 0:
            text = f"以管理员重启可多清理 {core.fmt_size(admin_extra)} →"
        elif available > 0:
            text = f"推荐清理项合计 {core.fmt_size(available)}，点上方按钮 →"
        else:
            text = "C 盘空间状态良好，暂时没有明显的可清理项。"
        self.ov_hint.configure(text=text)

    def _refresh_recent(self):
        if not hasattr(self, "recent_box"):
            return
        for w in self.recent_box.winfo_children():
            w.destroy()
        lines = core.log_tail(3)
        if not lines:
            self._label(
                self.recent_box,
                "暂无操作记录。实际执行清理、搬移或卸载后，会显示在这里。",
                8, fg=MUTED).pack(anchor="w")
            return
        for line in lines:
            text = line.strip()
            if len(text) > 150:
                text = text[:147] + "…"
            tk.Label(self.recent_box, text=text, bg=CARD, fg="#5D6B82",
                     font=(MONO, 8), anchor="w",
                     justify="left").pack(fill="x")

    def smart_clean(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        if not self.junk_rows:
            messagebox.showinfo("Cpan", "正在扫描可清理内容，请稍等几秒再试。")
            return
        chosen = [r for r in self.junk_rows
                  if r.get("default") and not r["skipped"] and r["size"] > 0]
        if not chosen:
            messagebox.showinfo("Cpan", "没有发现可清理的推荐项。")
            return
        total = sum(r["size"] for r in chosen)
        names = "、".join(r["name"] for r in chosen[:7])
        if len(chosen) > 7:
            names += f" 等 {len(chosen)} 项"
        if not messagebox.askyesno(
                "一键智能清理",
                f"将清理以下可再生的临时/缓存文件：\n\n{names}\n\n"
                f"预计释放 {core.fmt_size(total)}。\n"
                "回收站不在推荐项中，不会被清空。\n\n继续吗？"):
            return
        self._clean_junk_ids([r["id"] for r in chosen])

    def empty_recycle(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        size, items = core.recycle_bin_stats()
        if not items:
            messagebox.showinfo("Cpan", "回收站已经是空的。")
            return
        if not messagebox.askyesno(
                "清空回收站",
                f"回收站中有 {items} 项，共 {core.fmt_size(size)}。\n\n"
                "清空后无法恢复。确定清空吗？"):
            return
        self._run_task(core.empty_recycle_bin, self._recycle_emptied,
                       label="正在清空回收站…", progress="indeterminate")

    def _recycle_emptied(self, result):
        ok, msg = result
        core.oplog("CLEAN", "回收站", "OK" if ok else f"FAIL({msg})")
        if ok:
            self._set_status("回收站已清空。", "ok")
            for r in self.junk_rows:
                if r["id"] == "recycle_bin":
                    r["size"], r["files"] = 0, 0
            self._junk_render()
            self._refresh_overview()
            self._refresh_drives()
            if self.current_page == "log":
                self.log_refresh()
        else:
            self._set_status(f"清空回收站失败：{msg}", "error")
            messagebox.showerror("Cpan", f"清空失败：{msg}")

    # --------------------------------------------------------------- junk
    def _build_junk(self):
        page = self._make_page("junk")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))

        summary_outer, summary = self._card(wrap, px(18), px(12))
        summary_outer.pack(fill="x")
        left = tk.Frame(summary, bg=CARD)
        left.pack(side="left")
        self._label(left, "可回收（当前权限 · 不含回收站）", 9,
                    fg=MUTED).pack(anchor="w")
        self.junk_total_lbl = tk.Label(left, text="—", bg=CARD, fg=TEXT,
                                       font=(FONT, 20, "bold"))
        self.junk_total_lbl.pack(anchor="w")
        self.junk_sel_lbl = self._label(left, "尚未扫描", 9, fg=MUTED)
        self.junk_sel_lbl.pack(anchor="w")
        rb = tk.Frame(summary, bg=CARD)
        rb.pack(side="right")
        PillButton(rb, "推荐选择", self._junk_recommend, kind="soft",
                   size=9, height=28, padx=11).pack(side="left")
        PillButton(rb, "全选", lambda: self._junk_set_all(True),
                   kind="ghost", size=9, height=28,
                   padx=11).pack(side="left", padx=(px(5), 0))
        PillButton(rb, "全不选", lambda: self._junk_set_all(False),
                   kind="ghost", size=9, height=28,
                   padx=11).pack(side="left", padx=(px(5), 0))
        PillButton(rb, "重新扫描", self.junk_scan, kind="ghost", size=9,
                   height=28, padx=11).pack(side="left", padx=(px(5), 0))

        table_card, self.junk_tree = self._table(wrap, [
            ("sel", "", 40, "center", False),
            ("name", "类别", 170, "w", False),
            ("size", "大小", 100, "e", False),
            ("files", "文件数", 76, "e", False),
            ("note", "说明 / 状态", 430, "w", True),
        ], height=6)
        table_card.pack(fill="both", expand=True, pady=(px(11), 0))
        self.junk_tree.bind("<ButtonRelease-1>", self._junk_toggle)
        self.junk_tree.bind("<Double-1>", self._junk_detail)
        self.junk_tree.bind("<space>", self._junk_space)

        foot_outer, foot = self._card(wrap, px(18), px(10))
        foot_outer.pack(fill="x", pady=(px(10), 0))
        self._label(foot,
                    "单击行切换勾选 · 双击查看清理路径 · ★ 为推荐项",
                    9, fg=MUTED).pack(side="left")
        self.junk_clean_btn = PillButton(foot, "清理选中", self.junk_clean,
                                         kind="danger", size=9, height=30)
        self.junk_clean_btn.pack(side="right")
        self.junk_clean_btn.set_enabled(False)

        tools_outer, tools = self._card(wrap, px(18), px(10))
        tools_outer.pack(fill="x", pady=(px(10), 0))
        tl = tk.Frame(tools, bg=CARD)
        tl.pack(side="left")
        self._label(tl, "系统工具", 10, True).pack(anchor="w")
        self.systools_note = self._label(
            tl, "DISM 组件清理与关闭休眠需要管理员权限", 8, fg=MUTED)
        self.systools_note.pack(anchor="w")
        tr = tk.Frame(tools, bg=CARD)
        tr.pack(side="right")
        PillButton(tr, "系统组件清理 (DISM)", self.dism_tool, kind="soft",
                   size=9, height=29, padx=12).pack(side="left")
        PillButton(tr, "关闭休眠释放空间", self.hibernate_tool, kind="ghost",
                   size=9, height=29, padx=12).pack(side="left",
                                                   padx=(px(7), 0))

    def junk_scan(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        self._placeholder(self.junk_tree, "正在扫描可清理内容…")
        self.junk_sel_lbl.configure(text="正在统计大小…")

        def work():
            def progress(idx, total, row):
                self.q.put(("progress", int(idx * 100 / max(1, total)),
                            f"扫描：{row['name']}（{idx}/{total}）"))
            return core.scan_junk(progress=progress)

        self._run_task(work, self._junk_scanned, label="正在扫描垃圾文件…",
                       progress="percent")

    def _junk_scanned(self, rows):
        self.junk_rows = rows
        for r in self.junk_rows:
            r["on"] = bool(r.get("default")) and not r["skipped"] \
                and r.get("size", 0) > 0
        self._junk_render()
        total = sum(r["size"] for r in rows
                    if r["id"] != "recycle_bin" and not r["skipped"])
        admin_extra = sum(r["size"] for r in rows
                          if r["id"] != "recycle_bin" and r["skipped"])
        msg = (f"扫描完成：当前权限可清理 {core.fmt_size(total)}"
               f"（不含回收站）")
        if admin_extra:
            msg += f"；另有 {core.fmt_size(admin_extra)} 需管理员"
        self._set_status(msg, "ok")
        self._refresh_overview()
        self._refresh_drives()
        if self.current_page == "log":
            self.log_refresh()

    def _junk_render(self):
        self.junk_tree.delete(*self.junk_tree.get_children())
        for i, r in enumerate(self.junk_rows):
            if r["skipped"]:
                tag = "warn"
                mark = BLOCKED
            elif r["size"] == 0:
                tag = "muted"
                mark = CHECK if r.get("on") else EMPTY
            else:
                tag = "odd" if i % 2 else ""
                mark = CHECK if r.get("on") else EMPTY
            name = ("★ " if r.get("default") else "") + r["name"]
            note = r["skipped"] or r["desc"]
            self.junk_tree.insert(
                "", "end", iid=r["id"], tags=(tag,) if tag else (),
                values=(mark, name, core.fmt_size(r["size"]),
                        f"{r['files']:,}", note))
        self._update_junk_summary()

    def _update_junk_summary(self):
        if not self.junk_rows:
            self.junk_total_lbl.configure(text="—")
            self.junk_sel_lbl.configure(text="尚未扫描")
            self.junk_clean_btn.set_enabled(False)
            return
        total = sum(r["size"] for r in self.junk_rows
                    if r["id"] != "recycle_bin" and not r["skipped"])
        admin_extra = sum(r["size"] for r in self.junk_rows
                          if r["id"] != "recycle_bin" and r["skipped"])
        chosen = [r for r in self.junk_rows
                  if r.get("on") and not r["skipped"]]
        sel = sum(r["size"] for r in chosen)
        self.junk_total_lbl.configure(text=core.fmt_size(total))
        sel_text = f"已选 {len(chosen)} 项 · {core.fmt_size(sel)}"
        if admin_extra:
            sel_text += f" · 另有 {core.fmt_size(admin_extra)} 需管理员"
        self.junk_sel_lbl.configure(text=sel_text)
        self.junk_clean_btn.set_text(
            f"清理选中（{len(chosen)} 项 · {core.fmt_size(sel)}）")
        self.junk_clean_btn.set_enabled(bool(chosen) and not self.busy)

    def _junk_toggle(self, event):
        if self.junk_tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.junk_tree.identify_row(event.y)
        if not iid or iid == "__placeholder__":
            return
        row = next((r for r in self.junk_rows if r["id"] == iid), None)
        if not row:
            return
        if row["skipped"]:
            self._require_admin("清理系统临时文件 / 更新缓存")
            return
        row["on"] = not row.get("on")
        self.junk_tree.set(iid, "sel", CHECK if row["on"] else EMPTY)
        self._update_junk_summary()

    def _junk_space(self, _event):
        iid = self.junk_tree.focus()
        if not iid or iid == "__placeholder__":
            return
        row = next((r for r in self.junk_rows if r["id"] == iid), None)
        if row and not row["skipped"]:
            row["on"] = not row.get("on")
            self._junk_render()

    def _junk_set_all(self, on: bool):
        for r in self.junk_rows:
            if not r["skipped"]:
                r["on"] = on and r["size"] > 0
        self._junk_render()

    def _junk_recommend(self):
        for r in self.junk_rows:
            if not r["skipped"]:
                r["on"] = bool(r.get("default")) and r["size"] > 0
        self._junk_render()

    def _junk_detail(self, event):
        iid = self.junk_tree.identify_row(event.y)
        if not iid or iid == "__placeholder__":
            return
        row = next((r for r in self.junk_rows if r["id"] == iid), None)
        if not row:
            return
        paths = row.get("paths") or []
        body = (f"类别：{row['name']}\n"
                f"大小：{core.fmt_size(row['size'])} · "
                f"文件数：{row['files']:,}\n"
                f"说明：{row['desc']}\n")
        if row["skipped"]:
            body += f"状态：{row['skipped']}\n"
        body += "\n清理路径：\n"
        body += "\n".join(paths) if paths else "（回收站通过系统 API 清空）"
        self._text_dialog("清理详情", row["name"], body,
                          open_path=paths[0] if paths else None)

    def junk_clean(self):
        chosen = [r for r in self.junk_rows
                  if r.get("on") and not r["skipped"]]
        if not chosen:
            messagebox.showinfo("Cpan", "请先勾选要清理的类别。")
            return
        total = sum(r["size"] for r in chosen)
        has_recycle = any(r["id"] == "recycle_bin" for r in chosen)
        names = "、".join(r["name"] for r in chosen[:8])
        if len(chosen) > 8:
            names += f" 等 {len(chosen)} 项"
        extra = "\n\n注意：回收站会被清空，清空后不可恢复。" if has_recycle else ""
        if not messagebox.askyesno(
                "确认清理",
                f"即将清理：\n\n{names}\n\n预计释放 {core.fmt_size(total)}。\n"
                "这些都是可再生的临时/缓存文件。" + extra + "\n\n继续吗？"):
            return
        self._clean_junk_ids([r["id"] for r in chosen])

    def _clean_junk_ids(self, ids):
        pcb = self._progress_cb()
        self._run_task(
            lambda: core.clean_junk(ids, confirm=True, progress=pcb),
            self._junk_cleaned, label="正在清理…", progress="percent")

    def _junk_cleaned(self, rep):
        self._set_status(
            f"清理完成：释放 {core.fmt_size(rep['bytes'])}，删除 "
            f"{rep['deleted']} 个文件，跳过 {rep['skipped']} 个。", "ok")
        if rep["bytes"] == 0 and rep["skipped"] > 0:
            messagebox.showwarning(
                "Cpan", "没有文件被删除：相关文件正在被程序占用。\n"
                        "请关闭浏览器等程序后重试。")
        else:
            messagebox.showinfo(
                "清理完成",
                f"释放空间：{core.fmt_size(rep['bytes'])}\n"
                f"删除文件：{rep['deleted']} 个\n"
                f"跳过文件：{rep['skipped']} 个（正在使用，属正常）")
        self._refresh_drives()
        self._refresh_overview()
        if self.current_page == "log":
            self.log_refresh()
        self.junk_scan()

    # --------------------------------------------------------- system tools
    def dism_tool(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        if not self._require_admin("系统组件清理"):
            return
        if not messagebox.askyesno(
                "系统组件清理 (DISM)",
                "将运行 Windows 自带的组件清理（StartComponentCleanup），"
                "清理被新版本取代的旧组件。\n\n"
                "· 通常可释放数 GB 空间\n"
                "· 可能需要 5–20 分钟，请勿关闭窗口\n"
                "· 不会删除已安装更新，也不使用 /ResetBase\n\n"
                "开始清理吗？"):
            return
        self._run_task(
            lambda: core.system_component_cleanup(confirm=True),
            self._dism_done, label="DISM 清理中，可能需要几分钟…",
            progress="indeterminate")

    def _dism_done(self, rep):
        if rep["ok"]:
            self._set_status("DISM 系统组件清理完成。", "ok")
            messagebox.showinfo("DISM 清理完成",
                                rep["note"] + "\n\n磁盘占用已刷新。")
        else:
            self._set_status(f"DISM 未完成：{rep['note']}", "error")
            self._text_dialog("DISM 清理未完成", rep["note"],
                              rep.get("output") or "没有更多输出。")
        self._refresh_drives()
        self._refresh_overview()
        if self.current_page == "log":
            self.log_refresh()

    def hibernate_tool(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        size = core.hiberfil_size()
        if size <= 0:
            messagebox.showinfo(
                "Cpan", "当前没有开启休眠（hiberfil.sys 不存在），无需关闭。")
            return
        if not self._require_admin("关闭休眠"):
            return
        if not messagebox.askyesno(
                "关闭休眠",
                f"休眠文件约 {core.fmt_size(size)}，关闭后可释放这部分空间。\n\n"
                "代价：会同时关闭休眠和快速启动，可随时在系统设置中重新开启。\n"
                "确定关闭休眠吗？"):
            return
        self._run_task(lambda: core.set_hibernation(False, confirm=True),
                       self._hibernate_done, label="正在关闭休眠…",
                       progress="indeterminate")

    def _hibernate_done(self, rep):
        if rep["ok"]:
            self._set_status("休眠已关闭，hiberfil.sys 已释放。", "ok")
            messagebox.showinfo("Cpan", rep["note"])
        else:
            self._set_status(f"关闭休眠失败：{rep['note']}", "error")
            messagebox.showerror("Cpan", rep["note"])
        self._refresh_drives()
        self._refresh_overview()
        if self.current_page == "log":
            self.log_refresh()

    # ---------------------------------------------------------- analysis
    def _build_analysis(self):
        page = self._make_page("analysis")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        form_outer, form = self._card(wrap, px(18), px(12))
        form_outer.pack(fill="x")
        row1 = tk.Frame(form, bg=CARD)
        row1.pack(fill="x")
        self._label(row1, "目录", 9, fg=MUTED).pack(side="left",
                                                   padx=(0, px(8)))
        self.sa_path = self._entry(row1, width=55)
        self.sa_path.pack(side="left", fill="x", expand=True, ipady=px(5))
        self.sa_path.insert(0, "C:\\")
        self.sa_path.bind("<Return>", lambda _e: self.sa_scan())
        self.sa_scan_btn = PillButton(row1, "开始分析", self.sa_scan,
                                      kind="primary", size=9, height=31)
        self.sa_scan_btn.pack(side="left", padx=(px(8), 0))
        self.sa_stop_btn = PillButton(row1, "停止", self.sa_stop,
                                      kind="danger_soft", size=9, height=31,
                                      padx=12)
        self.sa_stop_btn.pack(side="left", padx=(px(6), 0))
        self.sa_stop_btn.set_enabled(False)
        row2 = tk.Frame(form, bg=CARD)
        row2.pack(fill="x", pady=(px(8), 0))
        self._label(row2, "常用：", 8, fg=MUTED).pack(side="left")
        for text, path in (("用户目录", core.expand("%USERPROFILE%")),
                           ("下载", core.expand("%USERPROFILE%\\Downloads")),
                           ("C 盘", "C:\\"), ("D 盘", "D:\\")):
            PillButton(row2, text,
                       lambda p=path: self._sa_quick(p),
                       kind="ghost", size=8, height=24,
                       padx=10).pack(side="left", padx=(px(4), 0))
        PillButton(row2, "上一级", self.sa_up, kind="ghost", size=8,
                   height=24, padx=10).pack(side="right")
        PillButton(row2, "打开位置", self.sa_open, kind="ghost", size=8,
                   height=24, padx=10).pack(side="right",
                                            padx=(0, px(4)))

        self.sa_summary = self._label(wrap, "选择文件夹后点击「开始分析」。",
                                      9, fg=MUTED)
        self.sa_summary.pack(anchor="w", pady=(px(10), px(6)))
        table_card, self.sa_tree = self._table(wrap, [
            ("name", "名称", 320, "w", True),
            ("kind", "类型", 80, "w", False),
            ("size", "占用", 110, "e", False),
            ("pct", "占比", 190, "w", False),
        ], height=6)
        table_card.pack(fill="both", expand=True)
        self.sa_tree.bind("<Double-1>", self._sa_open_row)

    def _sa_quick(self, path):
        self.sa_path.delete(0, "end")
        self.sa_path.insert(0, path)
        self.sa_scan()

    def sa_scan(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        path = self.sa_path.get().strip()
        if not path or not os.path.isdir(path):
            messagebox.showinfo("Cpan", "请填写一个存在的文件夹路径。")
            return
        self.sa_tree.delete(*self.sa_tree.get_children())
        self._sa_items = []
        self._sa_paths = {}
        self.sa_summary.configure(text=f"正在统计：{path}")
        self.sa_scan_btn.set_enabled(False)
        self.sa_stop_btn.set_enabled(True)
        ev = threading.Event()
        self._cancel_ev = ev

        def begin(item):
            self.q.put(("ui", lambda it=dict(item): self._sa_begin(it)))
            self.q.put(("status", f"正在统计：{item['name']}", "info"))

        def done_item(item):
            self.q.put(("ui", lambda it=dict(item): self._sa_item(it)))

        def work():
            return core.scan_child_items(path, on_begin=begin,
                                         on_item=done_item,
                                         should_stop=ev.is_set)

        self._run_task(
            work,
            lambda items: self._sa_done(items, path, ev.is_set()),
            label=f"正在分析 {path} …", progress="indeterminate",
            on_error=lambda _e: self._sa_reset_buttons())

    def _sa_begin(self, item):
        if self.sa_tree.exists(item["path"]):
            return
        kind = "文件夹" if item["is_dir"] else "文件"
        self.sa_tree.insert("", "end", iid=item["path"],
                            values=(item["name"], kind, "统计中…", ""),
                            tags=("muted",))
        self.sa_summary.configure(
            text=f"正在统计：{item['name']}（已完成 "
                 f"{len(self.sa_tree.get_children())} 项）")

    def _sa_item(self, item):
        self._sa_paths[item["path"]] = item
        if not self.sa_tree.exists(item["path"]):
            kind = "文件夹" if item["is_dir"] else "文件"
            self.sa_tree.insert("", "end", iid=item["path"],
                                values=(item["name"], kind, "", ""))
        kind = {"dir": "文件夹", "junction": "联接", "file": "文件"}.get(
            item["kind"], "文件")
        self.sa_tree.set(item["path"], "size",
                         core.fmt_size(item["size"]))
        self.sa_tree.set(item["path"], "kind", kind)

    def _sa_done(self, items, path, cancelled):
        self._sa_items = items
        self._sa_reset_buttons()
        self.sa_tree.delete(*self.sa_tree.get_children())
        total = sum(i["size"] for i in items)
        for idx, item in enumerate(items):
            kind = {"dir": "文件夹", "junction": "联接", "file": "文件"}.get(
                item["kind"], "文件")
            pct = item["size"] / total * 100 if total else 0
            filled = int(round(pct / 100 * 12))
            bar = "█" * filled + "░" * (12 - filled)
            tag = "odd" if idx % 2 else ""
            self.sa_tree.insert(
                "", "end", iid=item["path"],
                tags=(tag,) if tag else (),
                values=(item["name"], kind, core.fmt_size(item["size"]),
                        f"{bar} {pct:5.1f}%"))
        state = "已停止，显示部分结果" if cancelled else "统计完成"
        self.sa_summary.configure(
            text=f"{state}：{path} · {len(items)} 项 · 合计 "
                 f"{core.fmt_size(total)}"
                 + ("（双击文件夹可继续下钻）" if not cancelled else ""))
        self._set_status(f"空间分析{state}：{core.fmt_size(total)}", "ok")

    def _sa_reset_buttons(self):
        self.sa_scan_btn.set_enabled(True)
        self.sa_stop_btn.set_enabled(False)
        self._cancel_ev = None

    def sa_stop(self):
        if self._cancel_ev:
            self._cancel_ev.set()
            self.sa_stop_btn.set_enabled(False)
            self._set_status("正在停止分析…", "warn")

    def sa_up(self):
        path = os.path.normpath(self.sa_path.get().strip())
        parent = os.path.dirname(path)
        if not parent or parent == path:
            messagebox.showinfo("Cpan", "已经到盘符根目录。")
            return
        self.sa_path.delete(0, "end")
        self.sa_path.insert(0, parent)
        self.sa_scan()

    def sa_open(self):
        path = self.sa_path.get().strip()
        if os.path.isdir(path):
            self._open_path(path)
        else:
            messagebox.showinfo("Cpan", "目录不存在。")

    def _sa_open_row(self, event):
        iid = self.sa_tree.identify_row(event.y)
        if not iid:
            return
        item = self._sa_paths.get(iid)
        if not item:
            return
        if item["kind"] == "junction":
            messagebox.showinfo(
                "Cpan", "这是一个目录联接（junction），为避免重复统计不展开。")
            return
        if item["is_dir"]:
            self.sa_path.delete(0, "end")
            self.sa_path.insert(0, item["path"])
            self.sa_scan()
        else:
            self._open_select(item["path"])

    # ---------------------------------------------------------- app move
    def _build_appmove(self):
        page = self._make_page("appmove")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        toolbar = tk.Frame(wrap, bg=BG)
        toolbar.pack(fill="x", pady=(0, px(8)))
        PillButton(toolbar, "刷新列表", self.am_refresh, kind="ghost",
                   size=9, height=30, padx=12).pack(side="left")
        PillButton(toolbar, "打开安装位置", self.am_open, kind="ghost",
                   size=9, height=30, padx=12).pack(side="left",
                                                    padx=(px(6), 0))
        PillButton(toolbar, "搬出选中软件", self.am_move, kind="primary",
                   size=9, height=30).pack(side="left", padx=(px(6), 0))
        search_box = tk.Frame(toolbar, bg=BG)
        search_box.pack(side="right")
        self._label(search_box, "搜索", 8, fg=MUTED).pack(side="left",
                                                         padx=(0, px(5)))
        self.am_query = tk.StringVar()
        self.am_query.trace_add("write", lambda *_: self._am_render())
        self._entry(search_box, self.am_query, width=22).pack(
            side="left", ipady=px(4))
        self.am_summary = self._label(wrap, "尚未加载。刷新后会自动统计占用。",
                                      9, fg=MUTED)
        self.am_summary.pack(anchor="w", pady=(0, px(7)))
        table_card, self.am_tree = self._table(wrap, [
            ("name", "软件名称", 250, "w", True),
            ("loc", "安装位置（C 盘）", 360, "w", True),
            ("size", "占用", 100, "e", False),
            ("publisher", "发布者", 180, "w", False),
        ], height=8)
        table_card.pack(fill="both", expand=True)
        self.am_tree.bind("<Double-1>", lambda _e: self.am_open())
        tip = self._label(
            wrap,
            "原理：目录整体搬走后，原路径保留 NTFS 目录联接，注册表与快捷方式"
            "无需修改。搬前请退出目标软件；杀毒/驱动类软件不建议搬。",
            8, fg=MUTED, justify="left", wraplength=px(850))
        tip.pack(anchor="w", pady=(px(8), 0))

    def am_refresh(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        self._am_loaded = False
        self._am_gen += 1
        self._am_sizes = {}
        self._placeholder(self.am_tree, "正在读取已安装程序…")
        self.am_summary.configure(text="正在读取注册表中的程序列表…")
        self._run_task(core.c_drive_apps, self._am_loaded_cb,
                       label="正在读取已安装程序…", progress="indeterminate")

    def _am_loaded_cb(self, items):
        self._am_loaded = True
        self._am_items = items
        self._am_sizes = {}
        self._am_gen += 1
        self._am_render()
        if items:
            self.am_summary.configure(text=f"共 {len(items)} 个可搬移软件，"
                                           "正在统计占用…")
            self._am_start_sizes()
        else:
            self.am_summary.configure(text="没有发现装在 C 盘且可搬移的软件。")

    def _am_start_sizes(self):
        gen = self._am_gen
        items = list(self._am_items)

        def worker():
            for idx, item in enumerate(items):
                if gen != self._am_gen:
                    return
                loc = item.get("install_location") or ""
                size = core.dir_size(loc) if os.path.isdir(loc) else 0
                self.q.put(("ui", lambda i=idx, s=size:
                            self._am_size_ready(gen, i, s)))

        threading.Thread(target=worker, daemon=True).start()

    def _am_size_ready(self, gen, idx, size):
        if gen != self._am_gen:
            return
        self._am_sizes[idx] = size
        iid = str(idx)
        if self.am_tree.exists(iid):
            self.am_tree.set(iid, "size", core.fmt_size(size))
        total = sum(self._am_sizes.values())
        done = len(self._am_sizes)
        self.am_summary.configure(
            text=f"共 {len(self._am_items)} 个 · 已统计 {done}/"
                 f"{len(self._am_items)} · 合计 {core.fmt_size(total)}")

    def _am_render(self):
        query = self.am_query.get().strip().lower() if hasattr(
            self, "am_query") else ""
        self.am_tree.delete(*self.am_tree.get_children())
        shown = 0
        for idx, item in enumerate(self._am_items):
            hay = f"{item['name']} {item['publisher']} " \
                  f"{item['install_location']}".lower()
            if query and query not in hay:
                continue
            size = self._am_sizes.get(idx)
            self.am_tree.insert(
                "", "end", iid=str(idx), tags=("odd",) if shown % 2 else (),
                values=(item["name"], item["install_location"],
                        core.fmt_size(size) if size is not None else "统计中…",
                        item["publisher"]))
            shown += 1
        if self._am_items and shown == 0:
            self._placeholder(self.am_tree, "没有匹配的软件。")

    def _am_selected(self):
        sel = self.am_tree.selection()
        if not sel:
            messagebox.showinfo("Cpan", "请先选中一个软件。")
            return None
        try:
            return self._am_items[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def am_open(self):
        item = self._am_selected()
        if item:
            self._open_path(item["install_location"])

    def am_move(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        item = self._am_selected()
        if not item:
            return
        src = item["install_location"]
        running = []
        try:
            self.configure(cursor="watch")
            self.update_idletasks()
            running = core.running_processes_under(src)
        except Exception:
            running = []
        finally:
            self.configure(cursor="")
        if running:
            names = "、".join(f"{p['name']}(PID {p['pid']})"
                             for p in running[:5])
            if not messagebox.askokcancel(
                    "软件仍在运行",
                    f"检测到该目录下有进程正在运行：\n\n{names}\n\n"
                    "运行中的软件会锁住文件，导致搬移失败或回滚。\n"
                    "建议先彻底退出（含托盘图标）再搬。\n\n仍要继续尝试吗？"):
                return
        dest = self._choose_folder("搬到哪个文件夹？")
        if not dest:
            return
        if dest.lower().startswith("c:\\"):
            if not messagebox.askyesno(
                    "目标仍在 C 盘",
                    "目标文件夹仍在 C 盘，搬移无法释放 C 盘空间。\n"
                    "仍然继续吗？"):
                return
        size = self._am_sizes.get(
            self._am_items.index(item), 0)
        size_text = core.fmt_size(size) if size else "未知"
        final = os.path.join(dest, os.path.basename(src))
        if not messagebox.askyesno(
                "确认搬出软件",
                f"{item['name']}\n\n{src}\n  ↓ 搬到\n{final}\n\n"
                f"占用：{size_text}\n"
                "原位置会自动建立目录联接，注册表/快捷方式不用改。\n\n"
                "确认该软件已经关闭，开始搬移吗？"):
            return
        pcb = self._progress_cb()
        self._run_task(lambda: core.move_app(src, dest, confirm=True,
                                             progress=pcb),
                       self._am_moved, label="正在搬移软件…",
                       progress="percent")

    def _am_moved(self, rep):
        if rep["ok"]:
            self._set_status("软件搬家成功，联接已生效。", "ok")
            messagebox.showinfo(
                "搬移成功",
                f"{rep['note']}\n\n新位置：{rep['dst']}\n"
                f"释放：{core.fmt_size(rep['size'])}")
        else:
            self._set_status(f"软件搬家未完成：{rep['note']}", "warn")
            messagebox.showwarning("搬移未完成", rep["note"])
        self._refresh_drives()
        self._refresh_overview()
        if self.current_page == "log":
            self.log_refresh()
        self.am_refresh()

    # -------------------------------------------------------------- move
    def _build_move(self):
        page = self._make_page("move")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        form_outer, form = self._card(wrap, px(20), px(16))
        form_outer.pack(fill="x")
        form.grid_columnconfigure(1, weight=1)
        self._label(form, "源路径", 9, fg=MUTED).grid(
            row=0, column=0, sticky="e", padx=(0, px(10)), pady=px(6))
        self.mv_src = self._entry(form, width=58)
        self.mv_src.grid(row=0, column=1, sticky="ew", ipady=px(5),
                         pady=px(6))
        PillButton(form, "选文件夹",
                   lambda: self._pick_dir(self.mv_src), kind="ghost",
                   size=9, height=30, padx=12).grid(row=0, column=2,
                                                    padx=(px(7), 0))
        PillButton(form, "选文件",
                   lambda: self._pick_file(self.mv_src), kind="ghost",
                   size=9, height=30, padx=12).grid(row=0, column=3,
                                                    padx=(px(6), 0))
        self._label(form, "目标文件夹", 9, fg=MUTED).grid(
            row=1, column=0, sticky="e", padx=(0, px(10)), pady=px(6))
        self.mv_dst = self._entry(form, width=58)
        self.mv_dst.grid(row=1, column=1, sticky="ew", ipady=px(5),
                         pady=px(6))
        self.mv_dst.insert(0, self._default_dest())
        PillButton(form, "选择",
                   lambda: self._pick_dir(self.mv_dst), kind="ghost",
                   size=9, height=30, padx=12).grid(row=1, column=2,
                                                    padx=(px(7), 0))
        btns = tk.Frame(form, bg=CARD)
        btns.grid(row=2, column=1, columnspan=3, sticky="w",
                 pady=(px(8), 0))
        PillButton(btns, "预览", self.mv_preview, kind="soft",
                   size=9, height=32).pack(side="left")
        PillButton(btns, "开始搬移", self.mv_do, kind="primary",
                   size=9, height=32).pack(side="left", padx=(px(8), 0))

        quick = tk.Frame(form, bg=CARD)
        quick.grid(row=3, column=1, columnspan=3, sticky="w",
                 pady=(px(9), 0))
        self._label(quick, "常用来源：", 8, fg=MUTED).pack(side="left")
        home = core.expand("%USERPROFILE%")
        sources = [
            ("下载", os.path.join(home, "Downloads")),
            ("桌面", os.path.join(home, "Desktop")),
            ("文档", os.path.join(home, "Documents")),
            ("微信文件", os.path.join(home, "Documents", "xwechat_files")),
            ("旧版微信", os.path.join(home, "Documents", "WeChat Files")),
        ]
        for text, path in sources:
            if not os.path.isdir(path):
                continue
            PillButton(quick, text, lambda p=path: self._mv_use(p),
                       kind="ghost", size=8, height=24,
                       padx=10).pack(side="left", padx=(px(4), 0))

        prev_outer, prev = self._card(wrap, px(20), px(14))
        prev_outer.pack(fill="x", pady=(px(12), 0))
        self._label(prev, "预览结果", 10, True).pack(anchor="w")
        self.mv_preview_lbl = self._label(
            prev, "填写源和目标后点「预览」，可先查看大小与目标盘空间。",
            9, fg=MUTED, justify="left", wraplength=px(860))
        self.mv_preview_lbl.pack(anchor="w", pady=(px(6), 0))

        tips_outer, tips = self._card(wrap, px(20), px(14))
        tips_outer.pack(fill="x", pady=(px(12), 0))
        self._label(tips, "安全说明", 10, True).pack(anchor="w")
        self._label(
            tips,
            "· 跨盘搬移 = 复制 + 删除，完成后自动校验字节数；复制不完整时源目录保持不动。\n"
            "· 系统目录、盘符根目录、用户目录根目录一律拒绝搬移。\n"
            "· 微信 / QQ 文件目录搬走后，请到软件设置里把文件保存位置指向新目录。",
            9, fg=MUTED, justify="left",
            wraplength=px(860)).pack(anchor="w", pady=(px(6), 0))

    def _mv_use(self, path):
        self.mv_src.delete(0, "end")
        self.mv_src.insert(0, path)

    def mv_preview(self):
        src = self.mv_src.get().strip()
        dst = self.mv_dst.get().strip()
        if not src or not dst:
            messagebox.showinfo("Cpan", "请先填写源路径和目标文件夹。")
            return
        self.mv_preview_lbl.configure(text="正在计算大小…", fg=MUTED)
        self._run_task(
            lambda: core.move_path(src, dst, confirm=False),
            self._mv_previewed, label="正在计算大小并检查目标空间…",
            progress="indeterminate")

    def _mv_previewed(self, rep):
        note = rep["note"]
        if "dry-run" in note:
            text = (f"可以搬移\n源：{rep['src']}\n目标：{rep['dst']}\n"
                    f"大小：{core.fmt_size(rep['size'])}\n"
                    "点击「开始搬移」执行；完成后会自动校验大小。")
            color = OK
        else:
            text = f"暂不能搬移：{note}"
            color = WARN
        self.mv_preview_lbl.configure(text=text, fg=color)
        self._set_status(note, "ok" if color == OK else "warn")

    def mv_do(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        src = self.mv_src.get().strip()
        dst = self.mv_dst.get().strip()
        if not src or not dst:
            messagebox.showinfo("Cpan", "请先填写源路径和目标文件夹。")
            return
        if not messagebox.askyesno(
                "确认搬移",
                f"把\n{src}\n搬到\n{dst}\n\n"
                "搬移失败不会删除源数据，完成后会校验大小。继续吗？"):
            return
        pcb = self._progress_cb()
        self._run_task(
            lambda: core.move_path(src, dst, confirm=True, progress=pcb),
            self._moved, label="正在搬移…", progress="percent")

    def _moved(self, rep):
        if rep["ok"]:
            self._set_status("文件搬家完成，大小校验一致。", "ok")
            messagebox.showinfo("搬移完成",
                                f"已搬移到：\n{rep['dst']}\n\n"
                                f"大小：{core.fmt_size(rep['size'])}（已校验）")
        else:
            self._set_status(f"文件搬家未完成：{rep['note']}", "warn")
            messagebox.showwarning("搬移未完成", rep["note"])
        self._refresh_drives()
        self._refresh_overview()
        if self.current_page == "log":
            self.log_refresh()

    # ------------------------------------------------------------ custom
    def _build_custom(self):
        page = self._make_page("custom")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        form_outer, form = self._card(wrap, px(18), px(13))
        form_outer.pack(fill="x")
        row1 = tk.Frame(form, bg=CARD)
        row1.pack(fill="x")
        self._label(row1, "目录", 9, fg=MUTED).pack(side="left",
                                                   padx=(0, px(8)))
        self.cu_path = self._entry(row1, width=50)
        self.cu_path.pack(side="left", fill="x", expand=True, ipady=px(5))
        self.cu_path.insert(0, core.expand("%USERPROFILE%\\Downloads"))
        PillButton(row1, "浏览", lambda: self._pick_dir(self.cu_path),
                   kind="ghost", size=9, height=30, padx=12).pack(
            side="left", padx=(px(7), 0))
        PillButton(row1, "扫描", self.custom_scan, kind="primary",
                   size=9, height=30).pack(side="left", padx=(px(7), 0))
        row2 = tk.Frame(form, bg=CARD)
        row2.pack(fill="x", pady=(px(9), 0))
        self._label(row2, "扩展名", 9, fg=MUTED).pack(side="left")
        self.cu_ext = self._entry(row2, width=24)
        self.cu_ext.pack(side="left", ipady=px(4), padx=(px(6), px(14)))
        self.cu_ext.insert(0, ".tmp, .log, .bak")
        self._label(row2, "最小体积(MB)", 9, fg=MUTED).pack(side="left")
        self.cu_min = self._entry(row2, width=7)
        self.cu_min.pack(side="left", ipady=px(4), padx=(px(6), px(14)))
        self.cu_min.insert(0, "0")
        self._label(row2, "早于(天)", 9, fg=MUTED).pack(side="left")
        self.cu_days = self._entry(row2, width=7)
        self.cu_days.pack(side="left", ipady=px(4), padx=(px(6), 0))
        self.cu_days.insert(0, "0")
        row3 = tk.Frame(form, bg=CARD)
        row3.pack(fill="x", pady=(px(8), 0))
        self._label(row3, "快捷位置：", 8, fg=MUTED).pack(side="left")
        for text, path in (("下载", "%USERPROFILE%\\Downloads"),
                           ("桌面", "%USERPROFILE%\\Desktop"),
                           ("文档", "%USERPROFILE%\\Documents")):
            PillButton(row3, text,
                       lambda p=path: self._cu_quick(p), kind="ghost",
                       size=8, height=24, padx=10).pack(side="left",
                                                        padx=(px(4), 0))
        self._label(row3, "条件可组合；删除一律进回收站，可恢复。",
                    8, fg=MUTED).pack(side="right")

        toolbar = tk.Frame(wrap, bg=BG)
        toolbar.pack(fill="x", pady=(px(11), px(7)))
        self.cu_summary = self._label(toolbar, "尚未扫描", 9, fg=MUTED)
        self.cu_summary.pack(side="left")
        self.cu_delete_btn = PillButton(toolbar, "移入回收站", self.cu_delete,
                                        kind="danger", size=9, height=29)
        self.cu_delete_btn.pack(side="right")
        self.cu_delete_btn.set_enabled(False)
        PillButton(toolbar, "全选", self._cu_select_all, kind="ghost",
                   size=9, height=29, padx=11).pack(side="right",
                                                    padx=(0, px(6)))
        search = tk.Frame(toolbar, bg=BG)
        search.pack(side="right", padx=(0, px(14)))
        self.cu_query = tk.StringVar()
        self.cu_query.trace_add("write", lambda *_: self._cu_render())
        self._label(search, "搜索", 8, fg=MUTED).pack(side="left",
                                                     padx=(0, px(4)))
        self._entry(search, self.cu_query, width=18).pack(side="left",
                                                          ipady=px(3))

        table_card, self.cu_tree = self._table(wrap, [
            ("path", "文件", 600, "w", True),
            ("size", "大小", 110, "e", False),
            ("mtime", "修改日期", 110, "center", False),
        ], height=7, selectmode="extended")
        table_card.pack(fill="both", expand=True)
        self.cu_tree.bind("<<TreeviewSelect>>", self._cu_selection)
        self.cu_tree.bind("<Double-1>", self._cu_open_row)

    def _cu_quick(self, path):
        self.cu_path.delete(0, "end")
        self.cu_path.insert(0, core.expand(path))

    def custom_scan(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        exts = [e.strip() for e in self.cu_ext.get().split(",") if e.strip()]
        try:
            min_mb = float(self.cu_min.get() or 0)
            days = int(self.cu_days.get() or 0)
            path = self.cu_path.get().strip()
        except ValueError:
            messagebox.showerror("Cpan", "最小体积 / 天数必须是数字。")
            return
        self._placeholder(self.cu_tree, "正在按规则扫描…")
        self.cu_summary.configure(text="正在扫描…")
        self.cu_delete_btn.set_enabled(False)
        self._run_task(
            lambda: core.scan_custom(path, exts, min_mb, days),
            self._cu_scanned, label="正在按规则扫描文件…",
            progress="indeterminate")

    def _cu_scanned(self, hits):
        self.cu_hits = hits
        self._cu_render()
        total = sum(h["size"] for h in hits)
        self.cu_summary.configure(
            text=f"共 {len(hits)} 个文件 · {core.fmt_size(total)} · "
                 "删除会移入回收站")
        self._set_status(f"自定义扫描完成：{len(hits)} 个文件，"
                         f"{core.fmt_size(total)}", "ok")
        self._cu_selection()

    def _cu_render(self):
        if not hasattr(self, "cu_tree"):
            return
        query = self.cu_query.get().strip().lower()
        self.cu_tree.delete(*self.cu_tree.get_children())
        shown = 0
        for idx, h in enumerate(self.cu_hits):
            if query and query not in h["path"].lower():
                continue
            self.cu_tree.insert(
                "", "end", iid=str(idx), tags=("odd",) if shown % 2 else (),
                values=(h["path"], core.fmt_size(h["size"]), h["mtime"]))
            shown += 1
        if self.cu_hits and shown == 0:
            self._placeholder(self.cu_tree, "没有匹配的文件。")
        self._cu_selection()

    def _cu_selected_hits(self):
        out = []
        for iid in self.cu_tree.selection():
            try:
                out.append(self.cu_hits[int(iid)])
            except (ValueError, IndexError):
                continue
        return out

    def _cu_selection(self, _event=None):
        hits = self._cu_selected_hits()
        total = sum(h["size"] for h in hits)
        if hits:
            self.cu_summary.configure(
                text=f"已选 {len(hits)} 个 · {core.fmt_size(total)}")
        elif self.cu_hits:
            self.cu_summary.configure(
                text=f"共 {len(self.cu_hits)} 个文件 · "
                     f"{core.fmt_size(sum(h['size'] for h in self.cu_hits))} · "
                     "选择后可移入回收站")
        self.cu_delete_btn.set_enabled(bool(hits))
        self.cu_delete_btn.set_text(
            f"移入回收站（{len(hits)} 项）" if hits else "移入回收站")

    def _cu_select_all(self):
        self.cu_tree.selection_set(self.cu_tree.get_children())
        self._cu_selection()

    def _cu_open_row(self, event):
        iid = self.cu_tree.identify_row(event.y)
        if not iid:
            return
        try:
            self._open_select(self.cu_hits[int(iid)]["path"])
        except (ValueError, IndexError):
            pass

    def cu_delete(self):
        hits = self._cu_selected_hits()
        if not hits:
            messagebox.showinfo("Cpan", "请先选择要删除的文件。")
            return
        total = sum(h["size"] for h in hits)
        if not messagebox.askyesno(
                "移入回收站",
                f"把 {len(hits)} 个文件（{core.fmt_size(total)}）"
                "移入回收站？\n之后可随时恢复。"):
            return
        pcb = self._progress_cb()
        self._run_task(
            lambda: core.delete_custom([h["path"] for h in hits],
                                       confirm=True, progress=pcb),
            self._cu_deleted, label="正在移入回收站…", progress="percent")

    def _cu_deleted(self, rep):
        self._set_status(f"已移入回收站：{rep['ok']} 项，"
                         f"{core.fmt_size(rep['bytes'])}", "ok")
        if rep["failed"]:
            messagebox.showwarning(
                "部分未完成",
                "\n".join(rep["failed"][:8]))
        self.custom_scan()

    # ----------------------------------------------------------- uninstall
    def _build_uninstall(self):
        page = self._make_page("uninstall")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        toolbar = tk.Frame(wrap, bg=BG)
        toolbar.pack(fill="x", pady=(0, px(8)))
        PillButton(toolbar, "刷新列表", self.un_load, kind="ghost",
                   size=9, height=30, padx=12).pack(side="left")
        PillButton(toolbar, "卸载选中", self.un_uninstall, kind="danger",
                   size=9, height=30).pack(side="left", padx=(px(6), 0))
        search = tk.Frame(toolbar, bg=BG)
        search.pack(side="right")
        self.un_query = tk.StringVar()
        self.un_query.trace_add("write", lambda *_: self._un_render())
        self._label(search, "搜索", 8, fg=MUTED).pack(side="left",
                                                     padx=(0, px(4)))
        self._entry(search, self.un_query, width=22).pack(side="left",
                                                          ipady=px(4))
        self.un_summary = self._label(wrap, "尚未加载。", 9, fg=MUTED)
        self.un_summary.pack(anchor="w", pady=(0, px(7)))
        table_card, self.un_tree = self._table(wrap, [
            ("name", "软件名称", 280, "w", True),
            ("publisher", "发布者", 200, "w", True),
            ("size", "大小", 90, "e", False),
            ("date", "安装日期", 115, "center", False),
        ], height=8)
        table_card.pack(fill="both", expand=True)
        for col in ("name", "publisher", "size", "date"):
            self.un_tree.heading(col, command=lambda c=col: self._un_sort(c))
        self.un_tree.bind("<Double-1>", self._un_detail)

    def un_load(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        self._placeholder(self.un_tree, "正在读取已安装程序…")
        self.un_summary.configure(text="正在读取…")
        self._run_task(core.list_installed, self._un_loaded_cb,
                       label="正在读取已安装程序…", progress="indeterminate")

    def _un_loaded_cb(self, items):
        self._un_loaded = True
        self._un_items = items
        self._un_render()

    def _un_sort(self, col):
        if self._un_sort_col == col:
            self._un_sort_rev = not self._un_sort_rev
        else:
            self._un_sort_col = col
            # Size/date are most useful largest/newest first.
            self._un_sort_rev = col in ("size", "date")
        self._un_render()

    def _un_render(self):
        if not hasattr(self, "un_tree"):
            return
        titles = {"name": "软件名称", "publisher": "发布者",
                  "size": "大小", "date": "安装日期"}
        for col, title in titles.items():
            arrow = ""
            if col == self._un_sort_col:
                arrow = " ↓" if self._un_sort_rev else " ↑"
            self.un_tree.heading(col, text=title + arrow)
        query = self.un_query.get().strip().lower()
        items = [it for it in self._un_items
                 if not query or query in
                 f"{it['name']} {it['publisher']}".lower()]

        def key(it):
            if self._un_sort_col == "size":
                return it["size_kb"]
            if self._un_sort_col == "date":
                return it["install_date"]
            if self._un_sort_col == "publisher":
                return it["publisher"].lower()
            return it["name"].lower()

        items.sort(key=key, reverse=self._un_sort_rev)
        self.un_tree.delete(*self.un_tree.get_children())
        for i, it in enumerate(items):
            size = core.fmt_size(it["size_kb"] * 1024) if it["size_kb"] else "?"
            d = it["install_date"]
            if len(d) == 8 and d.isdigit():
                d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            self.un_tree.insert(
                "", "end", iid=str(i), tags=("odd",) if i % 2 else (),
                values=(it["name"], it["publisher"], size, d))
        self._un_view = items
        total = len(self._un_items)
        self.un_summary.configure(
            text=f"共 {total} 个程序" +
                 (f"，显示 {len(items)} 个" if query else "") +
                 " · 双击查看详情")
        if total and not items:
            self._placeholder(self.un_tree, "没有匹配的程序。")

    def un_uninstall(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        sel = self.un_tree.selection()
        if not sel:
            messagebox.showinfo("Cpan", "请先选中要卸载的软件。")
            return
        try:
            item = self._un_view[int(sel[0])]
        except (ValueError, IndexError, AttributeError):
            return
        if not messagebox.askyesno(
                "确认卸载",
                f"卸载「{item['name']}」？\n\n"
                "将启动该软件自带的官方卸载器，可能弹出卸载界面或 UAC。\n"
                "Cpan 不修改注册表。"):
            return
        self._run_task(
            lambda: core.uninstall_program(item, confirm=True),
            self._un_done, label=f"等待「{item['name']}」卸载完成…",
            progress="indeterminate")

    def _un_done(self, rep):
        self._set_status(f"卸载「{rep['name']}」：{rep['note']}",
                         "ok" if rep["ok"] else "warn")
        messagebox.showinfo("卸载结束",
                            f"{rep['name']}\n{rep['note']}")
        if self.current_page == "log":
            self.log_refresh()
        self.un_load()

    def _un_detail(self, event):
        iid = self.un_tree.identify_row(event.y)
        if not iid:
            return
        try:
            it = self._un_view[int(iid)]
        except (ValueError, IndexError, AttributeError):
            return
        body = (f"名称：{it['name']}\n"
                f"发布者：{it['publisher'] or '（未提供）'}\n"
                f"版本：{it['version'] or '（未提供）'}\n"
                f"估计大小："
                f"{core.fmt_size(it['size_kb'] * 1024) if it['size_kb'] else '未知'}\n"
                f"安装日期：{it['install_date'] or '（未提供）'}\n"
                f"安装位置：{it['install_location'] or '（未登记）'}\n\n"
                f"卸载命令：\n{it['uninstall']}\n")
        self._text_dialog("程序详情", it["name"], body,
                          open_path=it["install_location"] or None)

    # ----------------------------------------------------------- big files
    def _build_big(self):
        page = self._make_page("big")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        form_outer, form = self._card(wrap, px(18), px(12))
        form_outer.pack(fill="x")
        row = tk.Frame(form, bg=CARD)
        row.pack(fill="x")
        self._label(row, "目录", 9, fg=MUTED).pack(side="left",
                                                  padx=(0, px(8)))
        self.bf_dir = self._entry(row, width=44)
        self.bf_dir.pack(side="left", fill="x", expand=True, ipady=px(5))
        self.bf_dir.insert(0, core.expand("%USERPROFILE%"))
        PillButton(row, "浏览", lambda: self._pick_dir(self.bf_dir),
                   kind="ghost", size=9, height=30, padx=12).pack(
            side="left", padx=(px(7), 0))
        self._label(row, "≥ MB", 9, fg=MUTED).pack(side="left",
                                                   padx=(px(10), px(5)))
        self.bf_min = self._entry(row, width=7)
        self.bf_min.pack(side="left", ipady=px(5))
        self.bf_min.insert(0, "500")
        self.bf_scan_btn = PillButton(row, "扫描", self.big_scan,
                                      kind="primary", size=9, height=30)
        self.bf_scan_btn.pack(side="left", padx=(px(8), 0))
        self.bf_stop_btn = PillButton(row, "停止", self.big_stop,
                                      kind="danger_soft", size=9, height=30,
                                      padx=12)
        self.bf_stop_btn.pack(side="left", padx=(px(5), 0))
        self.bf_stop_btn.set_enabled(False)

        toolbar = tk.Frame(wrap, bg=BG)
        toolbar.pack(fill="x", pady=(px(10), px(7)))
        self.bf_summary = self._label(toolbar, "尚未扫描", 9, fg=MUTED)
        self.bf_summary.pack(side="left")
        PillButton(toolbar, "打开位置", self.bf_open, kind="ghost",
                   size=9, height=29, padx=11).pack(side="right")
        PillButton(toolbar, "移入回收站", self.bf_recycle, kind="danger",
                   size=9, height=29).pack(side="right", padx=(0, px(6)))
        PillButton(toolbar, "搬走选中", self.bf_move, kind="soft",
                   size=9, height=29).pack(side="right", padx=(0, px(6)))
        search = tk.Frame(toolbar, bg=BG)
        search.pack(side="right", padx=(0, px(12)))
        self.bf_query = tk.StringVar()
        self.bf_query.trace_add("write", lambda *_: self._bf_render())
        self._label(search, "搜索", 8, fg=MUTED).pack(side="left",
                                                     padx=(0, px(4)))
        self._entry(search, self.bf_query, width=16).pack(side="left",
                                                          ipady=px(3))

        table_card, self.bf_tree = self._table(wrap, [
            ("path", "文件", 700, "w", True),
            ("size", "大小", 120, "e", False),
        ], height=8, selectmode="extended")
        table_card.pack(fill="both", expand=True)
        self.bf_tree.bind("<<TreeviewSelect>>", self._bf_selection)
        self.bf_tree.bind("<Double-1>", self._bf_open_row)

    def big_scan(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        path = self.bf_dir.get().strip()
        try:
            min_mb = float(self.bf_min.get() or 500)
        except ValueError:
            messagebox.showerror("Cpan", "最小体积必须是数字。")
            return
        if not os.path.isdir(path):
            messagebox.showinfo("Cpan", "请填写一个存在的文件夹。")
            return
        self._placeholder(self.bf_tree, "正在扫描大文件…")
        self.bf_summary.configure(text="正在扫描…")
        self.bf_scan_btn.set_enabled(False)
        self.bf_stop_btn.set_enabled(True)
        ev = threading.Event()
        self._cancel_ev = ev

        def progress(seen, dirpath):
            self.q.put(("status", f"已扫描 {seen:,} 个文件…", "info"))

        def work():
            return core.find_big_files(path, min_mb, 80,
                                       progress=progress,
                                       should_stop=ev.is_set)

        self._run_task(work,
                       lambda hits: self._bf_scanned(hits, ev.is_set()),
                       label=f"正在扫描 {path} 中的大文件…",
                       progress="indeterminate",
                       on_error=lambda _e: self._bf_reset_buttons())

    def _bf_scanned(self, hits, cancelled):
        self.big_hits = hits
        self._bf_reset_buttons()
        self._bf_render()
        total = sum(h["size"] for h in hits)
        self.bf_summary.configure(
            text=f"{'已停止，显示部分结果' if cancelled else '扫描完成'}："
                 f"{len(hits)} 个 ≥ 阈值 · 合计 {core.fmt_size(total)}")
        self._set_status(f"大文件扫描完成：{len(hits)} 个，"
                         f"{core.fmt_size(total)}", "ok")
        self._bf_selection()

    def _bf_reset_buttons(self):
        self.bf_scan_btn.set_enabled(True)
        self.bf_stop_btn.set_enabled(False)
        self._cancel_ev = None

    def big_stop(self):
        if self._cancel_ev:
            self._cancel_ev.set()
            self.bf_stop_btn.set_enabled(False)
            self._set_status("正在停止扫描…", "warn")

    def _bf_render(self):
        if not hasattr(self, "bf_tree"):
            return
        query = self.bf_query.get().strip().lower()
        self.bf_tree.delete(*self.bf_tree.get_children())
        shown = 0
        for idx, h in enumerate(self.big_hits):
            if query and query not in h["path"].lower():
                continue
            self.bf_tree.insert(
                "", "end", iid=str(idx), tags=("odd",) if shown % 2 else (),
                values=(h["path"], core.fmt_size(h["size"])))
            shown += 1
        if self.big_hits and not shown:
            self._placeholder(self.bf_tree, "没有匹配的文件。")
        self._bf_selection()

    def _bf_selected_hits(self):
        out = []
        for iid in self.bf_tree.selection():
            try:
                out.append(self.big_hits[int(iid)])
            except (ValueError, IndexError):
                continue
        return out

    def _bf_selection(self, _event=None):
        hits = self._bf_selected_hits()
        if hits:
            self.bf_summary.configure(
                text=f"已选 {len(hits)} 项 · "
                     f"{core.fmt_size(sum(h['size'] for h in hits))}")
        elif self.big_hits:
            self.bf_summary.configure(
                text=f"{len(self.big_hits)} 个文件 · "
                     f"{core.fmt_size(sum(h['size'] for h in self.big_hits))}")

    def bf_open(self):
        hits = self._bf_selected_hits()
        if not hits:
            messagebox.showinfo("Cpan", "请先选中一个文件。")
            return
        self._open_select(hits[0]["path"])

    def _bf_open_row(self, event):
        iid = self.bf_tree.identify_row(event.y)
        if iid:
            try:
                self._open_select(self.big_hits[int(iid)]["path"])
            except (ValueError, IndexError):
                pass

    def bf_move(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        hits = self._bf_selected_hits()
        if len(hits) != 1:
            messagebox.showinfo("Cpan", "请选中一个文件再搬。")
            return
        hit = hits[0]
        dest = self._choose_folder("搬到哪个文件夹？")
        if not dest:
            return
        if not messagebox.askyesno(
                "确认搬移",
                f"{hit['path']}\n  ↓ 搬到\n{dest}\n\n"
                f"大小：{core.fmt_size(hit['size'])}。继续吗？"):
            return
        pcb = self._progress_cb()
        self._run_task(
            lambda: core.move_path(hit["path"], dest, confirm=True,
                                   progress=pcb),
            lambda rep: self._bf_moved(rep, hit["path"]),
            label="正在搬移大文件…", progress="percent")

    def _bf_moved(self, rep, path):
        if rep["ok"]:
            self.big_hits = [h for h in self.big_hits if h["path"] != path]
            self._bf_render()
            self._set_status("大文件搬移完成。", "ok")
            messagebox.showinfo("搬移完成", f"已搬移到：\n{rep['dst']}")
            self._refresh_drives()
            self._refresh_overview()
        else:
            self._set_status(f"搬移未完成：{rep['note']}", "warn")
            messagebox.showwarning("搬移未完成", rep["note"])

    def bf_recycle(self):
        if self.busy:
            self._set_status("有任务正在进行，请稍候…", "warn")
            return
        hits = self._bf_selected_hits()
        if not hits:
            messagebox.showinfo("Cpan", "请先选中文件。")
            return
        total = sum(h["size"] for h in hits)
        if not messagebox.askyesno(
                "移入回收站",
                f"把 {len(hits)} 项（{core.fmt_size(total)}）移入回收站？\n"
                "之后可以从回收站恢复。"):
            return
        paths = {h["path"] for h in hits}
        pcb = self._progress_cb()
        self._run_task(
            lambda: core.delete_custom([h["path"] for h in hits],
                                       confirm=True, progress=pcb),
            lambda rep: self._bf_recycled(rep, paths),
            label="正在移入回收站…", progress="percent")

    def _bf_recycled(self, rep, paths):
        self.big_hits = [h for h in self.big_hits if h["path"] not in paths]
        self._bf_render()
        self._set_status(f"已移入回收站：{rep['ok']} 项，"
                         f"{core.fmt_size(rep['bytes'])}", "ok")
        if rep["failed"]:
            messagebox.showwarning("部分未完成",
                                   "\n".join(rep["failed"][:8]))
        if self.current_page == "log":
            self.log_refresh()

    # ---------------------------------------------------------------- log
    def _build_log(self):
        page = self._make_page("log")
        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=px(26), pady=px(16))
        toolbar = tk.Frame(wrap, bg=BG)
        toolbar.pack(fill="x", pady=(0, px(8)))
        PillButton(toolbar, "刷新", self.log_refresh, kind="soft",
                   size=9, height=29).pack(side="left")
        PillButton(toolbar, "打开日志文件", self._open_log_file, kind="ghost",
                   size=9, height=29, padx=11).pack(side="left",
                                                    padx=(px(6), 0))
        PillButton(toolbar, "打开日志目录", self._open_log_dir, kind="ghost",
                   size=9, height=29, padx=11).pack(side="left",
                                                    padx=(px(6), 0))
        self.log_count = self._label(toolbar, "", 8, fg=MUTED)
        self.log_count.pack(side="right")
        card = tk.Frame(wrap, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="both", expand=True)
        self.log_text = tk.Text(card, bg="#FBFCFE", fg=TEXT, relief="flat",
                                bd=0, font=(MONO, 9), wrap="word",
                                padx=px(10), pady=px(8))
        self.log_text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(card, orient="vertical",
                           command=self.log_text.yview,
                           style="Vertical.TScrollbar")
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.configure(state="disabled")

    def log_refresh(self):
        lines = core.log_tail(800)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        if lines:
            self.log_text.insert("1.0", "".join(lines))
            self.log_text.see("end")
            self.log_count.configure(text=f"最近 {len(lines)} 行 · "
                                          f"{core.LOG_FILE}")
        else:
            self.log_text.insert(
                "1.0", "暂无操作记录。\n\n"
                       "实际执行清理、搬移、删除或卸载后，记录会出现在这里。\n"
                       "dry-run / 预览不会写日志。")
            self.log_count.configure(text="暂无记录")
        self.log_text.configure(state="disabled")
        self._set_status("操作日志已刷新。", "muted")

    def _open_log_file(self):
        if not os.path.exists(core.LOG_FILE):
            messagebox.showinfo("Cpan", "还没有日志文件。")
            return
        try:
            os.startfile(core.LOG_FILE)
        except Exception as exc:
            messagebox.showerror("Cpan", str(exc))

    def _open_log_dir(self):
        if not os.path.isdir(core.LOG_DIR):
            messagebox.showinfo("Cpan", "还没有日志目录。")
            return
        self._open_path(core.LOG_DIR)

    # ------------------------------------------------------------- dialog
    def _text_dialog(self, title, heading, body, open_path=None):
        top = tk.Toplevel(self)
        top.title(title)
        top.configure(bg=BG)
        top.transient(self)
        w, h = px(720), px(440)
        x = self.winfo_rootx() + max(0, (self.winfo_width() - w) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - h) // 2)
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.minsize(px(520), px(320))
        outer, body_frame = self._card(top, px(20), px(16))
        outer.pack(fill="both", expand=True, padx=px(14), pady=px(14))
        self._label(body_frame, heading, 12, True).pack(anchor="w")
        text_wrap = tk.Frame(body_frame, bg=CARD)
        text_wrap.pack(fill="both", expand=True, pady=(px(8), px(10)))
        text = tk.Text(text_wrap, bg="#FBFCFE", fg=TEXT, relief="flat",
                       bd=0, font=(MONO, 9), wrap="word",
                       highlightthickness=1, highlightbackground=BORDER,
                       padx=px(8), pady=px(8))
        text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(text_wrap, orient="vertical", command=text.yview,
                           style="Vertical.TScrollbar")
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.insert("1.0", body)
        text.configure(state="disabled")
        buttons = tk.Frame(body_frame, bg=CARD)
        buttons.pack(fill="x")
        if open_path:
            PillButton(buttons, "打开位置",
                       lambda: self._open_path(open_path), kind="soft",
                       size=9, height=30).pack(side="left")
        PillButton(buttons, "关闭", top.destroy, kind="ghost",
                   size=9, height=30).pack(side="right")
        top.bind("<Escape>", lambda _e: top.destroy())
        top.grab_set()
        top.focus_set()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--cli" in sys.argv:
        # Light entrance for headless self-checks: cpan_gui.py --cli scan
        rows = core.scan_junk()
        total = sum(r["size"] for r in rows)
        for r in rows:
            print(f"{r['name']}: {core.fmt_size(r['size'])} "
                  f"({r['files']} files)")
        print(f"total: {core.fmt_size(total)}")
        return
    app = CpanApp()
    app.mainloop()


if __name__ == "__main__":
    main()
