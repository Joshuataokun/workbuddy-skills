---
name: c-drive-cleaner
description: C 盘空间诊断与受控清理技能。当用户问 C 盘空间不足、C 盘满了、清理不动、可用空间没增加、缓存在反复长回来、想查大文件或隐藏占用、想知道哪个软件在吃 C 盘、要看 AppData 占用排行时调用。默认只做只读扫描出报告；清理必须显式预览、二次确认后才执行，且目标路径只认白名单。
version: 1.1.0
---

# C 盘空间诊断与受控清理

## 本版边界

默认只读。`analyze.ps1` 只扫描不写入；清理必须显式调用 `clean.ps1 -ReallyDelete`，否则只出预览。

- 24 个扫描脚本经核验**零 `Remove-Item`**，只调只读 API（目录枚举、注册表读取、WMI）。
- 清理只有一个入口 `clean.ps1`，目标路径只能来自 `safety\allowed-targets.json` 白名单，**不接受任何临时传入的路径**。
- 无迁移、无注册表修改、无服务启停、无定时删除。

## 环境要求

Windows 10/11，**PowerShell 5.1 即可**（不用 PS7 语法、不用三元和 `??`），无需 Python/Node。部分类别需管理员。

### 本机执行策略（必读）

本机 `Get-ExecutionPolicy` 为 **Restricted**，直接 `& .\analyze.ps1` 会报「禁止运行脚本」。**不要改系统策略**，用进程级放开：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Set-Location "$env:USERPROFILE\.workbuddy\skills\c-drive-cleaner"
```

每条命令前跑这两行，只影响当前会话，不写注册表。

## 快速开始

```powershell
# 日常：临时/浏览器/开发缓存/大文件/更新残留五类，出 Markdown 报告
.\analyze.ps1 -Categories "B,D,C,F,WU" -OutputFormat markdown

# 全量只读扫描（慢）
.\analyze.ps1 -OutputFormat markdown

# 快速证据集，跳过全盘扫
.\analyze.ps1 -Fast -OutputFormat markdown

# 只看 AI 软件占用（WorkBuddy / Qoder / Codex / TRAE / 豆包等）
.\analyze.ps1 -Categories "AF" -OutputFormat json

# 精确核算单目录真实占用（NTFS 分配字节 + 硬链接去重）
.\measure-space.ps1 -Paths "$env:LOCALAPPDATA\SomeApp"

# 增长基线，下次对比看谁在长
.\track-growth.ps1 -Mode compare -Record
```

报告写到 `reports\CleanSight-CS-<日期>-<时间>-<健康分>.md`。

**报告结构**：上游 `BuildReport` 原本漏写扫描明细、只出 12 行摘要，本版已补「二、扫描明细」（按类别分组、含大小/风险/路径/建议）。明细只列 ≥1 MB 项，更小的折成一行汇总，避免缩略图缓存这类噪音撑爆表格。

## 扫描类别

| 类别 | 覆盖 | 权限 |
|---|---|---|
| `B` 临时缓存 | Temp、缩略图、回收站、Update 缓存 | 普通 |
| `C` 开发缓存 | npm / pip / cargo / maven / gradle 等 | 普通 |
| `D` 浏览器 | Chrome / Edge / Firefox 等 | 普通 |
| `E` 应用数据 | IDE、媒体、办公、AI 工具 | 普通 |
| `AF` AI 软件生命周期 | 安装目录 / runtime / 模型 / 扩展 / 索引 / 更新残留 | 普通 |
| `F` 大文件 | 原生并发 TOP 20 + 用户目录排行 | 普通 |
| `GR` 增长 | 带时间戳的路径级增量与日增长率 | 普通 |
| `G` 特殊占用 | Docker / WSL / 游戏平台 | 普通 |
| `L` 即时通讯 | 微信 / QQ / 钉钉缓存 | 普通 |
| `K` 输入法 | 词库、日志 | 普通 |
| `I` 多版本残留 | 同软件多版本并存 | 普通 |
| `J` 重复运行时 | Electron / CEF 重复 | 普通 |
| `MS` 厂商托管存储 | WPS 云缓存、ESP-IDF 归档（**只能走厂商 UI**） | 普通 |
| `U` 不常用软件候选 | 卸载注册表 + 安装时间 + 体积 | 普通 |
| `MX` C 盘零碎信息 | 一级目录、根目录散落文件、扩展名分布 | 普通 |
| `WU` Windows 更新残留 | WinRE、更新下载、待重启信号、CBS 日志 | 普通 |
| `A` 系统隐藏 | hiberfil / pagefile / 还原点 / WinSxS | 部分需管理员 |
| `H` 安全软件 | EDR / NAC / 杀毒（**只列不碰**） | 普通 |
| `AD` 管理员深度核算 | VSS、WinSxS、WindowsApps、Installer、DriverStore | **管理员** |
| `VM` 虚拟内存 | PagingFiles 注册表 + pagefile.sys 实际大小 | 普通 |
| `SA` NTFS 实际占用 | 逻辑大小 / 硬链接去重 / 分配字节 | 普通（慢） |

## 清理执行（必须二次确认）

**铁律：先跑预览，把目标路径和大小报给用户，拿到明确同意后才能加 `-ReallyDelete`。用户说"清理一下"不等于同意删除具体路径。**

```powershell
# 1) 预览（默认，不删任何东西）
.\clean.ps1 -Profile tier1,browser,windows,apps

