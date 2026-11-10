# 版本变更与由来（出问题才需要读）

> 正文只留判断与顺序，踩过的坑记在这里。改规则前先扫一遍，避免把别人的教训再踩一次。

## v1.4.1 · 2026-11-04

**修 `converge.py` 路径核验的三类误报**（技能空间收敛时实测，报出的 4 处失效全是假阳性，逐条实测路径都在）：

- **不展开 `~`**：原实现直接 `os.path.exists()`，所有 `~/...` 写法必判失效 → 加 `expanduser` + `expandvars`。
- **不过滤占位符**：只跳过了 `*` 和 `…`，`<name>` 被当成真实路径 → 一并跳过含 `<` 的候选。
- **URL 咬尾**：`http://…` 被 `PATH_RE` 匹配成 `p:`（抠掉斜杠后只剩 `p:`）→ 跳过以 `:` 结尾、或含 `://` 的候选。
- 报告口径改为「有效候选数」而非「全部候选数」，噪声不再计入分母。

**反向验证**：造 `C:/no-such-dir-abc123/foo` 仍报「失效 1」，确认没修成"永远 PASS"——只去掉误报，保留真报。

**由来**：本空间 B 档收敛时路径项 FAIL 4 处，人工逐条核实后发现全是脚本问题。教训：**核验脚本本身也要被核验**，报 FAIL 先验证是记忆错还是脚本错，别急着回滚记忆。

## v1.4.0 · 2026-10-31

**对外改进（按技能成熟度模型 L2 → L3）**
- 新增 `evals/scenarios.md` 四个验收场景（正常 / 输入不全 / 误用边界 / 误删防护）——补上"改规则靠感觉"的缺口。
- 新增 `scripts/converge.py verify`：五项核验从四条人肉命令收成一条，退出码即判定。
- 新增 `scripts/converge.py snapshot`：快照 + 逐文件 md5 校验，让"备份存在"升级为"备份可恢复"。
- 正文新增「何时不要用」；A 档收紧为"纯问答轮不记结论"。
- 「由来」「处置表格式」「归档索引模板」「收敛记录模板」下沉到 `references/`，正文瘦身。
- 收敛记录新增三个数：耗时、字符前后、处置条数。

## v1.3.0 · 2026-10-29 傍晚
第 12 条旧判据"有 argparse 且无写死盘符"实测全盘失效——12 个脚本全无 argparse、全有盘符，按字面连天天在用的 `verify_sync.py` 都该归档。改为**技术层（盘符在模块级常量 vs 散在函数内）+ 业务层（产物是否还活着）**两层判据，用 AST 遍历判断。

## v1.2.0 · 2026-10-29 下午
① 压缩没有算法、只有判断，须写清"凭什么删" → 第 9 条补"别处有副本的只留指针"；② 实测压到 2,936 字符却 71 行、memcheck 仍报绿 → 第 10 条加行数核验，四项改五项；③ 把博客二手数据当一手（称 91.8k★，连接器实测 97,009★）→ 第 2 条加来源层级与时点；④ 只保证"一条没丢"，用户无法验证 → 第 21 条要求处置表。

## v1.0.0 → v1.1.0 · 2026-10-29 上午
- 手工令牌比对号称零丢失，脚本复测发现漏 3 个指针（台账空间 ID、回滚点全路径、build_publish 路径）→ 第 10 条改为脚本产生清单。
- 由空间文件上移为技能：方法随仓库走（sync.sh / restore.sh），触发词双保险（技能 description + 用户级记忆）。

## 更早的教训（写进正文条款）

| 日期 | 事故 | 落到哪条 |
|---|---|---|
| 2026-10-27 | 误删暂存目录内 15 条记忆原件（三处无副本） | 第 3、15 条 |
| 2026-10-27 | 全空间收敛实测：poker 25 个、台账 16 个令牌零丢失、16 处路径 exists 全过 | 第 10 条 |
| 2026-10-26 | AST 判盘符路径（朴素正则误把 `http://` 当路径） | 第 12 条 |

## 外部调研结论（勿重复查）

