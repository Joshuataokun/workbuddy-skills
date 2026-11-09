# TTL 到期清理 · 细则（v1.6.0）

> 正文 SKILL.md 第 25–30 条是精简版；本文件是权威细则。**改 TTL 规则前先读这里。**

## 一、要解决的问题

收敛技能原本「只归档不删除」：`_archive/`、`_cleared-*`、`archive/memory-*` 里的东西越堆越多，永远不会消失。2026-11-09 实测全机 26 个隔离单元、约 300+ 文件，最老 28 天，从没清过。
用户口径（原话）：「增加到期自行删除机制（3 天，3 天后再次运行收敛技能，自行删除）」。

## 二、硬边界（用户 2026-11-09 拍板）

| 项 | 决定 |
|---|---|
| 删除范围 | **只删垃圾类**：草稿脚本、诊断/测试产物、本轮中间产物、解析出的 json、`__pycache__`。记忆快照、旧日志、技能备份、交付物、基线/构建产物、仓库资产、**>1MB 文件**一律 pin，永不自动删 |
| 存量 | **补 manifest 立即纳入计时**（26 个单元已补，非破坏） |
| 确认门 | **自动删 + 留痕**；首次启用强制 dry-run 一次，之后不再逐次点头 |
| 计时 | 归档时刻 + 3 天；**不建定时任务**——不运行收敛就不删，按事件不按日历 |
| 作用域 | purge 只作用于当前空间（SKILL.md 第 20 条）；backfill 写 manifest 是非破坏的，可跨空间 |

## 三、命令速查

```
PY = C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe
S  = ~/.workbuddy/skills/workspace-converge/scripts/ttl.py

# 新归档登记（移入隔离单元的当刻）
python $S init <隔离单元目录> [--ttl-days 3] [--pin] [--force]

# 存量补 manifest（非破坏；已有 manifest 的跳过）
python $S backfill E:/WorkBuddy [--dry-run]

# 只读到期清单（将删 / 引用拦截 / pin / 未到期 / 活动守卫延后）
python $S scan <空间根> --refs <空间>/.workbuddy/archive/ttl-refs.txt

# 到期释放（首次自动 dry-run 并写 armed；第二次起真删）
python $S purge <空间根> --refs <空间>/.workbuddy/archive/ttl-refs.txt [--dry-run]

# 永不自动删：整目录或单个文件
python $S pin <隔离单元目录> [--file <manifest 里的相对路径>]
```

**purge 前必须刷新 `ttl-refs.txt`**：导出自动化 prompt（`automation_update mode=view`）与各空间引用到的脚本/路径关键词，写进 `<空间>/.workbuddy/archive/ttl-refs.txt`。不传 `--refs` 时脚本仍会扫各空间 MEMORY.md 与日志，但覆盖不全，报告要注明。

## 四、manifest（`_TTL.json`）

写在**隔离单元根目录**。单元＝`_archive/<日期>` 这类内层批次，或 `_cleared-<日期>` 整体；容器目录 `_archive` 本身不算单元（否则会漏掉写在批次里的 manifest）。

字段：`version`、`created_by`、`created_at`、`archived_at`、`time_basis`、`ttl_days`、`expires_at`、`pinned`、`pin_reason`、`root`、`files[]`。
`files[]` 每项：`path`、`bytes`、`sha256`、`disposition`（purgeable / pinned）、`reason`、`deleted_at`。

`archived_at` 取值优先级：目录名里的日期 → 目录内最早文件 mtime → 目录 mtime。`time_basis` 如实记录依据；按目录名推算属**推断**，不是精确归档时刻。

## 五、分级判据（白名单式，宁可留错不许删对）

判 purgeable 必须全部满足：路径不含任何 `PIN_MARKERS`（memory-snapshot / memory-20 / backups / `.workbuddy/archive` / `.workbuddy/memory/archive` / workbuddy-skills-repo / baseline / out/assets / `/out/` / h5-patch / node_modules / dist / release）· 扩展名不在 `PIN_EXTS`（.md/.xlsx/.docx/.pdf/图片/.zip/.csv/.txt/.ps1/.sh…）· ≤1MB · 扩展名在 `PURGE_EXTS`（.py/.js/.pyc/.json/.log/.out/.tmp/.html）或文件名 `test_*.xlsx`。
其余一律 pinned。`test_*.xlsx` 的判定排在 `.xlsx` 通用 pin 之前。

**单元目录本身**落在 `.workbuddy/archive`、`.workbuddy/memory/archive`、`.workbuddy/backups`、`workbuddy-skills-repo` → 整目录强制 pin（含其中的 json/log）。技能仓库整体跳过，不写 manifest，否则 `_TTL.json` 会被 sync.sh 带进公开仓库。

## 六、删前四道闸

1. **manifest 合法**：version=1、files 非空、expires_at 可解析。缺失/损坏/空 → 整批不处理
2. **已过期**：now ≥ expires_at
3. **活动守卫**：单元内（排除 `_TTL.json`）24h 内有写入 → 整批延后
4. **未被引用**：完整相对路径、末两段路径、或特异文件名出现在引用文本里 → 保留并报告。`build.py`/`index.html`/`extract.py` 等 `GENERIC_NAMES` 不凭同名拦（避免"别处提到过同名"永久卡住删除）

