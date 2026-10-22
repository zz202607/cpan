# Cpan — C 盘空间管家

Windows C 盘清理、空间分析与搬家工具。纯 Python 标准库实现，无需安装任何依赖。
安全规则见 [EXPERT.md](EXPERT.md)：白名单自动清理、用户文件走回收站、
先预览后确认、危险路径一律拒绝、操作全程留痕。

## 2.0 更新

- **全新界面**：深色侧边栏 + 页面式布局，DPI 自适应，中文字体清晰。
  所有耗时任务都在后台线程运行，扫描/清理时界面不冻结。
- **概览仪表盘**：C 盘空间、磁盘使用、可清理总量、回收站、最近操作、一键智能清理。
- **空间分析**：按文件夹统计占用，带占比条，双击逐层下钻，可随时停止。
- **一键智能清理**：只勾选可再生的缓存/临时文件，不包含回收站和 Windows.old。
- **软件搬家更稳**：搬前检测目标目录中正在运行的进程，避免半途失败。
- **管理员入口**：普通模式下可在应用内直接以管理员身份重启。
- **系统工具**：官方 DISM 组件清理、关闭休眠释放 hiberfil.sys（均需管理员）。
- **更多实用清理项**：崩溃转储、系统网页缓存、传递优化缓存、开发工具缓存，
  以及 Chrome/Edge 的 GPUCache / ShaderCache。
- **列表全面升级**：搜索、排序、多选、选中项合计、双击打开位置/详情。
- **可分发安装包**：单文件 Setup.exe，按用户安装、免管理员、无需 Python；
  带新的应用图标、安装向导配图、开始菜单与桌面快捷方式。

## 文件清单

| 文件 | 作用 |
|---|---|
| `EXPERT.md` | 专家设计文档（安全规则、白/黑名单、实现要点） |
| `cpan_core.py` | 核心引擎：扫描/清理/搬家/卸载/空间分析/系统工具 |
| `cpan_gui.py` | 图形界面（侧边栏 + 9 个页面，点按钮即用） |
| `cpan.py` | 命令行入口（默认 dry-run，`--yes` 才真正执行） |
| `启动清理.bat` | 双击启动图形界面 |
| `logs/cpan_ops.log` | 源码运行时的操作日志；安装版在 `%LOCALAPPDATA%\Cpan\logs\` |
| `assets/` | 应用图标（ico/png）与安装向导图片 |
| `installer/` | Inno Setup 脚本、版本信息、简体中文语言文件 |
| `tools/make_icon.py` | 生成图标与安装向导图片（仅构建时用 Pillow） |
| `build.ps1` / `requirements-build.txt` | 一键构建（测试 → EXE → 安装器 → 便携 ZIP） |
| `tests/` | 离线、沙箱化的行为测试 |

## 快速开始（图形界面）

双击 `启动清理.bat`。需要清理系统级缓存时，点侧边栏底部的
**以管理员重启**（会弹出 UAC），不用再手动右键。

九个页面：

1. **概览** — C 盘空间与使用率、各磁盘余量、可清理垃圾、最近操作；
   「一键智能清理」只清推荐项，回收站须手动勾选。
2. **垃圾清理** — 扫描 → 勾选 → 确认清理；每项显示大小、文件数与清理路径。
   回收站、Windows.old 默认不勾选；★ 标记推荐项。
3. **空间分析** — 选目录统计每个子文件夹/文件的占用与占比；
   双击文件夹下钻，双击文件定位；支持停止。
4. **自定义清理** — 按扩展名 / 最小体积 / 天数筛选；支持搜索、多选、全选；
   删除一律进回收站（可恢复）。
5. **软件搬家** — 列出装在 C 盘的软件并统计实际占用；搬前检查运行中的进程；
   搬走后原路径保留 NTFS 目录联接，注册表/快捷方式不用改；
   Program Files 里的软件需要先点「以管理员重启」，否则程序会拒绝搬移。
6. **文件搬家** — 把 C 盘目录/文件搬到其他盘；先预览大小和目标空间，
   完成后校验大小，复制不完整时绝不删源。
7. **大文件** — 递归找大文件，支持搜索、多选、搬走、送回收站、打开位置。
8. **软件卸载** — 搜索、按大小/日期排序，调用软件官方卸载器。
9. **操作日志** — 查看实际执行的清理、搬移、删除、卸载记录，可直接打开日志文件。

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

## 安装包与分发

当前已构建好两个分发文件（位于 `dist/`，不需要接收方安装 Python）：

- `dist\installer\Cpan-Setup-2.0.0.exe` — 单文件安装器，约 9.6 MB
- `dist\Cpan-Portable-2.0.0.zip` — 便携版，解压即用，约 10.3 MB

安装器行为：

- 按用户安装到 `%LOCALAPPDATA%\Programs\Cpan`，**安装过程不需要管理员权限**；
- 创建开始菜单 `Cpan` 组（Cpan / 卸载 Cpan）；桌面快捷方式可选，默认勾选；
- 安装版启动时不需要 Python；系统级清理时，程序内部仍会按需请求 UAC 提权；
- 日志写入 `%LOCALAPPDATA%\Cpan\logs\cpan_ops.log`，卸载时保留，方便排查；
- 卸载：Windows 设置 → 应用，或开始菜单里的「卸载 Cpan」；
- 仅支持 Windows 10/11 x64。

**关于 SmartScreen**：安装包和 EXE 目前没有代码签名证书，Windows 可能提示
“Windows 已保护你的电脑 / 未知发布者”。内部使用可点「更多信息 → 仍要运行」；
面向公众分发建议购买代码签名证书并给 setup 与 Cpan.exe 签名。

### 重新构建

```powershell
python -m pip install -r requirements-build.txt
winget install JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

