---
name: c-drive-cleaner
description: C 盘空间诊断与受控清理技能。当用户问 C 盘空间不足、C 盘满了、清理不动、可用空间没增加、缓存在反复长回来、想查大文件或隐藏占用、想知道哪个软件在吃 C 盘、要看 AppData 占用排行时调用。默认只做只读扫描出报告；清理必须显式预览、二次确认后才执行，且目标路径只认白名单。
version: 1.0.0
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
.\clean.ps1 -Profile tier1,browser,windows

# 2) 确认后执行
.\clean.ps1 -Profile tier1 -ReallyDelete

# 3) 需可还原时：移到 D 盘隔离区
.\clean.ps1 -Profile browser -ReallyDelete -Quarantine
.\restore.ps1 -Manifest .\reports\clean-<时间戳>.json
```

| 组 | 内容 | 前置条件 |
|---|---|---|
| `tier1` | 用户 Temp、npm 缓存、pip 缓存 | 无，随时可跑 |
| `browser` | Chrome 的 Cache / Code Cache / GPUCache / Service Worker | **先完全退出 Chrome** |
| `windows` | Windows\Temp、更新下载缓存、传递优化 | 需管理员 |

### 五道守卫（任一不过即整体拒绝，fail closed）

1. 必须是绝对路径且落在 **C 盘**
2. 不得命中 `protected_roots`（桌面/文档/下载/图片/视频/音乐/OneDrive/Roaming/AppData\LocalLow/System32/WinSxS/Program Files 等 22 条）
3. 路径**任意祖先**不得是 junction 或符号链接（否则删的是别的盘）
4. 必须真实存在
5. 必须出现在白名单 JSON 里

每次执行写清单到 `reports\clean-<时间戳>.json`：逐项成功/失败数、占用跳过的文件、前后体积。

## 本机硬约束（2026-10-28 三次对照实验）

1. **本会话的删除是直接永久删除，不进回收站。** 40 MB 单文件、34 MB 目录各删一次，删除后可用空间立即 +40 MB / +33.9 MB，回收站始终为 0。
2. **`Clear-RecycleBin` 在本会话不可用。** 恒定抛 `Win32Exception: The system cannot find the file specified`，清空前后空间 Δ=0。**这不是"报错但已完成"**——早先据此判成功是错的。回收站要清，交给资源管理器或火绒这类能直接调 Shell API 的工具，本技能不承担。
3. **不要用整盘可用空间差值判断清空是否生效。** 空间会因系统活动和他人操作变化。唯一判据是 `C:\$Recycle.Bin` 下 `$R*` 合计体积有没有下降。`-EmptyTrash` 已按体积判定，不生效就报"未生效"。
4. **`[safe-delete][SAFE_DELETE_FAIL_CLOSED] {"reason":"trash-failed"}` 和 `RuntimeException` 不可靠**——东西可能已删也可能没删，必须用目录体积交叉核对，不据此下结论。
5. **不要用 `[IO.Directory]::Delete()` 或 P/Invoke 绕开限制。** 绕一次，以后所有删除都失去保护。
6. 占用中的文件会失败并列出，属正常现象，关程序后重跑续删。
7. Chrome 关掉后会自启（实测 13→0→19 进程）。清 Service Worker 前必须确认 `Get-Process chrome` 为空。
8. `-Quarantine` 跨盘移动是复制+删除，700 MB 级需几十秒。

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

- `space-accounting-and-regeneration.md` — 占用核算与再生（最有用）
- `ai-software-lifecycle.md` — AI 软件生命周期分类口径
- `unused-and-misc.md` — U / MX 类边界
- `vendor-managed-storage.md` — 哪些只能走厂商入口
- `admin-deep-accounting.md` — 管理员层只读核算
- `upstream-readme.md` / `upstream-changelog.md` — 上游说明与版本史

## 上游与许可

上游 [niuhai/skill-c-cleaner](https://github.com/niuhai/skill-c-cleaner)（CleanSight），MIT License。

本技能为本地定制版：移除上游全部可写清理脚本，自建白名单驱动的 `clean.ps1`，补齐报告明细，扫描器与配置原样保留。分发时须保留 `LICENSE`。