- `agent-almanac/prune-agent-memory`：自我检查不算核验、需外部锚点、删除留审计账、压缩时不新写
- `moltq` / `pearceit` 生产实践：推测词被压缩拔高成定论是高频隐性损伤
- `rem-sleep`：分档（Consolidate / Defrag）、拿不准就保留
- `memory-merger`：两条记忆冲突时不自己选边
- OpenClaw 社区：重要内容前置（截断从尾部开始）、频繁重写破坏缓存
- 技能工程标准（2026-10）：成熟度 L0-L5、可验证逻辑必须脚本化、≥3 个 eval 场景、正文 <5,000 tokens
- 不采用：letta / cognee 类向量库方案（要服务、要 key、不可人读）

## v1.5.0（2026-11-08）忘坑与止损

**问题**：坑记了但召回靠模型自觉（卡片 resume 是 instruction-gated），跨空间的坑更是看不见；返工无熔断（一翔 6 脚本作废、核对写 5 遍——换了说法没换事没人拦）。

**外部依据**（2026-11-08 调研，勿重复查）：
- AgentsMesh：recall 靠规则提醒必然失败，改 hook（动作前确定性注入）才 deterministic——"Models don't remember to ask"
- enso-os（94★）：SessionStart 注入 lessons、rules in code not prompts、"200 行 hooks > 800 行 prompt"
- ShieldCortex：stored memory ≠ active memory，纠错埋在散文里配不上当前问题
- TradeMemory：预飞检查——先召回教训再行动，红灯即停
- 熔断阶梯（CSDN/xzhibot）：同一做法第 2 次失败必须停并报告；终止三判据（成功/失败/放弃）

**换机后重注册 hook**（settings.json 是账号级不进仓库；让助手改 settings.json 即可）：
在 `%USERPROFILE%\.workbuddy\settings.json` 的 `hooks.SessionStart` 数组追加：
`{"matcher":"","hooks":[{"type":"command","command":"\"<python3.13绝对路径>\" \"%USERPROFILE%\\.workbuddy\\skills\\workspace-converge\\scripts\\pitfall_inject.py\"","timeout":10,"metadata":{"managed_by":"pitfall-reminder"}}]}`
验证：新会话开头应出现 `<pitfall-reminder>` 段；`pitfalls/inject.log` 有当次记录。

**变更**：
- 新增「止损三条款」（返工熔断/方向门/放弃判据）——干活时生效，不等收尾
- A 档记坑必填**触发场景**；复发≥2 或跨空间 → 晋升 `references/pitfalls-INDEX.md`（SessionStart hook 数据源，scripts/pitfall_inject.py 每会话注入前 6 条；脚本与索引都在技能内＝随 sync.sh 仓库走，换机 restore 后重注册 hook 即可，注册命令见下）
- A 档新增止损回填：止损原因当场写成坑
- B 档新增第 15 条坑体检：MEMORY 坑逐条判定晋升/留置/失效
- 配套：my-project-card 2.0.1 简报置顶「⚠ 开工先读：坑与已排除」（card.py grab_section，acceptance 30/30）
- 场景 E5（止损）加入 evals

## v1.5.1（2026-11-08 晚）编码缺陷修复

**现象**：新会话实测坑注入通了（7 条全对），但内容到达时是乱码——hook 宿主（Node spawn）环境无 PYTHONUTF8/PYTHONIOENCODING，Python 管道 stdout 默认 cp936，文本层 write 吐 GBK 字节，宿主按 UTF-8 解码即花。接收方靠读源文件才还原。

**修复**：pitfall_inject.py 改为 `sys.stdout.buffer` 显式写 UTF-8 字节；敌意环境（剥掉全部编码变量）实测输出严格 UTF-8 通过。

**沉淀**：新坑「[编码] 管道stdout默认GBK」晋升进 pitfalls-INDEX.md（天生跨空间：本机一切被宿主捕获 stdout 的脚本都适用），inject 7→8。

## v1.6.0（2026-11-09）TTL 到期清理 + 全面优化

**问题**：收敛只归档不删除，全机 26 个隔离单元 / 300+ 文件 / 最老 28 天从没清过。用户要求「3 天后再次运行收敛技能，自行删除」。