`build.ps1` 会依次运行完整测试、生成图标/安装向导图、用 PyInstaller 打包
`Cpan.exe`、用 Inno Setup 编译安装器、生成便携 ZIP，并输出 SHA-256。
版本号在 `build.ps1`、`installer/cpan.iss`、`installer/version_info.txt` 中同步修改。

## 测试

```bash
cd /d/my-project/Cpan
python -m pip install pytest     # 仅首次
python -m pytest                 # 全量：154 passed, 3 skipped（约 2 秒）
python -m pytest tests/test_move.py   # 只跑搬家/联接
```

测试覆盖（`tests/` 目录，全部离线沙箱化，不触碰真实回收站与系统目录）：

| 文件 | 覆盖 |
|---|---|
| `test_protection.py` | 保护路径：大小写/分隔符/`..`归一化/盘符根/环境变量展开/合法路径放行 |
| `test_junk.py` | 垃圾类别结构、扫描计量、白名单删除、缩略图前缀过滤、被占用文件跳过、dry-run/执行、管理员分级 |
| `test_custom.py` | 扩展名/体积/天数过滤的组合、回收站路径、保护路径拒绝 |
| `test_move.py` | 文件搬家与联接搬家：dry-run、空间校验、同名冲突、回滚，以及**回归测试：复制未完整时绝不删源目录** |
| `test_junction.py` | 真实 NTFS 联接的识别与透传计量 |
| `test_uninstall.py` | MSI `/I{}`→`/X{}` 转换、静默串优先、退出码语义、dry-run 不启动 |
| `test_cli.py` | 命令行接线：不带 `--yes` 一律不执行 |
| `test_utils.py` / `test_stats.py` | 工具函数与目录计量 |
| `test_extras.py` | 推荐项、扫描进度、磁盘列表、空间分析、进程检测、DISM/休眠 dry-run、日志尾部、联接剪枝 |

测试即验收：安全规则（白名单、回收站兜底、保护路径、默认 dry-run）
都在测试里以行为级断言固化，改代码前先跑一遍。

## 安全说明

- **自动删除只发生在白名单目录**（临时文件、浏览器 Cache、缩略图、
  更新/传递优化缓存、崩溃转储、错误报告等可再生数据）。
- **用户指定的文件永远进回收站**，可恢复。
- `C:\Windows`、`Program Files`、系统引导文件、各盘根目录等一律拒绝操作。
- 浏览器只删 Cache / Code Cache / GPUCache / ShaderCache，不碰书签、密码、历史记录。
- 注册表不删不写（卸载功能只读取卸载命令）。
- 所有递归扫描、计量与复制都会跳过目录联接/符号链接，避免重复统计或误动链接目标；
  搬移的源路径本身是联接时直接拒绝。
- **系统组件清理**使用 Windows 官方 `DISM /StartComponentCleanup`，不手动删
  WinSxS，也不使用 `/ResetBase`；耗时数分钟，需管理员权限。
- **关闭休眠**通过 `powercfg /h off` 实现，会同时关闭快速启动，可随时再开启。
- 每次实际执行的删除/移动/卸载/系统工具操作都写入操作日志：源码运行时在
  `logs/cpan_ops.log`，安装版在 `%LOCALAPPDATA%\Cpan\logs\cpan_ops.log`。
- 清理/搬家等 Shell 操作在后台线程中先初始化 COM，避免
  `SHEmptyRecycleBinW` 返回 `0x8000FFFF` 的偶发失败。

## 常见问题

- **某些类别显示"需要管理员权限"**：点该行或侧边栏的「以管理员重启」，
  确认 UAC 后即可清理系统临时文件、更新缓存、Windows.old、DISM 等。
- **某些文件"跳过"**：正在被占用（如浏览器开着），属正常现象，关掉相关程序再清即可。
- **软件搬家前提示进程正在运行**：说明软件（含托盘进程）还没关干净。
  建议先退出再搬；强行继续可能复制失败并自动回滚，源目录不会被删。
- **软件搬家安全吗？**：联接是 Windows 原生机制（NTFS junction），不修改注册表。
  搬前关闭目标软件；若搬后软件异常，把目录移回原处、删掉联接即可完全还原。
  杀毒/安全类软件不建议搬。
- **卸载时弹出原软件卸载界面**：正常，跟着走完即可。
- **微信文件搬走后**：在微信 设置 → 文件管理 里重新指定新目录。
- **回收站清空失败**：2.0 已在后台线程初始化 COM；若仍失败，通常是权限或
  回收站元数据损坏，可用系统自带的磁盘清理处理。
