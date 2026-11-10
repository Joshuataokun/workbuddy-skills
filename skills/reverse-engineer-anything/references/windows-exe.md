# Windows `.exe` / PE 逆向工作流（本地增强）

本页是本地新增的 `.exe` 专用入口。上游技能把 PE 能力分散在「Route the
target first」的各个条目里；这里把它收成一条可执行的顺序：**先分型 → 再取静态
证据 → 最后才考虑深度反编译**。所有命令都只读文件，不执行目标。

## 0. 三条硬边界（本机 2026-11-10 实测）

1. **本机 `rea` CLI 是 6.8.0**（`command -v rea` 定位，`rea --version` 确认），
   而本技能文档同步自 GitHub main 的 v62。`rea --help` 才是本机真实命令清单；
   文档里出现、6.8.0 里没有的操作不要调。当前已知缺：
   `inspect-binary-hardening`、`inspect-elf-unwind-ranges`、
   `inspect-kernel-build-config`、`inspect-native-initializers`、
   `inspect-windows-shortcut`，以及 desktop build-computer 系列。
   调用前用 `rea <command> --help` 确认；不存在就如实报能力缺口。
2. **MCP 会话不一定连着 REA**。WorkBuddy 会话里若没有 `open_binary` 等工具，
   走 CLI 的 target-free 命令（下面第 3 节），不要假装 MCP 结果存在。
   CLI 里也没有 `open-binary` 子命令，那是 MCP 工具名。
3. **深度反编译需要原生引擎**。本机 `rea providers` 只列出
   `rea-dotnet-static`、`sqlite`、`rea-artifact-graph`（部分可用）；直接跑
   `rea analyze <path>` 会返回 `provider_unavailable`。不要擅自安装
   Ghidra / Hopper / IDA，也不要擅自 `rea update`；先报告用户，等明确授权。
   运行时观察（启动/附加/插桩）同样要单独授权，见
   [runtime-observation.md](runtime-observation.md)。

## 1. 第一步：分型（零依赖，不需要 REA）

```bash
python scripts/pe_triage.py "<绝对路径/app.exe>"            # 人读摘要
python scripts/pe_triage.py "<绝对路径/app.exe>" --json     # 完整 JSON
python scripts/pe_triage.py "<绝对路径/app.exe>" --out <新文件.json>
```

脚本只用 Python 标准库，读 DOS/PE 头、节表、数据目录、导入表、
Authenticode 表位置、各节熵与字节标记，输出分两部分：

- `observed`：PE32 / PE32+、架构、入口 RVA、ImageBase、子系统、节、
  导入 DLL 与函数、签名表是否存在、SHA-256、编译时间戳 —— 都是文件里读到的。
- `inferred`：`primary_route` 与候选类型（native / dotnet / pyinstaller /
  electron / go / rust / deno / bun / installer / packed / vb6 / autoit …）。
  这些是**字节与布局推断**，不是结论；字符串和混淆器节名都可以伪造。

`sha256` 用来和 REA Evidence 的 `subject.digest.sha256` 对齐，确认后续每条证据
说的是同一个文件。解析异常、采样截断都写进 `parse_issues` / `limitations`，
不要当成 0 或"没有"。

本机实测样本：

| 样本 | 脚本判定 | 交叉验证 |
| --- | --- | --- |
| `C:\Windows\System32\cmd.exe` | PE32+ / amd64 / native，43 DLL、286 个导入函数 | `rea inspect-pe-imports` 的 SHA-256 一致 `15cd209c…` |
| `...\Framework64\v4.0.30319\AddInProcess.exe` | PE32 / i386 / dotnet（CLR 目录） | `rea inspect-managed-artifact` 返回合法 Evidence |
| `D:\Program Files\WorkBuddy\WorkBuddy.exe` | PE32+ / amd64 / electron（`electron.asar`，204 MB，有签名表） | 大文件在 256 MiB 默认上限内正常完成 |

## 2. 按路线选工具

| `primary_route` | 先做什么 | 说明 |
| --- | --- | --- |
| `native` | 第 3 节通用证据；要函数级伪代码再走第 4 节 | 原生 C/C++/汇编；无引擎时只能给静态事实 |
| `dotnet` | `rea inspect-managed-artifact <path>`、`rea inspect-managed-members <path>`、`rea compare-managed-members ...` | PE/CLI 元数据、类型/方法、`ldstr` 字面量；本机 `rea-dotnet-static` 可用 |
| `pyinstaller` | `rea inspect-artifact <path> --detail summary --evidence_output <新文件>` | CArchive 才是应用层，bootloader 只是原生前缀；解出的 `.pyc` 用 `rea inspect-python-pyc` |
| `electron` | 先取 ASAR/资源，再 `rea analyze-javascript-application <解包目录> --json` | 看 JS 层，不要在原生壳里找业务逻辑 |
| `go` / `rust` | `rea inspect-go-binary` / `rea inspect-rust-binary` | 读内嵌构建与依赖元数据（缺失 ≠ 不是 Go/Rust） |
| `deno` / `bun` | `inspect-artifact`（v62 描述的新载体） | 6.8.0 支持有限，先跑 CLI 看返回，不要预设结论 |
| `installer` | `rea inspect-artifact ...` | NSIS / Inno Setup：先列安装包内容，再决定对哪个成员深入分析 |
| `packed` | `rea inspect-byte-entropy <path>`；再用导入表/节熵判断是否加壳 | 高熵只是线索，不等于恶意，也不等于一定加壳 |
| `vb6` / `delphi` / `autoit` | 导入表 + 资源 + 字符串 | 运行时依赖往往是主要线索；不要按原生 C 去反编译 |