**调研**（2026-11-09，出处与全文摘要见 `references/ttl-guide.md` 第九节，**勿重复查**）：
- Hermes Curator RFC #16077：archive-only + 显式 purge + pin + ledger + dry-run + 引用 cron 跳过
- Archive Management Skill：TTL 且 applied_count=0 才删、活跃引用永不删、清理写 archive.log
- 本机每周体检 v9.3：计划冻结 / 24h 活动守卫 / 路径断言 / manifest 校验 / 回读校验
- openclaw-optimization-guide：MEMORY.md 只做索引

**变更**：
- 新增 `scripts/ttl.py`（init / backfill / scan / purge / pin），只依赖标准库；输出走 stdout.buffer 显式 UTF-8
- 新增 `references/ttl-guide.md`：细则、命令速查、与 v9.3 的分工、调研出处、首跑实测
- SKILL.md 新增第 25–30 条（精简版，细则下沉）、description/description_zh 同步加 TTL 触发词、速览加「到期清理」、脚本表加 ttl.py
- evals 新增 E6（六场景覆盖未到期 / 引用 / pin / 首次 dry-run / 幂等 / 分类）
- 存量 26 单元补 `_TTL.json`（非破坏）；当前空间首次 dry-run 已跑、armed 已写、**本轮零删除**
- 主动 pin `test_ledger.xlsx` / `test_ledger2.xlsx`（check_ledger.py 回归样本）

**用户拍板**：只删垃圾类 / 存量补 manifest 立即执行 / 自动删＋留痕（首次 dry-run）。

**两种判断与上一版不同**：10-26 反对建 learnings 技能、10-29 反对建第 13 个技能，理由是"复盘不能让操作变快"；这次 TTL 是从真实堆积里长出来的、有确定性脚本和验收场景，条件不同结论不同。

## v1.7.0（2026-11-10 晚）收尾链 + Stop 自动清理

**问题**：用户问「卡片技能与收敛技能是否重复、要不要把收敛合并进卡片」。核查后定性为**编排重复**而非能力重复：同一轮收尾要写卡片 / MEMORY.md / 当天日志三处，且收敛 A 档靠模型自觉、卡片 Stop 守卫是 hook，表现成「卡片每次都拦、收敛常常没干」。

**调研（勿重复查）**：合并派 close-session / wrap-it-up / Session Cleanup 都把「写记忆」与「清产物」放同一收尾流程，但删除一律先审计或交互确认；分离派 claude-mem `auto-clear.js`（只清上下文不删盘、必须先 `work_state_write` 成功）、Neat Freak（知识收尾与清场分阶段，「最初说做完后清理不替代最终确认」）、living-docs-governance（one canonical owner per fact）、moltbook/clirank（scratch 与 durable 分层）、GitHub Copilot CLI（cleanup 只预览、prune 要 dry-run）。**结论**：主流把两者放同一流程的不同阶段，不做同一个自动删除动作；且两技能本来是上下游（收敛写坑索引 → 坑注入 hook ＋ 卡片简报置顶消费），合并会切断。

**三处口径矛盾（用户裁决）**：用户级记忆「列待删、产物不自行删除」／SKILL.md A 档「只删本轮新建的」／v1.6.0 TTL 真删 purge。用户拍板：**方案 A 不合并 ＋ A 档真删本轮新建中间产物 ＋ 沿用 TTL 模式**（首次 dry-run，之后自动删并留台账）。

**变更**：
- 新增 `references/wrap-routing.md`（归属表唯一主本：一张表定死什么写哪、收尾链、删除硬规矩）
- 新增 `scripts/wrap_cleanup.py`（Stop hook 调用；复用 ttl.py 的 `sha256` / `collect_refs` / `referenced` / `PIN_MARKERS`，不重复造护栏）
- 新增 `scripts/acceptance_wrap.py`（22 项，整场跑在临时 HOME）
- SKILL.md：description 弱化「任务收尾」抢词、A 档第 1/4 条改口径、速览/脚本表/参考更新、version 1.7.0；evals 新增 E7
- 配套 `my-project-card`：SKILL.md 加归属表指针、`stop_guard.py` reason 加「同一件事只写一处、不要自己删文件」；顺手修其 `description_en` 的 `project: goal` 冒号+空格隐患（11-10 同类事故）
- 两个技能的 description 已同步进 `.skill-list-cache.json`，备份在本空间 `.workbuddy/backups/`

