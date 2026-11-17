# 记忆预算与整合（唯一主本，v2.3.0）

> 2026-11-18 用户拍板方案 A：卡片技能补上「用户级 / 空间级 MEMORY.md」的预算体检与整合提案，**不复活收敛技能 B 档压缩记忆，不做日志归档**。
> 改规则只改这一份；别处只留指针。

## Threshold

| 项 | 值 | 说明 |
|---|---|---|
| 字符上限 | 3000 | 沿用用户级记忆既有预算，不改成 Claude Code 的 25KB |
| 行数上限 | 70 | 同上 |
| 预警线 | 80% | 任一维度达到即提示；**只提示、不阻断、不自动删** |
| 相似度 | ≥0.93 且长度 ≥12 | 与 `card.py` 的查重口径一致 |

预警由 `SessionStart` 的 `pitfall_inject.py` 在注入坑提醒时顺带打一行，**复用现有 hook、不新增条目**。`Stop` 时刻不另挂提示：它的 stdout 是 `continue:false` / reason 判定通道，塞普通文本会被吞或污染判定；`stop_guard.py` 被拦时的 reason 里补一句状态即可。

## check 出哪四类候选

只读扫描两份 MEMORY.md 的条目行（`- `／`数字. `／`> ` 开头，长 ≥6），每条只出一条提案，理由可叠加：

| 类别 | 判据 | 建议动作 |
|---|---|---|
| 失效标记 | 含「已失效／已废弃／已作废／不再使用／旧口径／已删除／不再生效」 | 确认后删除 |
| 重复条目 | 同文件内与更早条目完全相同，或相似度 ≥0.93 | 合并或删其一 |
| 别处已有 | 条目正文在另一份 MEMORY.md、当天日志或卡片主卡中原样出现 | 留指针、删正文 |
| 待核实 | 含推测性陈述（大概／估计／大概率／似乎／也许／应该是／可能是／疑似）或凭据样式 | 补来源或改【待确认】 |

**推测词只收陈述、不收场景描述**：「意图不确定 → 先问」「可能手机或桌面」是硬规则，不是推测。11-18 首版正则含裸的「不确定」，把用户级两条硬规则误报成待核实，已收紧（回归里有一条专测这个）。

## 命令速查

```bash
M=~/.workbuddy/skills/my-project-card/scripts/memory_check.py

# 只看预算状态（hook 用这个）
python $M status --workspace "<当前工作区>"

# 只读体检：量两个数 + 出带编号的待整合清单
python $M check --workspace "<当前工作区>"
python $M check --workspace "<当前工作区>" --out "<空间>/.workbuddy/archive/memory-清单.md"

# 逐条点头后执行（默认是干跑）
python $M apply --ids 1,3 --workspace "<当前工作区>"
python $M apply --ids 1,3 --confirm --workspace "<当前工作区>"

# 把某条替换成新写法，而不是删掉
python $M apply --ids 2 --confirm --replace "2=新写法：……" --workspace "<当前工作区>"
```

`apply` 的闸门：`--ids` 必填（先跑 `check` 看编号）；不加 `--confirm` 只干跑、零改动；`--scope user` **一律拒绝**。

## 用户级记忆是只读的

用户级 `~/.workbuddy/user-*/MEMORY.md` 全空间共用，改一处影响所有空间。所以脚本对它**只体检、只列候选，从不写入**。确需修改时单独确认后处理，并自己量字符预算。空间级 `MEMORY.md` 才允许 `apply`。

## 删除护栏

- 删前把整份 MEMORY.md 复制进 `<空间>/.workbuddy/backups/MEMORY.<时间戳>.md`，校验 sha256 与原文件一致才继续；校验失败即放弃、原文件不动。
- 原子写：临时文件 + `os.replace`，避免多会话读-改-写覆盖。
- 每次写入追加一行到 `<空间>/.workbuddy/archive/memory-变更报告.md`：时间 / 编号 / 行号 / 理由 / 处置 / 备份 sha256 / 字符前后。
- **台账不是恢复源**，恢复只能去备份目录。本机回收站两条路都被拦。
- 无人值守一条都不删；候选编号只在本次 `check` 结果内有效，文件变了就重跑 `check`。

## 生效前提与换机

- `settings.json` 外部修改**不热加载**，改完 hooks 要重启 WorkBuddy 或在 `/hooks` 面板审阅。
- 用户级路径用 `~/.workbuddy/user-*/MEMORY.md` 通配，不写死账号 ID；换机照抄账号名会找不到文件。
- 验收时用环境变量 `MEMORY_CHECK_HOME` 把整个 HOME 重定向到临时目录，`acceptance_memory.py` 整场不碰真实记忆。
- `budget_status()` 只量两个数、不扫候选，供 SessionStart 轻量调用；import 失败或异常一律静默跳过，不影响坑提醒。

## 明确不做

- 不做日志归档（当前 9 份，攒到 20 份再评估）。
- 不把 MEMORY.md 改成索引 + topic 文件分层（那是方案 B，会动全局口径文件）。
- 不按年龄淘汰条目：按「是否被替代 / 别处是否已有」判，年龄不是价值的代理。
- 不自动压缩上下文：压缩是平台行为，技能没有接口触发（见 `handoff-guide.md` 第七节）。

## 出处（2026-11-18 查，一手）

- Claude Code 官方 `code.claude.com/docs/en/memory`：MEMORY.md 是索引、一行一条；启动只加载前 200 行或 25KB；写后自动量，接近上限提醒 `merge or drop stale entries`；topic 文件按需读。
- GitHub `tigerless-labs/agent-memory` README（MIT）：独立 Manage 层、睡眠期整合；「无人值守只可 add/update，删除永远只是提案、要人确认」；supersede 保留链条；每次出 dream-report。
- GitHub `josiahcrackle9631/memory-bank` 的 `context-efficiency.md`：50–120 行 / 500–1200 token 基准，会话结束出 compression report，5 条 self-test 与 anti-patterns。
- AgentOS 官方 `useagentos.dev/docs/features/memory`：curated 2000 字符，超限写入被拒并返回现有条目让模型同批整合，batch 原子、`.bak` drift guard、溢出归档不丢。