## 3. 通用静态证据（本机 6.8.0 逐条实测通过）

下列命令都是 target-free：给绝对路径即可，不要先 `open_binary`。加
`--format json` 得到完整 Evidence（`operation`、`subject.digest.sha256`、
`normalized_result`、`limitations`）；输出大时用 `--filter-output <keys>` 或
`--evidence_output <新文件>` 保留完整记录（不会覆盖已有文件）。

```bash
rea inspect-pe-imports       "<path>" --format json   # 导入 / 延迟导入 DLL 与函数、ILT/IAT RVA
rea inspect-pe-load-config   "<path>" --format json   # TLS 回调、加载配置、安全 cookie、CFG 等声明
rea inspect-pe-certificates  "<path>" --format json   # WIN_CERTIFICATE 表身份（不验签、不作信任结论）
rea inspect-pe-resources     "<path>" --format json   # 版本信息、图标、manifest、资源范围与哈希
rea inspect-native-exports   "<path>" --format json   # 导出表（DLL 尤其有用）
rea inspect-artifact         "<path>" --detail summary --evidence_output <新文件.json>
rea inspect-managed-artifact "<path>" --format json   # .NET 专用
rea inspect-managed-members  "<path>" --format json   # .NET 成员与字面量
```

本机实测：7 条 `inspect-*` 命令全部返回合法 Evidence JSON，
`inspect-artifact --detail summary --evidence_output` 也成功。
`cmd.exe` 无 Authenticode 表时 `inspect-pe-certificates` 仍正常返回"观察到缺失"，
不要把它读成"文件未签名"或"签名无效"。

口径：导入表是**声明**，不是实际调用；安全目录缺失是**该表缺席**，
不证明镜像从别处没带签名；CFG/ASLR 标志是链接器声明，不证明运行时生效。

## 4. 深度分析（可选，需引擎）

```bash
rea providers                       # 先看有哪些 provider 真的可用
rea analyze "<path>" --provider <id>
rea function "<path>" <address>     # 或 rea decompile / instructions / xrefs / search
```

MCP 已连接时，等价路线是 `open_binary` → `binary_overview` →
`analyze_function` / `decompile` / `xrefs`；会话没有这些工具就别调用。
本机当前 `rea analyze` 返回 `provider_unavailable`（已实测），所以这一节属于
"用户授权安装引擎之后"的步骤，不是默认步骤。

静态分析不能证明执行行为。需要"程序实际做了什么"时，必须单独授权并限定目标，
见 [runtime-observation.md](runtime-observation.md) 与
[evidence-workflows.md](evidence-workflows.md)。

## 5. 结论口径

- 分清 `observed` / `inferred` / `unknown`，每条结论带 Evidence ID 或 SHA-256。
- 签名表 ≠ 可信；打包标记 ≠ 恶意；静态事实 ≠ 运行时行为。
- 负结果要写清搜索边界：没找到 ≠ 不存在；解析失败 ≠ 值为 0。
- 一次调查结束对照原始问题清单，逐条标 answered / partial / unresolved。

## 6. 常见坑

- 把 `.exe` 一律当原生 C++：最常见错误。先分型，路线错会白跑一轮。
- PE32 与 PE32+ 的 thunk 宽度不同（4 / 8 字节），脚本已按 `bits` 处理。
- 用相对路径或没给含空格路径加引号；UNC 网络路径不要用（可能外泄凭据）。
- 大文件：脚本默认拒收 >256 MiB；`inspect-pe-*` 默认 64 MiB，用
  `--max-file-bytes` 调，但别把整块输出塞进上下文，先 summary 再分页。
- `--evidence_output` / `--out` 只接受**新路径**，脚本不会覆盖已有文件。
- 上游再同步会覆盖 `SKILL.md` 与上游 `references/`；本页与
  `scripts/pe_triage.py` 是本地增量，重新同步后要按 SKILL.md 末尾的
  "Local installation notes" 重新叠加描述与路由改动。
