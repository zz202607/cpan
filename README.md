# Cpan — C盘安全清理工具

Windows C 盘清理工具，纯 Python 标准库实现，无需安装任何依赖。
设计原则见 [EXPERT.md](EXPERT.md)：白名单自动清理、用户文件走回收站、
先预览后确认、危险路径一律拒绝、操作全程留痕。

## 文件清单

| 文件 | 作用 |
|---|---|
| `EXPERT.md` | 专家设计文档（安全规则、白/黑名单、实现要点） |
| `cpan_core.py` | 核心引擎：扫描/清理/搬家/卸载/大文件 |
| `cpan_gui.py` | 图形界面（5 个标签页，点按钮即用） |
| `cpan.py` | 命令行入口（默认 dry-run，`--yes` 才真正执行） |
| `启动清理.bat` | 双击启动图形界面 |
| `logs/cpan_ops.log` | 操作日志（自动生成） |

## 快速开始（图形界面）

双击 `启动清理.bat`，六个标签页：

1. **垃圾清理** — 扫描垃圾类别 → 显示各项体积 → 勾选 → 确认后删除。
2. **软件搬家** — 列出装在 C 盘的软件及占用大小，一键搬到其他盘。
   采用目录联接（junction）方式：原路径保留链接，注册表/快捷方式不用改，
   软件照常使用。失败自动回滚。
3. **文件搬家** — 把 C 盘的目录/文件搬到其他盘，移动后自动校验大小。
4. **自定义清理** — 按 扩展名 / 最小体积 / 天数 规则找文件 → 送回收站（可恢复）。
5. **软件卸载** — 列出已安装程序，选中后调用官方卸载器。
6. **大文件** — 找大文件，可一键搬家或送回收站。

需要清理 `C:\Windows\Temp`、更新缓存、`Windows.old` 时：
右键 `启动清理.bat` → **以管理员身份运行**。

## 命令行用法

```bash
cd /d/my-project/Cpan

python cpan.py scan                                # 扫描所有垃圾类别
python cpan.py clean --cats user_temp,chrome_cache # dry-run 预览
python cpan.py clean --cats all --yes              # 真正执行
python cpan.py custom --path "$USERPROFILE\Downloads" --ext .tmp,.log --days 30
python cpan.py custom --path "$USERPROFILE\Downloads" --ext .tmp --delete --yes
python cpan.py move --src "$USERPROFILE\Downloads" --dst "D:\\" --yes
python cpan.py apps                                # 列出已安装程序
python cpan.py apps --cdrive                       # 只列装在 C 盘的
python cpan.py appmove --name "某软件" --dst "D:\\" --yes  # 联接方式搬出 C 盘
python cpan.py uninstall --name "某软件" --yes
python cpan.py bigfiles --dir "$USERPROFILE" --min-mb 300
```

所有破坏性命令不带 `--yes` 时只打印计划，不做任何改动。

## 安全说明

- **自动删除只发生在白名单目录**（临时文件、浏览器 Cache、缩略图、
  更新缓存、错误报告等可再生数据）。
- **用户指定的文件永远进回收站**，可恢复。
- `C:\Windows`、`Program Files`、系统引导文件、各盘根目录等一律拒绝操作。
- 浏览器只删 Cache 目录，不碰书签/密码/历史记录。
- 注册表不删不写（卸载功能只读取卸载命令）。
- 每次实际执行的删除/移动/卸载都写入 `logs/cpan_ops.log`。

## 常见问题

- **软件搬家安全吗？**：联接是 Windows 原生机制（NTFS junction），不修改注册表。
  搬前关闭目标软件；若搬后软件异常，把目录移回原处、删掉联接即可完全还原。
  杀毒/安全类软件不建议搬。
- **某些文件"跳过"**：正在被占用（如浏览器开着），属正常现象，关掉相关程序再清即可。
- **卸载时弹出原软件卸载界面**：正常，跟着走完即可。
- **微信文件搬走后**：在微信 设置 → 文件管理 里重新指定新目录。