**路径断言**：候选文件规范化后必须落在单元目录内，否则保留。

## 七、执行流程（吸收每周体检 v9.3 的成熟做法）

- **首次启用**：ledger 里没有 `armed: true` → 强制 dry-run，只出清单、写 armed，不删任何文件
- **两阶段**：先冻结清单 `.workbuddy/archive/ttl-plan-<时间戳>.jsonl`，再**只按清单删**，不重新枚举目录
- **删前复核**：重取 size/mtime 与计划比对，被改动即跳过（计入 skipped）
- **逐文件删**，清空的空子目录按倒序 `rmdir`；保留 `_TTL.json` 作墓碑
- **回读**：报告每个单元剩余文件数
- **台账** `.workbuddy/archive/ttl-ledger.md`：时间 / 隔离目录 / 文件 / 字节 / sha256 前 12 位 / 归档时间 / 理由
- **幂等**：manifest 里记 `deleted_at`，重复运行不会二次删

**台账不是恢复源**：删除不可逆，ledger 只留审计证据，不含文件内容。想留就在 3 天窗口内 `pin`。

## 八、与每周体检 v9.3 的分工（重要，别混）

| | 每周体检 v9.3 | 本技能 |
|---|---|---|
| 管什么 | 平台级隔离根 `E:\WorkBuddy\.trash-quarantine`、`C:\Users\Administrator\.cleanup-quarantine`、`backups\`、会话回滚/编辑历史索引、已删空间目录 | 空间内 `_archive/`、`_cleared-*`、`archive/memory-*` |
| 期限 | 7 天（隔离）/ 各类 retention 天数 | 3 天 |
| 策略源 | `cleanup-policy.json` | `_TTL.json`（`--ttl-days`） |
| 触发 | 每周一 11:00 自动 | 再次运行收敛技能时 |
| manifest | `manifest.json`（items/from/to/sha256） | `_TTL.json`（归档/到期/sha256/处置） |

范围不重叠，天数不同是有意的：空间内草稿 3 天够，平台级回滚 7 天。**v9.3 已成熟运行的机制（计划冻结、活动守卫、路径断言、回读校验、口令/保留白名单、V1–V11 验收）直接吸收进 ttl.py，不重复造。**

## 九、调研来源（2026-11-09，勿重复查）

- **NousResearch/hermes-agent RFC #16077（Hermes Curator）**：active→stale→archived 生命周期；`purge` 独立命令且**永不自动**；`pin` 永不自动处理、被 cron 引用的跳过；每次变更先写 ledger 可 rollback；`run --dry-run` 预览；`list-archived`/`restore`；`archive_ttl_days` 需显式开启。社区明确主张 archive-only（issue #7816）
- **Archive Management Skill（skillsmp / go-agent-llm-orchestrator）**：TTL 过期**且 `applied_count=0`** 才删；仍被使用的条目永不删；清理写 `archive.log`（时间戳+执行者）；反模式：盲删、移动后不更新引用、日志无限增长
- **本机每周体检 v9.3（2026-11-09 已在运行）**：两阶段计划冻结、24h 活动守卫、路径断言、manifest 校验、回读与回收站对账
- **openclaw-optimization-guide（394★）Part 27**：MEMORY.md 只当索引、细节下沉；堆积本身是隐性成本
- 已查过不再查：rem-sleep、memory-merger、prune-agent-memory、moltq/pearceit、AgentsMesh、enso-os、ShieldCortex

> 主流项目都不敢自动删（Hermes：「Purging never happens automatically」）。本技能的自动 purge 比它们激进，靠 **pin 分级 + 四道闸 + 首次 dry-run + ledger** 把激进变安全，差别只在"到期后谁按删除键"。

## 十、2026-11-09 首跑实测

- 全机补 manifest **26 个单元**；分类结果：将删 **35 个 / 709.8 KB**、引用拦截 21、pin 160、活动守卫延后 25、未到期 0
- 将删清单集中在三处：`work-gongzi/_archive/20261017`（12）、`work-gongzi/_archive/20261026`（17）、`prompt-skill-upgrade/_archive/20261029`（6），全是草稿脚本、解析 json、test 表、一次性打包脚本
- 主动 pin `test_ledger.xlsx` / `test_ledger2.xlsx`（`check_ledger.py` 的回归样本，删了没法复验）
- 今天新建 `网游单机/_cleared-20261109` 未到期 ＋ 24h 活动守卫双重拦下；其中 16MB `index.77bbw.js` 与 2MB `cocos2d-js-min.js` 因 `/out/`、`baseline` 判为 pin，**不会因到期被抹掉**
- 当前空间首次 dry-run 已跑、armed 已写；**本轮零删除**

## 十一、换机

脚本与本文在技能目录内，随 `sync.sh` → GitHub → `restore.sh` 走。但 `ttl-refs.txt`、`_TTL.json`、`ttl-ledger.md` 都在各空间本地，不进仓库。新机上第一次运行收敛时：先 `backfill` 重建 manifest（非破坏），再看 dry-run 清单。