# 2) 确认后执行 —— 本机删除常进回收站，必须带 -EmptyTrash 才真正释放
.\clean.ps1 -Profile tier1,apps -ReallyDelete -EmptyTrash

# 3) 需可还原时：移到 D 盘隔离区
.\clean.ps1 -Profile browser -ReallyDelete -Quarantine
.\restore.ps1 -Manifest .\reports\clean-<时间戳>.json
```

| 组 | 内容 | 前置条件 |
|---|---|---|
| `tier1` | 用户 Temp、npm 缓存、pip 缓存 | 无，随时可跑 |
| `browser` | Chrome 的 Cache / Code Cache / GPUCache / Service Worker | **先完全退出 Chrome**（关掉会自启） |
| `windows` | Windows\Temp、更新下载缓存、传递优化 | 需管理员 |
| `apps` | 微信 `xwechat\log`、腾讯会议 `WebkitCacheData`+`Logs`、WorkBuddy `logs`/`traces`/更新残留、Cherry Studio 更新残留 | 删 WorkBuddy 自己的日志需退出应用，否则正被写入的删不掉 |

### 六道守卫（任一不过即整体拒绝，fail closed）

1. 必须是绝对路径且落在 **C 盘**
2. 不得命中 `absolute_deny`（桌面/文档/下载/图片/视频/音乐/OneDrive/System32/WinSxS/Program Files 等 17 条）——**写进白名单也不豁免**
3. 不得命中 `protected_roots`（`%APPDATA%`、LocalLow、Programs、Outlook、OneDrive 等 5 条）——只有当路径被白名单**明确列出**时才放行
4. 路径**任意祖先**不得是 junction 或符号链接（否则删的是别的盘）
5. 必须真实存在
6. 必须出现在白名单 JSON 里（不接受任何临时传入的路径）

第 3 条为什么要开豁免：`%APPDATA%` 整体保护会连带挡住 `Tencent\xwechat\log` 这类合法缓存。不放行就只能二选一——放弃保护或放弃清理。折中做法是「人工审核进白名单的才穿」，`absolute_deny` 兜底。

每次执行写清单到 `reports\clean-<时间戳>.json`：逐项成功/失败数、占用跳过的文件、前后体积、回收站前后体积。

## 本机硬约束（2026-10-28 / 10-30 实测）

1. **删除行为不稳定，不能假设。** 2026-10-28 测试时 40 MB 单文件和 34 MB 小目录是**直接永久删除**（空间立即 +40 / +33.9 MB，回收站仍为 0）；2026-10-30 清理 1.4 GB 应用日志时却**全部进了回收站**（回收站涨到 921 MB，空间一点没释放）。同一台机器、同一个命令，结果不同。
   所以：**执行后必须查回收站体积**，涨了就说明要走清空那一步，别指望"删完就释放"。
2. **`Clear-RecycleBin` 可用，但会抛假异常。** 2026-10-30 用 921 MB 内容实测：调用抛 `Win32Exception: The system cannot find the file specified`，清空后回收站体积归零、C 盘 +1.41 GB——**异常是假的，操作是真做完了**，不要因为报错就重试或放弃。
   （2026-10-28 曾误判它"不可用"：那次测试时回收站本来就是空的，"找不到文件"是空回收站的正常反应，据此下结论是错的。）
3. **判定只能看回收站体积**（`C:\$Recycle.Bin` 下 `$R*` 合计），既不能看异常，也不能看整盘空间差值——空间会因系统活动和他人操作变化。`-EmptyTrash` 已按体积判定。
4. **`[safe-delete][SAFE_DELETE_FAIL_CLOSED] {"reason":"trash-failed"}` 和 `RuntimeException` 不可靠**——东西可能已删也可能没删，必须用目录体积交叉核对，不据此下结论。
5. **不要用 `[IO.Directory]::Delete()` 或 P/Invoke 绕开限制。** 绕一次，以后所有删除都失去保护。
6. 占用中的文件会失败并列出，属正常现象，关程序后重跑续删。
7. Chrome 关掉后会自启（实测 13→0→19 进程）。清 Service Worker 前必须确认 `Get-Process chrome` 为空。
8. `-Quarantine` 跨盘移动是复制+删除，700 MB 级需几十秒。

## DISM / WinSxS —— 别把它当增长点

2026-10-30 实测：本机 WinSxS 实际 12.05 GB，但其中 **8.14 GB 是与系统共享的硬链接**，不算额外占用。

跑了 `/StartComponentCleanup /ResetBase`：清理日期更新了，但组件存储大小、备份与已禁用功能项**一个字节没变**，C 盘也没释放。

原因：DISM 报的「备份和已禁用的功能 3.91 GB」主体是**已禁用的 Windows 可选功能**，不是旧补丁备份。`ResetBase` 只删被 superseded 的组件版本，删不掉已禁用功能。要清得用 `Disable-WindowsOptionalFeature -Remove`，会断掉以后重新启用，不做。

**DISM 说「推荐使用组件存储清理：是」≠ 能回收那几个 GB。** 别把 `AnalyzeComponentStore` 的数字当承诺报给用户。

两个操作细节：`Dism.exe` 不在 PATH，用 `C:\Windows\System32\Dism.exe`；输出经管道会因 GBK 编码乱码，**直接调用，不要 `| Select-String`**。

WinSxS **绝对不能手动删**（微软官方警告：系统无法启动、无法更新）。

## 明确不做的事

`allowed-targets.json` 的 `excluded_by_design` 记录了故意排除项，改白名单前先读：

- **缩略图/图标缓存**：被 explorer 独占，不结束 explorer 删不掉，只值 7 MB，收益不抵风险
- **回收站**：可能混有误删文件，须由用户在资源管理器人工确认
- **WER 错误报告**：可能含故障排查线索
- **Prefetch**：清了会拖慢程序启动

## 输出口径

报告必须区分这四类，**不能把目录占用当成可清理额度**：

1. **可回收**：明确的安全缓存，有实测证据
2. **需确认**：低风险但要用户判断
3. **只能走厂商**：WPS、ESP-IDF、微信这类有官方管理入口的
4. **仅信息**：解释空间去向，不等于可删

三条硬约束：父子目录去重后再汇总，**不能父子相加**；页面文件、WinSxS、VSS、WindowsApps 只进「仅信息」层；扫描命中 ≠ 可删除。

给用户列「可回收」之前，**先过一遍 `references/never-delete.md`**：C 盘上最大的几个目录（WPS addons、Adobe CameraRaw、NVIDIA NGX、微信 radium、AnyTXT 索引）都不是垃圾，误报一次就可能让用户删掉功能数据。

## 已知坑

- **junction / 符号链接**：目标或任一祖先为 junction 时统计失真，删除只释放**目标盘**空间。脚本会标 `partial`，报告须如实说明。
- **再生**：清完 5 分钟、1 小时、24 小时后数量可能回涨。`track-regeneration` 已移除，隔天用 `track-growth.ps1 -Mode compare` 对比。

## 建议的三步诊断法

1. **量总账**：`-Categories "MX"` 看空间被哪几个一级目录占了
2. **找大户**：`-Categories "F"` 出大文件 TOP 20；怀疑某软件用 `measure-space.ps1` 精算
3. **判性质**：`-Categories "B,C,D,WU"` 区分「临时可回收」与「应用数据要迁移」

第 1 步的数字只是解释空间去向，**不是可释放空间**。

## references 目录

上游文档原样保留，其中提到的 `cleaners/`、`migrators/` **在本版已移除**，只作判定口径参考，不要照着调用。

- `never-delete.md` — **看着大但不能删的目录清单 + 陌生大目录的判定五问**（最有用，给用户报建议前先读）
- `space-accounting-and-regeneration.md` — 占用核算与再生
- `ai-software-lifecycle.md` — AI 软件生命周期分类口径
- `unused-and-misc.md` — U / MX 类边界
- `vendor-managed-storage.md` — 哪些只能走厂商入口
- `admin-deep-accounting.md` — 管理员层只读核算
- `upstream-readme.md` / `upstream-changelog.md` — 上游说明与版本史

## 上游与许可

上游 [niuhai/skill-c-cleaner](https://github.com/niuhai/skill-c-cleaner)（CleanSight），MIT License。

本技能为本地定制版：移除上游全部可写清理脚本，自建白名单驱动的 `clean.ps1`，补齐报告明细，扫描器与配置原样保留。分发时须保留 `LICENSE`。