**挂载与验收**：`settings.json` 是账号级、不进仓库。`hooks.Stop` 现共 3 条（tdrive / `stop_guard.py` / `wrap_cleanup.py`），挂载前备份、挂载后回读校验「非 hooks 键 + SessionStart + SessionEnd + 原 Stop 条目」均未变。**完整可复制的挂载命令在 `references/wrap-routing.md`「生效前提」**（别在 changelog 里再存一份）；改完 hooks 不热加载，须重启或在 `/hooks` 面板审阅。
- `my-project-card/scripts/acceptance.py` 41/41、`scripts/acceptance_wrap.py` 22/22 通过；两技能 frontmatter 9 项齐全、description 与路由缓存一致、无「冒号+空格」。
- `py_compile` 四个脚本通过；真实 hook 命令喂空输入 `{}` → exit 0、stdout/stderr 均 0 字节（hook 协议不脏）。
- 交付前必跑 `verify_sync.py`（本机 / 仓库 / `origin/main` 全技能一致，exit 0）。

**本机环境**：三个 Python 都没装 PyYAML，frontmatter 改用等价的 plain-scalar 严格检查（重点复现「冒号+空格」事故），别再花时间找解析器。

## v1.8.0（2026-11-10 深夜）上下文交接

**问题**：复杂任务几轮就触发平台自动压缩，压缩中断对话、且丢中间状态；用户想主动掌握节奏，明确「总不能一句话一个会话吧」。

**本机实测**：会话记录最大 25.4 MB / 4739 行，单会话 22–38 次 compact 标记；平台有 `ContextSummaryAgent` / `compact-summary` 注入 / 会话级 `preMessageCompactPct`，但 **app.asar 里 `PreCompact` 出现 0 次**（无压缩前钩子）；可用 hooks 只有 SessionStart / Stop / SessionEnd；官方文档未公开压缩阈值设置。

**调研**（出处与全文摘要见 `references/handoff-guide.md` 第八节，**勿重复查**）：Claude Code（~95% 自动压缩、`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=70`、PreCompact hook、`/compact` 带指令）、OpenAI Codex（服务端 `/responses/compact`、`auto_compact_limit`、大输出落文件只留引用）、Gemini CLI（SNAPSHOT/ROLLING_SUMMARY 节点＋滞回触发）、LangGraph（`trigger=("fraction",0.8)`、`keep` 最近 20 条、`summary_prompt` 保数字人名）、GitHub `affaan-m/everything-claude-code` 的 `strategic-compact` SKILL.md（阶段边界决策表、what survives/lost、真实 token 主信号、工具调用数是弱代理、"把计划写进文件"）。

**共同结论**：主流不靠更频繁压缩，而靠「逻辑边界压缩 + 压缩前把状态写进文件」。平台没有 PreCompact 时，把压缩点交还给人、状态承接交给文件，是同等效果的替代路径。

**用户拍板**：只做方案 A；HANDOVER 落空间内；不做 C（不调平台水位）、不做 B（不加 Stop 水位 hook）、不做 D（不只靠自觉）；不新建技能。

**变更**：
- 新增 `scripts/handoff.py`（save/show/clear/summary：六字段校验、原子写、全局活跃指针、7 天过期、≤220 字符注入摘要）
- 扩展 `scripts/pitfall_inject.py`：SessionStart 在坑提醒后追加 `<handoff>` 摘要，**复用现有 hook，不新增条目、不碰平台配置**
- `references/handoff-guide.md`（权威细则、阶段边界表、调研出处、换机说明）＋ `wrap-routing.md` 归属表加一行（HANDOVER 只放会话态、结论只留指针）
- SKILL.md 第 31–35 条、description 三处同步加「交接 / 上下文压缩」触发词、v1.8.0；evals 加 E8；templates 加模板
- 端到端实测 8 项通过（字段校验拒绝缺节、clear 归档不删、撤销指针后不再注入、严格 UTF-8）
